
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# --------------------------------------------------
# PATHS
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

# Used for audio files by main.py
DATA_DIR = Path(
    os.getenv("MAAMEMO_DATA_DIR", str(BASE_DIR))
)

DATA_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# DATABASE CONFIGURATION
# --------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.strip()

    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgres://",
            "postgresql://",
            1
        )

    print("Using PostgreSQL database")

else:
    DATABASE_PATH = DATA_DIR / "maamemo.db"
    DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

    print(f"Using local SQLite database: {DATABASE_PATH}")


# --------------------------------------------------
# DATABASE ENGINE
# --------------------------------------------------

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True
    )

else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"sslmode": "require"}
    )


# --------------------------------------------------
# DATABASE SESSION
# --------------------------------------------------

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


# --------------------------------------------------
# BASE CLASS
# --------------------------------------------------

Base = declarative_base()


# --------------------------------------------------
# DATABASE DEPENDENCY
# --------------------------------------------------

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
