from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
import jwt
from db.session import get_db
from db.models import User
from core.security import decode_access_token, TokenType
from .service import get_user_by_id


# Bearer token security for access tokens
access_security = HTTPBearer(auto_error=False, scheme_name="AccessToken")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(access_security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user from access token.
    Only accepts valid access tokens (not refresh tokens).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not credentials:
        raise credentials_exception
    
    token = credentials.credentials
    
    try:
        payload = decode_access_token(token)
        
        # Validate token type - must be access token
        token_type = payload.get("type")
        if token_type != TokenType.ACCESS.value:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type. Access token required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        sub = payload.get("sub")
        if not sub:
            raise credentials_exception
        
        user_id = int(sub)
            
    except jwt.PyJWTError:
        raise credentials_exception
    except ValueError:
        # int() conversion failed
        raise credentials_exception
        
    user = await get_user_by_id(db, user_id=user_id)
    
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    return user
