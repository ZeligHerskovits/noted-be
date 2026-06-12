import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Prefer environment configuration; keep fallback for local/dev.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://devuser:noteddev%401234@3.149.182.148:5432/noted_dev",
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=int(os.getenv("DB_POOL_SIZE", "3")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "2")),
    pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "10")),
    pool_use_lifo=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# REMINDER: You must create the 'trusted_devices' table in your database for OTP login to work.
# Use Alembic or a manual SQL migration, since auto-creation is not enabled. 