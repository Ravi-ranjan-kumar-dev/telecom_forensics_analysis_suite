"""Database operations for application users."""

from __future__ import annotations

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from . import models, schemas
from .schemas import UserRole
from .security import hash_password


class FirstAdminAlreadyExistsError(RuntimeError):
    """Raised when first-time setup has already been completed."""


def get_user_by_username(
    db: Session,
    username: str,
) -> models.User | None:
    return (
        db.query(models.User)
        .filter(models.User.username == username)
        .first()
    )


def user_count(db: Session) -> int:
    """Return the number of application user accounts."""

    return int(
        db.query(func.count(models.User.id)).scalar()
        or 0
    )


def create_user(
    db: Session,
    user: schemas.UserCreate,
) -> models.User:
    """Create a user with the requested validated role."""

    db_user = models.User(
        username=user.username,
        password_hash=hash_password(user.password),
        role=user.role.value,
        is_active=True,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def create_first_admin(
    db: Session,
    request: schemas.FirstAdminCreate,
) -> models.User:
    """Create the only unauthenticated account allowed by setup."""

    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(
            text("LOCK TABLE users IN EXCLUSIVE MODE")
        )

    if user_count(db):
        raise FirstAdminAlreadyExistsError(
            "First-time setup has already been completed."
        )

    admin = models.User(
        username=request.username,
        password_hash=hash_password(request.password),
        role=UserRole.admin.value,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def update_user_role(
    db: Session,
    username: str,
    new_role: UserRole,
) -> models.User | None:
    """Update a user's role."""

    user = get_user_by_username(db, username)
    if not user:
        return None
    if not isinstance(new_role, UserRole):
        raise ValueError("Invalid role")
    user.role = new_role.value
    db.commit()
    db.refresh(user)
    return user


def update_user_password(
    db: Session,
    user: models.User,
    new_password: str,
) -> models.User:
    """Replace a user's password hash and persist the change."""

    user.password_hash = hash_password(new_password)
    db.commit()
    db.refresh(user)
    return user


def list_all_users(db: Session) -> list[models.User]:
    """Return all application user accounts ordered by ID."""
    return db.query(models.User).order_by(models.User.id.asc()).all()


def create_officer_account(
    db: Session,
    officer: schemas.AdminOfficerCreate,
) -> models.User:
    """Create a new police officer / investigator account."""
    db_user = models.User(
        username=officer.username.strip(),
        password_hash=hash_password(officer.password),
        role=officer.role.value,
        is_active=True,
        full_name=(officer.full_name or "").strip(),
        police_unit=(officer.police_unit or "").strip(),
        district=(officer.district or "").strip(),
        state=(officer.state or "").strip(),
        mobile_number=(officer.mobile_number or "").strip(),
        expires_at=(officer.expires_at or "").strip(),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def update_user_status(
    db: Session,
    username: str,
    *,
    is_active: bool,
    expires_at: str | None = None,
) -> models.User | None:
    """Activate/deactivate an officer account and optionally set expiry date."""
    user = get_user_by_username(db, username)
    if not user:
        return None
    user.is_active = bool(is_active)
    if expires_at is not None:
        user.expires_at = str(expires_at).strip()
    db.commit()
    db.refresh(user)
    return user
