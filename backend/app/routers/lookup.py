# backend/app/routers/lookup.py
"""SDR and CGI lookup endpoints with secure token validation."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Annotated

from ..database import get_db
from ..auth import oauth2_scheme, decode_token
from .. import models, schemas

router = APIRouter(prefix="/api/lookup", tags=["Lookup"])

def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    payload = decode_token(token)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is disabled")
    return user

@router.get("/sdr/{mobile_number}", response_model=schemas.SDRProfileOut)
def lookup_sdr(
    mobile_number: str,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    subscriber = (
        db.query(models.SDRSubscriber)
        .filter(models.SDRSubscriber.mobile_number == mobile_number)
        .first()
    )
    if not subscriber:
        raise HTTPException(status_code=404, detail="SDR profile not found")
    return subscriber

@router.get("/cgi/{cgi_value}", response_model=schemas.CGIProfileOut)
def lookup_cgi(
    cgi_value: str,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    tower = (
        db.query(models.CGIAddress)
        .filter(models.CGIAddress.cgi == cgi_value)
        .first()
    )
    if not tower:
        raise HTTPException(status_code=404, detail="CGI record not found")
    return tower