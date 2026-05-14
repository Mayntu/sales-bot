"""
Synchronous SQLAlchemy engine for Celery workers.

Uses psycopg2 (sync driver). Pool is shared across tasks in the same worker process.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Replace asyncpg with psycopg2 — psycopg2-binary is already in requirements
_sync_url = settings.database_url.replace("+asyncpg", "+psycopg2")

sync_engine = create_engine(
    _sync_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    pool_recycle=settings.db_pool_recycle,
)

SyncSession = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)
