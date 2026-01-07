from datetime import datetime, timedelta
from typing import Dict, Any
from enum import Enum
from passlib.context import CryptContext
import jwt
import hashlib
from .config import settings


class TokenType(str, Enum):
    """Token type constants for type-safe token validation."""
    ACCESS = "access"
    REFRESH = "refresh"
    PASSWORD = "password"  # Short-lived token for password reset via OAuth


# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_token(token: str) -> str:
    """
    Hash a token for secure storage in database.
    Uses SHA-256 which is fast and suitable for tokens (not passwords).
    """
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(data: Dict[str, Any]) -> str:
    to_encode = data.copy()
    
    # Add expiration time 
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": TokenType.ACCESS.value})
    
    # Encode JWT
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any]) -> str:
    to_encode = data.copy()
    expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire, "type": TokenType.REFRESH.value})
    
    encoded_jwt = jwt.encode(
         to_encode, 
         settings.JWT_SECRET_KEY, 
         algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def create_password_token(data: Dict[str, Any]) -> str:
    """
    Create a short-lived password token for OAuth users to reset password.
    Configurable via PASSWORD_TOKEN_EXPIRE_MINUTES (default 10 mins).
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.PASSWORD_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": TokenType.PASSWORD.value})
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM]
    )
    
    return payload
