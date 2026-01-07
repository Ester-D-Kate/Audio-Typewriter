from pydantic_settings import BaseSettings
from pathlib import Path
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_TOKEN_EXPIRE_MINUTES: int = 10
    MAX_DEVICES_PER_USER: int = 10
    
    BASE_URL: str = "http://localhost:8000"
    
    # CORS - comma-separated origins for web dashboard
    CORS_ORIGINS: str = "*"
    
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    
    GITHUB_CLIENT_ID: str | None = None
    GITHUB_CLIENT_SECRET: str | None = None
    
    # Optional - for future encrypted storage feature
    ENCRYPTION_KEY: str | None = None
    
    GROQ_API_KEY: str = ""
    GROQ_RPM_LIMIT: int = 30
    GROQ_TPM_LIMIT: int = 12000
    APP_USER_RATE_LIMIT_RPM: int = 12
    APP_USER_RATE_LIMIT_RPD: int = 600
    APP_USER_RATE_LIMIT_TPM: int = 6000
    
    class Config:
        env_file = Path(__file__).resolve().parent.parent.parent / ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS into a list."""
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    def validate_settings(self):
        """Validate critical settings are properly configured."""
        errors = []
        
        if not self.DATABASE_URL:
            errors.append("DATABASE_URL is required")
        
        if not self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY) < 32:
            errors.append("JWT_SECRET_KEY must be at least 32 characters")
        
        if errors:
            raise ValueError("Configuration errors: " + "; ".join(errors))


settings = Settings()
settings.validate_settings()
