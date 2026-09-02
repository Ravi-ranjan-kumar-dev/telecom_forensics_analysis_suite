#admin.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Annotated

from ..database import get_db
from ..auth import InvalidTokenError, decode_token, oauth2_scheme
from .. import crud, schemas, models
from ..schemas import UserRole

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
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


@router.put("/user-role", response_model=schemas.UserOut)
def assign_role(
    role_update: schemas.UserRoleUpdate,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    # Ensure the actor is active admin
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not enough permissions")

    user = crud.update_user_role(db, role_update.username, role_update.role)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
