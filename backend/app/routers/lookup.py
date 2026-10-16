"""SDR and CGI single + batch lookup endpoints for multi-user VPS deployment."""

from __future__ import annotations

import os
import sys
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from .. import models, schemas
from ..auth import InvalidTokenError, decode_token, oauth2_scheme
from ..database import get_db

from modules.database.cgi_repository import normalize_cgi
from modules.database.lookup_service import lookup_cgi_profile, lookup_sdr_profile
from modules.enrichment.cgi_address_enrichment import _lookup_cgi_addresses_cached
from modules.enrichment.sdr_subscriber_enrichment import (
    lookup_sdr_subscribers_cached,
    normalize_mobile_number,
)

router = APIRouter(prefix="/api/lookup", tags=["Lookup"])


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
    normalized = normalize_mobile_number(mobile_number) or mobile_number.strip()
    subscriber = (
        db.query(models.SDRSubscriber)
        .filter(models.SDRSubscriber.mobile_number.in_([normalized, mobile_number.strip()]))
        .first()
    )
    if subscriber:
        return subscriber

    local_result = lookup_sdr_profile(normalized)
    if local_result.get("found") and local_result.get("record"):
        record = local_result["record"]
        return schemas.SDRProfileOut(
            mobile_number=str(record.get("mobile_number", normalized)),
            subscriber_name=record.get("subscriber_name", ""),
            father_name=record.get("father_name", ""),
            address=record.get("raw_address") or record.get("clean_address", ""),
            id_type=record.get("id_type", ""),
            id_number=record.get("id_number", ""),
            operator=record.get("operator_or_source_category") or record.get("operator", ""),
            circle=record.get("circle", ""),
            activation_date=record.get("activation_date", ""),
            caf_number=record.get("caf_number", ""),
            source_file=record.get("source_file", ""),
        )

    raise HTTPException(status_code=404, detail="SDR profile not found")


@router.post("/sdr/batch", response_model=schemas.SDRBatchLookupResponse)
def lookup_sdr_batch(
    request: schemas.SDRBatchLookupRequest,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Batch SDR lookup for report enrichment across multiple districts/states."""
    cleaned = sorted(
        {
            normalize_mobile_number(num)
            for num in (request.numbers or [])
            if normalize_mobile_number(num)
        }
    )
    if not cleaned:
        return schemas.SDRBatchLookupResponse(records=[], count=0)

    found_map: dict[str, schemas.SDRProfileOut] = {}

    for start in range(0, len(cleaned), 1000):
        batch = cleaned[start : start + 1000]
        rows = (
            db.query(models.SDRSubscriber)
            .filter(models.SDRSubscriber.mobile_number.in_(batch))
            .all()
        )
        for row in rows:
            found_map[str(row.mobile_number)] = schemas.SDRProfileOut.model_validate(row)

    missing = [num for num in cleaned if num not in found_map]
    if missing:
        try:
            df = lookup_sdr_subscribers_cached(tuple(missing))
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    if str(row.get("sdr_found", "")).upper() != "YES":
                        continue
                    mob = str(row.get("lookup_mobile", "")).strip()
                    if mob and mob not in found_map:
                        found_map[mob] = schemas.SDRProfileOut(
                            mobile_number=mob,
                            subscriber_name=str(row.get("subscriber_name", "") or ""),
                            father_name=str(row.get("father_name", "") or ""),
                            address=str(row.get("subscriber_address", "") or ""),
                            id_type=str(row.get("id_type", "") or ""),
                            id_number=str(row.get("id_number", "") or ""),
                            operator=str(row.get("operator", "") or ""),
                            circle=str(row.get("circle", "") or ""),
                            activation_date=str(row.get("activation_date", "") or ""),
                            caf_number=str(row.get("caf_number", "") or ""),
                            source_file=str(row.get("source_file", "") or ""),
                        )
        except Exception:
            pass

    records = list(found_map.values())
    return schemas.SDRBatchLookupResponse(records=records, count=len(records))


@router.get("/cgi/{cgi_value}", response_model=schemas.CGIProfileOut)
def lookup_cgi(
    cgi_value: str,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    normalized = normalize_cgi(cgi_value) or cgi_value.strip()
    tower = (
        db.query(models.CGIAddress)
        .filter(models.CGIAddress.cgi.in_([normalized, cgi_value.strip()]))
        .first()
    )
    if tower:
        return tower

    local_result = lookup_cgi_profile(normalized)
    if local_result.get("found") and local_result.get("record"):
        record = local_result["record"]
        return schemas.CGIProfileOut(**record)

    raise HTTPException(status_code=404, detail="CGI record not found")


@router.post("/cgi/batch", response_model=schemas.CGIBatchLookupResponse)
def lookup_cgi_batch(
    request: schemas.CGIBatchLookupRequest,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Batch CGI lookup for report enrichment across multiple districts/states."""
    cleaned = sorted(
        {
            normalize_cgi(cgi)
            for cgi in (request.cgis or [])
            if normalize_cgi(cgi)
        }
    )
    if not cleaned:
        return schemas.CGIBatchLookupResponse(records=[], count=0)

    found_map: dict[str, schemas.CGIProfileOut] = {}

    for start in range(0, len(cleaned), 1000):
        batch = cleaned[start : start + 1000]
        rows = (
            db.query(models.CGIAddress)
            .filter(models.CGIAddress.cgi.in_(batch))
            .all()
        )
        for row in rows:
            found_map[str(row.cgi)] = schemas.CGIProfileOut.model_validate(row)

    missing = [cgi for cgi in cleaned if cgi not in found_map]
    if missing:
        try:
            df = _lookup_cgi_addresses_cached(tuple(missing))
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    key = str(row.get("cgi", "")).strip()
                    if key and key not in found_map:
                        row_dict = row.to_dict()
                        found_map[key] = schemas.CGIProfileOut(
                            cgi=key,
                            operator=str(row_dict.get("operator", "") or ""),
                            circle=str(row_dict.get("circle", "") or ""),
                            state=str(row_dict.get("state", "") or ""),
                            district=str(row_dict.get("district", "") or ""),
                            police_station=str(row_dict.get("police_station", "") or ""),
                            address=str(row_dict.get("address", "") or ""),
                            latitude=float(row_dict["latitude"]) if row_dict.get("latitude") is not None and str(row_dict.get("latitude")) not in {"", "nan", "<NA>"} else None,
                            longitude=float(row_dict["longitude"]) if row_dict.get("longitude") is not None and str(row_dict.get("longitude")) not in {"", "nan", "<NA>"} else None,
                            site_name=str(row_dict.get("site_name", "") or ""),
                            town=str(row_dict.get("town", "") or ""),
                            source_file=str(row_dict.get("source_file", "") or ""),
                        )
        except Exception:
            pass

    records = list(found_map.values())
    return schemas.CGIBatchLookupResponse(records=records, count=len(records))
