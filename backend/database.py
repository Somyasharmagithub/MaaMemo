import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# ==================================================
# PATHS
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent

# main.py imports DATA_DIR to store uploaded audio and narration files.
# On Render, set MAAMEMO_DATA_DIR only if a persistent disk is mounted.
DATA_DIR = Path(
    os.getenv("MAAMEMO_DATA_DIR", str(BASE_DIR))
).expanduser()

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Local SQLite database path
DATABASE_PATH = DATA_DIR / "maamemo.db"


# ==================================================
# DATABASE CONFIGURATION
# ==================================================

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    # SQLAlchemy 2.1 may select the psycopg (v3) driver for a plain
    # postgresql:// URL. This project installs psycopg2-binary instead,
    # so explicitly select the psycopg2 dialect.
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgres://",
            "postgresql+psycopg2://",
            1
        )

    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgresql://",
            "postgresql+psycopg2://",
            1
        )

    elif DATABASE_URL.startswith("postgresql+psycopg://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgresql+psycopg://",
            "postgresql+psycopg2://",
            1
        )

    print("Using PostgreSQL database")

else:
    # Local development fallback
    DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"
    print(f"Using local SQLite database: {DATABASE_PATH}")


# ==================================================
# DATABASE ENGINE
# ==================================================

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


# ==================================================
# DATABASE SESSION
# ==================================================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


# ==================================================
# BASE CLASS
# ==================================================

Base = declarative_base()


# ==================================================
# DATABASE DEPENDENCY
# ==================================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
