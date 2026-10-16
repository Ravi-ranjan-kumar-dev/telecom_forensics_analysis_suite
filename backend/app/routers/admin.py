"""Admin endpoints for managing Police Officer accounts, roles, status & passwords."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import InvalidTokenError, decode_token, oauth2_scheme
from ..database import get_db

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> models.User:
    try:
        payload = decode_token(token)
    except InvalidTokenError as error:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        ) from error
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = crud.get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _require_admin(current_user: models.User) -> models.User:
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return current_user


@router.get("/users", response_model=list[schemas.UserOut])
def list_users(
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    return crud.list_all_users(db)


@router.post(
    "/users",
    response_model=schemas.UserOut,
    status_code=status.HTTP_201_CREATED,
)
def create_officer(
    officer: schemas.AdminOfficerCreate,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    existing = crud.get_user_by_username(db, officer.username.strip())
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Username '{officer.username}' already exists.",
        )
    return crud.create_officer_account(db, officer)


@router.put("/user-role", response_model=schemas.UserOut)
def assign_role(
    role_update: schemas.UserRoleUpdate,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    user = crud.update_user_role(db, role_update.username, role_update.role)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/users/{username}/status", response_model=schemas.UserOut)
def update_officer_status(
    username: str,
    status_update: schemas.UserStatusUpdate,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    if username.strip() == current_user.username and not status_update.is_active:
        raise HTTPException(
            status_code=400,
            detail="Administrator cannot deactivate their own active account.",
        )
    user = crud.update_user_status(
        db,
        username.strip(),
        is_active=status_update.is_active,
        expires_at=status_update.expires_at,
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/users/{username}/reset-password")
def admin_reset_officer_password(
    username: str,
    reset_req: schemas.AdminPasswordReset,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    user = crud.get_user_by_username(db, username.strip())
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    crud.update_user_password(db, user, reset_req.new_password)
    return {"message": f"Password updated for {user.username}."}
