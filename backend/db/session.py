from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator
from core.config import settings


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False, 
    pool_pre_ping=True,
    future=True,
    pool_size=20,  # Maximum number of connections to keep in pool
    max_overflow=10,  # Maximum overflow connections
    pool_timeout=30,  # Seconds to wait before giving up on getting a connection
    pool_recycle=3600  # Recycle connections after 1 hour
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
