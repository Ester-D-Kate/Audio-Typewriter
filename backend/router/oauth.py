import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi_sso.sso.google import GoogleSSO
from fastapi_sso.sso.github import GithubSSO

from core.config import settings
from db.session import get_db
from auth.schemas import OAuthToken
from auth.service import (
    get_or_create_oauth_user,
    create_user_access_token,
    create_user_refresh_token,
    create_user_password_token
)
from auth.utils import get_device_info

logger = logging.getLogger(__name__)
router = APIRouter()

# Determine if insecure HTTP is allowed (only for localhost development)
_allow_insecure = settings.BASE_URL.startswith("http://localhost")

# Initialize SSO providers (only if configured)
google_sso = None
if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
    google_sso = GoogleSSO(
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        redirect_uri=f"{settings.BASE_URL}/auth/google/callback",
        allow_insecure_http=_allow_insecure
    )
    logger.info("Google OAuth initialized")

github_sso = None
if settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET:
    github_sso = GithubSSO(
        client_id=settings.GITHUB_CLIENT_ID,
        client_secret=settings.GITHUB_CLIENT_SECRET,
        redirect_uri=f"{settings.BASE_URL}/auth/github/callback",
        allow_insecure_http=_allow_insecure
    )
    logger.info("GitHub OAuth initialized")


@router.get("/google/redirect", tags=["OAuth"])
async def google_redirect():
    """Redirect to Google OAuth login page."""
    if not google_sso:
        logger.warning("Google OAuth redirect attempted but not configured")
        raise HTTPException(status_code=501, detail="Google auth not configured")
    
    logger.info("Redirecting to Google OAuth")
    async with google_sso:
        return await google_sso.get_login_redirect()


@router.get("/google/callback", response_model=OAuthToken, tags=["OAuth"])
async def google_callback(
    request: Request, 
    db: AsyncSession = Depends(get_db)
):
    """Google OAuth callback - creates or retrieves user and returns tokens."""
    if not google_sso:
        raise HTTPException(status_code=501, detail="Google auth not configured")
    
    logger.info("Google OAuth callback received")
    device_info = get_device_info(request)
        
    async with google_sso:
        user_info = await google_sso.verify_and_process(request)
    
    if not user_info.email:
        logger.warning("Google OAuth failed: no email provided")
        raise HTTPException(status_code=400, detail="No email provided by Google")
        
    user = await get_or_create_oauth_user(
        db=db, 
        email=user_info.email,
        provider="google"
    )
    logger.info("Google OAuth user authenticated")
    
    access_token = create_user_access_token(user)
    refresh_token = await create_user_refresh_token(db, user, device_info)
    password_token = create_user_password_token(user)
    logger.info("Google OAuth completed: tokens issued")
    
    return OAuthToken(
        access_token=access_token,
        refresh_token=refresh_token,
        password_token=password_token,
        token_type="bearer"
    )


@router.get("/github/redirect", tags=["OAuth"])
async def github_redirect():
    """Redirect to GitHub OAuth login page."""
    if not github_sso:
        logger.warning("GitHub OAuth redirect attempted but not configured")
        raise HTTPException(status_code=501, detail="GitHub auth not configured")
    
    logger.info("Redirecting to GitHub OAuth")
    async with github_sso:
        return await github_sso.get_login_redirect()


@router.get("/github/callback", response_model=OAuthToken, tags=["OAuth"])
async def github_callback(
    request: Request, 
    db: AsyncSession = Depends(get_db)
):
    """GitHub OAuth callback - creates or retrieves user and returns tokens."""
    if not github_sso:
        raise HTTPException(status_code=501, detail="GitHub auth not configured")
    
    logger.info("GitHub OAuth callback received")
    device_info = get_device_info(request)
        
    async with github_sso:
        user_info = await github_sso.verify_and_process(request)
        
    if not user_info.email:
        logger.warning("GitHub OAuth failed: no email provided")
        raise HTTPException(status_code=400, detail="No email provided by GitHub")
        
    user = await get_or_create_oauth_user(
        db=db,
        email=user_info.email,
        provider="github"
    )
    logger.info("GitHub OAuth user authenticated")
    
    access_token = create_user_access_token(user)
    refresh_token = await create_user_refresh_token(db, user, device_info)
    password_token = create_user_password_token(user)
    logger.info("GitHub OAuth completed: tokens issued")
    
    return OAuthToken(
        access_token=access_token,
        refresh_token=refresh_token,
        password_token=password_token,
        token_type="bearer"
    )

