"""SDR and CGI lookup endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Annotated

from ..database import get_db
from ..auth import oauth2_scheme
from .. import models, schemas

router = APIRouter(prefix="/api/lookup", tags=["Lookup"])


# ----------------------------- SDR Lookup -----------------------------

@router.get("/sdr/{mobile_number}", response_model=schemas.SDRProfileOut)
def lookup_sdr(
    mobile_number: str,
    db: Session = Depends(get_db),
    token: Annotated[str, Depends(oauth2_scheme)] = None,
):
    """
    Lookup a mobile number in the SDR subscriber database.
    Returns subscriber name, address, father name, etc.
    """
    # This is a placeholder; you can later use JWT to authorize if needed.
    # For now, we'll use a simple query.

    # Lookup in SDR table
    subscriber = (
        db.query(models.SDRSubscriber)
        .filter(models.SDRSubscriber.mobile_number == mobile_number)
        .first()
    )

    if not subscriber:
        raise HTTPException(status_code=404, detail="SDR profile not found for this number")

    return subscriber


# ----------------------------- CGI Lookup -----------------------------

@router.get("/cgi/{cgi_value}", response_model=schemas.CGIProfileOut)
def lookup_cgi(
    cgi_value: str,
    db: Session = Depends(get_db),
    token: Annotated[str, Depends(oauth2_scheme)] = None,
):
    """
    Lookup a CGI / Cell ID in the tower address database.
    Returns operator, circle, address, coordinates, etc.
    """
    tower = (
        db.query(models.CGIAddress)
        .filter(models.CGIAddress.cgi == cgi_value)
        .first()
    )

    if not tower:
        raise HTTPException(status_code=404, detail="CGI / Cell record not found")

    return tower
