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
