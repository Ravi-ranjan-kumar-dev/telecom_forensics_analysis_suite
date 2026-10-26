"""Shared current-account policy for managed API operations."""
from datetime import datetime, time, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from . import crud
from .auth import InvalidTokenError, decode_token, oauth2_scheme
from .database import get_db


def account_is_usable(user, *, now=None):
    if user is None or not user.is_active:
        return False
    expiry = str(getattr(user, 'expires_at', '') or '').strip()
    if not expiry:
        return True
    try:
        if len(expiry) == 10:
            # A date-only expiry includes that calendar day in UTC.
            deadline = datetime.combine(datetime.fromisoformat(expiry).date(), time(), timezone.utc) + timedelta(days=1)
        else:
            deadline = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError):
        return False
    return (now or datetime.now(timezone.utc)) < deadline


def current_account(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)):
    try:
        payload = decode_token(token)
    except InvalidTokenError as error:
        raise HTTPException(status_code=401, detail='Invalid token') from error
    user = crud.get_user_by_username(db, str(payload.get('sub', '')))
    if not account_is_usable(user):
        raise HTTPException(status_code=403, detail='Account is disabled, expired or unavailable')
    return user


def require_master_importer(user):
    if not account_is_usable(user) or user.role != 'admin':
        raise HTTPException(status_code=403, detail='Active administrator account required for master imports')
    return user
