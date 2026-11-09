
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# --------------------------------------------------
# DATABASE CONFIGURATION
# --------------------------------------------------

# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Persistent storage directory:
# Local: MaaMemo project directory
# Render: /var/data (configured through environment variable)
DATA_DIR = Path(
    os.getenv("MAAMEMO_DATA_DIR", str(BASE_DIR))
)

# Ensure storage directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# SQLite database file
DATABASE_PATH = DATA_DIR / "maamemo.db"

# SQLite connection URL
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"


# --------------------------------------------------
# DATABASE ENGINE
# --------------------------------------------------

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True
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
# BASE CLASS FOR DATABASE MODELS
# --------------------------------------------------

Base = declarative_base()


# --------------------------------------------------
# DATABASE SESSION DEPENDENCY
# --------------------------------------------------

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
