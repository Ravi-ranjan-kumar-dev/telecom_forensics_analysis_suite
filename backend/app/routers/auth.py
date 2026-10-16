"""Authentication and first-time setup endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..auth import (
    InvalidTokenError,
    create_access_token,
    decode_token,
    oauth2_scheme,
    validate_password_reset_token,
)
from ..database import get_db
from ..security import verify_password

router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
)

INVALID_CREDENTIALS = "Incorrect username or password"
INVALID_RESET = "Invalid or expired password-reset credentials"


@router.get(
    "/setup-status",
    response_model=schemas.SetupStatus,
)
def setup_status(
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Report whether the first application administrator is required."""

    return {
        "setup_required": crud.user_count(db) == 0,
    }


def _create_first_admin(
    request: schemas.FirstAdminCreate,
    db: Session,
):
    try:
        return crud.create_first_admin(db, request)
    except crud.FirstAdminAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="First-time setup has already been completed.",
        ) from error


@router.post(
    "/setup-admin",
    response_model=schemas.UserOut,
    status_code=status.HTTP_201_CREATED,
)
def setup_admin(
    request: schemas.FirstAdminCreate,
    db: Session = Depends(get_db),
):
    """Create the first admin only while the user table is empty."""

    return _create_first_admin(request, db)


@router.post(
    "/register",
    response_model=schemas.UserOut,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def register_first_admin_compatibility(
    request: schemas.FirstAdminCreate,
    db: Session = Depends(get_db),
):
    """Keep the old path as a setup-only compatibility endpoint."""

    return _create_first_admin(request, db)


@router.post(
    "/login",
    response_model=schemas.Token,
)
def login(
    form_data: Annotated[
        OAuth2PasswordRequestForm,
        Depends(),
    ],
    db: Session = Depends(get_db),
) -> dict[str, str]:
    username = form_data.username.strip()
    user = crud.get_user_by_username(db, username)
    if (
        not user
        or not user.is_active
        or not verify_password(
            form_data.password,
            user.password_hash,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        access_token = create_access_token(
            data={
                "sub": user.username,
                "role": user.role,
            }
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backend authentication is not configured.",
        ) from error

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.get(
    "/me",
    response_model=schemas.UserOut,
)
def read_users_me(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    try:
        payload = decode_token(token)
    except InvalidTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from error

    username = str(payload.get("sub", ""))
    user = crud.get_user_by_username(db, username)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    return user


@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
)
def forgot_password(
    request: schemas.PasswordResetRequest,
) -> dict[str, str]:
    """Return a non-enumerating description of the local reset flow."""

    del request
    return {
        "message": (
            "Use an administrator-issued, short-lived reset token. "
            "No account or token details are returned by this endpoint."
        )
    }


@router.post("/reset-password")
def reset_password(
    request: schemas.PasswordResetConfirm,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Reset a password with a short-lived token issued on the host."""

    user = crud.get_user_by_username(
        db,
        request.username,
    )
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=INVALID_RESET,
        )

    try:
        validate_password_reset_token(
            request.token,
            username=user.username,
            password_hash=user.password_hash,
        )
    except InvalidTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=INVALID_RESET,
        ) from error

    crud.update_user_password(
        db,
        user,
        request.new_password,
    )
    return {
        "message": "Password reset successfully.",
    }
