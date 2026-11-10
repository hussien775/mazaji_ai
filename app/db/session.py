from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)
from app.core.config import settings

# Create modern async SQLAlchemy engine with optimized connection pooling
async_engine = create_async_engine(
    settings.async_database_url,
    echo=False,  # تم إيقاف طباعة الاستعلامات لتسريع المعالجة وحماية الأداء
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE
)

# Async session factory
async_session_factory = async_sessionmaker(
    bind=async_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=AsyncSession
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that yields an async database session per request.
    Automatically closes the session when request completes.
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
