import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from core.security import decode_access_token, TokenType, verify_password, get_password_hash
from db.session import get_db
from db.models import User
from auth.schemas import (
    UserCreate, 
    UserLogin, 
    UserRead, 
    Token, 
    UserUpdate,
    PasswordResetRequest,
    UserUsernameUpdate, 
    UserDelete,
    RefreshTokenRequest
)
from auth.service import (
    get_user_by_email,
    get_user_by_username,
    create_user,
    authenticate_user,
    create_user_access_token,
    update_user,
    get_user_by_id,
    delete_user,
    create_user_refresh_token,
    refresh_user_tokens,
    revoke_user_refresh_token,
    get_user_devices, 
    revoke_all_user_tokens
)
from auth.dependencies import get_current_user
from auth.utils import get_device_info

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED, tags=["Authentication"])
async def signup(
    user_in: UserCreate, 
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user and return access + refresh tokens."""
    device_info = get_device_info(request)
    logger.info("Signup attempt started")
    
    if user_in.username:
        existing_user = await get_user_by_username(db, username=user_in.username)
        if existing_user:
            logger.warning("Signup failed: username already exists")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered"
            )
    
    if user_in.email:
        existing_user = await get_user_by_email(db, email=user_in.email)
        if existing_user:
            logger.warning("Signup failed: email already exists")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    user = await create_user(db, user_in)
    logger.info("User created successfully")
    
    access_token = create_user_access_token(user)
    refresh_token = await create_user_refresh_token(db, user, device_info)
    logger.info("Signup completed: tokens issued")
    
    return Token(
        access_token=access_token, 
        refresh_token=refresh_token, 
        token_type="bearer"
    )


@router.post("/login", response_model=Token, tags=["Authentication"])
async def login(
    user_in: UserLogin, 
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Authenticate user and return access + refresh tokens."""
    device_info = get_device_info(request)
    logger.info("Login attempt started")
    
    user = await authenticate_user(db, identifier=user_in.identifier, password=user_in.password)
    
    if not user:
        logger.warning("Login failed: invalid credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        logger.warning("Login failed: user account deactivated")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated. Please contact support."
        )
    
    access_token = create_user_access_token(user)
    refresh_token = await create_user_refresh_token(db, user, device_info)
    logger.info("Login successful: tokens issued")
    
    return Token(
        access_token=access_token, 
        refresh_token=refresh_token, 
        token_type="bearer"
    )


@router.get("/user-details", response_model=UserRead, tags=["Authentication"])
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user details."""
    logger.info("User details retrieved")
    return current_user


@router.get("/devices", tags=["Authentication"])
async def get_my_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get list of active devices/IPs for the current user."""
    devices = await get_user_devices(db, current_user)
    logger.info("Device list retrieved")
    return {"devices": devices, "count": len(devices)}


@router.patch("/reset-username", response_model=UserRead, tags=["Authentication"])
async def update_me_username(
    username_data: UserUsernameUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user's username."""
    logger.info("Username update requested")
    try:
        user_update = UserUpdate(username=username_data.username)
        updated_user = await update_user(db, current_user, user_update)
        logger.info("Username updated successfully")
        return updated_user
    except ValueError as e:
        logger.warning("Username update failed: validation error")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/reset-password", response_model=UserRead, tags=["Authentication"])
async def reset_password(
    password_data: PasswordResetRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Reset password using old_password OR password_token."""
    logger.info("Password reset requested")
    verified = False
    
    if password_data.password_token:
        try:
            payload = decode_access_token(password_data.password_token)
            if (payload.get("type") == TokenType.PASSWORD.value and 
                payload.get("purpose") == "password_reset" and
                int(payload.get("sub")) == current_user.id):
                verified = True
                logger.info("Password reset verified via token")
        except Exception:
            logger.debug("Password token verification failed, trying old password")
    
    if not verified and password_data.old_password:
        if verify_password(password_data.old_password, current_user.hashed_password):
            verified = True
            logger.info("Password reset verified via old password")
    
    if not verified:
        logger.warning("Password reset failed: invalid credentials")
        if not password_data.password_token and not password_data.old_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either old_password or password_token is required"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid credentials"
        )
    
    current_user.hashed_password = get_password_hash(password_data.new_password)
    await db.commit()
    await db.refresh(current_user)
    logger.info("Password reset completed successfully")
    
    return current_user


@router.delete("/delete-user", status_code=status.HTTP_204_NO_CONTENT, tags=["Authentication"])
async def delete_me(
    user_in: UserDelete,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete current user account. Requires username confirmation."""
    logger.info("User deletion requested")
    if user_in.username != current_user.username:
        logger.warning("User deletion failed: username mismatch")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username validation failed. Please provide your correct username to confirm deletion."
        )
        
    await delete_user(db, current_user)
    logger.info("User deleted successfully")
    return None


@router.post("/refresh-tokens", response_model=Token, tags=["Authentication"])
async def refresh_tokens(
    token_request: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access and refresh tokens."""
    logger.info("Token refresh requested")
    device_info = get_device_info(request)
    tokens = await refresh_user_tokens(db, device_info, token_request.refresh_token)
    
    if not tokens:
        logger.warning("Token refresh failed: invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info("Token refresh successful")
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["Authentication"])
async def logout(
    token_request: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Logout from the current device/IP."""
    logger.info("Logout requested")
    
    try:
        payload = decode_access_token(token_request.refresh_token)
        
        if payload.get("type") != TokenType.REFRESH.value:
            logger.warning("Logout failed: invalid token type")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token type. Refresh token required."
            )
        
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token"
            )
        
        user_id = int(sub)
        user = await get_user_by_id(db, user_id)
        
        if not user:
            logger.warning("Logout failed: user not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        await revoke_user_refresh_token(db, user, token_request.refresh_token)
        logger.info("Logout successful")
        
    except HTTPException:
        raise
    except Exception:
        logger.error("Logout failed: unexpected error")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Logout failed. Please try again."
        )
        
    return None


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT, tags=["Authentication"])
async def logout_all_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Logout from all devices."""
    logger.info("Logout from all devices requested")
    await revoke_all_user_tokens(db, current_user)
    logger.info("Logged out from all devices successfully")
    return None

