from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
import os
import sys

load_dotenv()

from modules.core.paths import DATABASE_DIR

# Explicit deployments keep their URL. Source installs retain their historical
# PostgreSQL default; local SQLite is opt-in there to avoid hiding old accounts.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
LOCAL_AUTH = os.getenv("ETHICALARMOR_LOCAL_AUTH", "").lower() in {"1", "true", "yes"} or getattr(sys, "frozen", False)
if not DATABASE_URL:
    if LOCAL_AUTH:
        DATABASE_DIR.mkdir(parents=True, exist_ok=True)
        DATABASE_URL = "sqlite:///" + str((DATABASE_DIR / "local_auth.db").resolve()).replace("\\", "/")
    else:
        DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/telecom_forensics"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _configure_sqlite(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


