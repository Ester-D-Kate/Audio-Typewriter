"""
Pydantic schemas for authentication.
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


class UserCreate(BaseModel):
    """Schema for user registration."""
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    """Schema for user login."""
    identifier: str  # Username or email
    password: str


class UserRead(BaseModel):
    """Schema for returning user data."""
    id: int
    username: str
    email: str
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    """Schema for token response (normal login/signup)."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class OAuthToken(BaseModel):
    """Schema for OAuth token response (includes password_token for password reset)."""
    access_token: str
    refresh_token: str
    password_token: str  # For OAuth password reset
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Schema for token refresh request."""
    refresh_token: str


class PasswordResetRequest(BaseModel):
    """
    Schema for password reset.
    Either old_password OR password_token is required (not both).
    - old_password: for users who know their current password
    - password_token: for OAuth users who re-authenticated to reset
    """
    new_password: str = Field(..., min_length=6)
    old_password: Optional[str] = None
    password_token: Optional[str] = None


class UserUpdate(BaseModel):
    """Schema for updating user profile."""
    username: Optional[str] = Field(None, min_length=3, max_length=100)


class UserUsernameUpdate(BaseModel):
    """Schema for username change."""
    username: str = Field(..., min_length=3, max_length=100)


class UserDelete(BaseModel):
    """Schema for account deletion confirmation."""
    username: str = Field(..., min_length=3, max_length=100)


class TextRequest(BaseModel):
    """Schema for text input requests."""
    text: str
