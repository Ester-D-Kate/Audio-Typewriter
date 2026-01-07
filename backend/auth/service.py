from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, delete
from typing import Optional, List
import uuid
import secrets
from .schemas import UserCreate, UserUpdate, Token
from db.models import User, RefreshToken
from core.encryption import encrypt_key
from core.security import (
    create_access_token,
    create_refresh_token,
    create_password_token,
    get_password_hash,
    verify_password,
    decode_access_token,
    hash_token,
    TokenType
)
from core.config import settings


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Get user by email address."""
    result = await db.execute(select(User).filter(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """Get user by username."""
    result = await db.execute(select(User).filter(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_identifier(db: AsyncSession, identifier: str) -> Optional[User]:
    """Get user by either username or email."""
    result = await db.execute(
        select(User).filter(
            or_(User.username == identifier, User.email == identifier)
        )
    )
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """Get user by ID."""
    result = await db.execute(select(User).filter(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, user_in: UserCreate) -> User:
    """Create a new user."""
    hashed_password = get_password_hash(user_in.password)
    
    db_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hashed_password,
        is_active=True
    )
    
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    
    return db_user


async def authenticate_user(db: AsyncSession, identifier: str, password: str) -> Optional[User]:
    """Authenticate user by identifier (username or email) and password."""
    user = await get_user_by_identifier(db, identifier)
    
    if not user:
        return None
    
    if not verify_password(password, user.hashed_password):
        return None
    
    return user


def create_user_access_token(user: User) -> str:
    """Create an access token for the user."""
    return create_access_token(data={
        "sub": str(user.id), 
        "username": user.username or "", 
        "email": user.email or ""
    })


def create_user_password_token(user: User) -> str:
    """
    Create a short-lived password token for OAuth password reset.
    This token allows user to reset password without knowing old password.
    """
    return create_password_token(data={
        "sub": str(user.id),
        "purpose": "password_reset"
    })


async def get_user_device_count(db: AsyncSession, user_id: int) -> int:
    """Get the number of active devices/sessions for a user."""
    result = await db.execute(
        select(func.count(RefreshToken.id)).filter(RefreshToken.user_id == user_id)
    )
    return result.scalar() or 0


async def create_user_refresh_token(db: AsyncSession, user: User, device_info: str) -> str:
    """
    Create a refresh token for a user.
    Auto-deletes oldest session if device limit is reached (user never locked out).
    """
    # FIRST: Clean up any expired tokens for this user
    now = datetime.now(timezone.utc)
    await db.execute(
        delete(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.expires_at < now
        )
    )
    
    # Check device count
    device_count = await get_user_device_count(db, user.id)
    
    # If at limit, delete the OLDEST session (auto-logout)
    if device_count >= settings.MAX_DEVICES_PER_USER:
        oldest_result = await db.execute(
            select(RefreshToken)
            .filter(RefreshToken.user_id == user.id)
            .order_by(RefreshToken.created_at.asc())  # Oldest first
            .limit(1)
        )
        oldest_session = oldest_result.scalar_one_or_none()
        if oldest_session:
            await db.delete(oldest_session)
    
    
    # Create new refresh token
    refresh_token = create_refresh_token(data={
        "sub": str(user.id), 
        "device_info": device_info
    })
    
    # Calculate expiration
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    # Store hashed token in database
    db_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        device_info=device_info,
        expires_at=expires_at
    )
    
    db.add(db_token)
    await db.commit()
    
    return refresh_token


async def refresh_user_tokens(db: AsyncSession, device_info: str, refresh_token: str) -> Optional[Token]:
    """
    Refresh access and refresh tokens for a user.
    Implements token rotation - old refresh token is invalidated.
    """
    # Decode token to get user_id
    try:
        payload = decode_access_token(refresh_token)
        
        # Validate token type
        if payload.get("type") != TokenType.REFRESH.value:
            return None
            
        sub = payload.get("sub")
        if not sub:
            return None
            
        user_id = int(sub)
    except Exception:
        return None
    
    # Get user
    user = await get_user_by_id(db, user_id)
    if not user:
        return None
    
    # Find the stored token by hash (don't match device_info - IP can change!)
    token_hash = hash_token(refresh_token)
    result = await db.execute(
        select(RefreshToken).filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == user_id
        )
    )
    stored_token = result.scalar_one_or_none()
    
    if not stored_token:
        return None
    
    # Check if token is expired
    now = datetime.now(timezone.utc)
    token_expires_at = stored_token.expires_at
    if token_expires_at.tzinfo is None:
        token_expires_at = token_expires_at.replace(tzinfo=timezone.utc)
    
    if token_expires_at < now:
        # Token expired - delete it
        await db.delete(stored_token)
        await db.commit()
        return None
    
    # Token is valid - rotate it
    # Delete old token
    await db.delete(stored_token)
    
    # Create new tokens
    new_access_token = create_user_access_token(user)
    new_refresh_token = create_refresh_token(data={
        "sub": str(user.id), 
        "device_info": device_info
    })
    
    new_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    # Store new refresh token
    new_db_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(new_refresh_token),
        device_info=device_info,
        expires_at=new_expires_at
    )
    
    db.add(new_db_token)
    await db.commit()
    
    return Token(
        access_token=new_access_token,
        refresh_token=new_refresh_token
    )


async def revoke_user_refresh_token(db: AsyncSession, user: User, refresh_token: str) -> bool:
    """Revoke (logout) a specific session by its refresh token."""
    token_hash_value = hash_token(refresh_token)
    result = await db.execute(
        select(RefreshToken).filter(
            RefreshToken.user_id == user.id,
            RefreshToken.token_hash == token_hash_value
        )
    )
    token = result.scalar_one_or_none()
    
    if token:
        await db.delete(token)
        await db.commit()
        return True
    
    return False


async def revoke_all_user_tokens(db: AsyncSession, user: User) -> int:
    """Revoke all refresh tokens for a user (logout from all devices)."""
    result = await db.execute(
        delete(RefreshToken).where(RefreshToken.user_id == user.id)
    )
    await db.commit()
    return result.rowcount


async def get_user_devices(db: AsyncSession, user: User) -> List[dict]:
    """Get list of active devices for a user."""
    result = await db.execute(
        select(RefreshToken).filter(RefreshToken.user_id == user.id)
    )
    tokens = result.scalars().all()
    
    now = datetime.now(timezone.utc)
    devices = []
    for token in tokens:
        token_expires_at = token.expires_at
        if token_expires_at is not None and token_expires_at.tzinfo is None:
            token_expires_at = token_expires_at.replace(tzinfo=timezone.utc)
        devices.append({
            "device_info": token.device_info,
            "created_at": token.created_at.isoformat() if token.created_at else None,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
            "is_expired": token_expires_at < now if token_expires_at else True
        })
    
    return devices


async def get_or_create_oauth_user(
    db: AsyncSession, 
    email: str, 
    provider: str,
    display_name: Optional[str] = None
) -> User:
    """
    Get existing user or create new one for OAuth login.
    
    Args:
        db: Database session
        email: User's email from OAuth provider
        provider: OAuth provider name ('google' or 'github')
        display_name: Display name from provider (not used for username)
    
    Username format: emailprefix_provider (e.g., john_gmail, jane_github)
    This ensures uniqueness as email prefixes are unique per provider.
    """
    user = await get_user_by_email(db, email=email)
    if user:
        return user
    
    # Generate username from email prefix + provider suffix
    email_prefix = email.split("@")[0].lower()
    
    # Clean the email prefix (remove special chars except underscore)
    email_prefix = ''.join(c if c.isalnum() or c == '_' else '' for c in email_prefix)
    
    # Ensure minimum length
    if len(email_prefix) < 3:
        email_prefix = f"{email_prefix}{secrets.token_hex(2)}"
    
    # Provider suffix
    provider_suffix = provider.lower()
    if provider_suffix == 'google':
        provider_suffix = 'gmail'
    
    # Create username as emailprefix_provider
    username = f"{email_prefix}_{provider_suffix}"
    
    # In rare case of collision (shouldn't happen), add random suffix
    existing = await get_user_by_username(db, username)
    if existing:
        username = f"{username}_{secrets.token_hex(2)}"
    
    # Generate random password (user doesn't know it, but can reset via password_token)
    random_password = str(uuid.uuid4())
    
    # Create user with random password (never NULL)
    db_user = User(
        username=username,
        email=email,
        hashed_password=get_password_hash(random_password),
        is_active=True
    )
    
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    
    return db_user


async def update_user(db: AsyncSession, current_user: User, user_in: UserUpdate) -> User:
    """Update user profile (username)."""
    if user_in.username is not None and user_in.username != current_user.username:
        existing = await get_user_by_username(db, user_in.username)
        if existing and existing.id != current_user.id:
             raise ValueError("Username already taken")
        current_user.username = user_in.username

    await db.commit()
    await db.refresh(current_user)
    return current_user




async def delete_user(db: AsyncSession, user: User) -> bool:
    """Delete a user and all related data."""
    await db.delete(user)
    await db.commit()
    return True
