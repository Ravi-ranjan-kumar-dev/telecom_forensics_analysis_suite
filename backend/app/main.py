# backend/app/main.py
import sys
import os

# Add project root to sys.path so we can import 'modules'
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastapi import FastAPI
from .database import engine, Base
from . import models
from .routers import auth, lookup, admin, imports

Base.metadata.create_all(bind=engine)


def _ensure_user_columns() -> None:
    from sqlalchemy import inspect, text
    optional_cols = {
        "full_name": "VARCHAR",
        "police_unit": "VARCHAR",
        "district": "VARCHAR",
        "state": "VARCHAR",
        "mobile_number": "VARCHAR",
        "expires_at": "VARCHAR",
    }
    try:
        inspector = inspect(engine)
        if "users" not in inspector.get_table_names():
            return
        existing = {col["name"] for col in inspector.get_columns("users")}
        with engine.begin() as conn:
            for col_name, col_type in optional_cols.items():
                if col_name not in existing:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
    except Exception:
        pass


_ensure_user_columns()

app = FastAPI(title="Telecom Forensics Backend", version="0.1.0")
__version__ = "1.0.0"

app.include_router(auth.router)
app.include_router(lookup.router)
app.include_router(admin.router)
app.include_router(imports.router)

@app.get("/")
def root():
    return {"message": "Telecom Forensics Backend is running"}

@app.get("/api/health")
def health_check():
    return {"status": "ok"}