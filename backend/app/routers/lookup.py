"""SDR and CGI single + batch lookup endpoints for multi-user VPS deployment."""

from __future__ import annotations

import os
import sys
import pandas as pd
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from .. import models, schemas
from ..auth import oauth2_scheme
from ..database import get_db
from ..access_policy import current_account

from modules.database.cgi_repository import normalize_cgi
from modules.database.lookup_service import lookup_cgi_profile, lookup_sdr_profile
from modules.enrichment.cgi_address_enrichment import lookup_cgi_addresses
from modules.enrichment.sdr_subscriber_enrichment import (
    lookup_sdr_subscribers,
    normalize_mobile_number,
)

router = APIRouter(prefix="/api/lookup", tags=["Lookup"])


def _lookup_text(value):
    if pd.api.types.is_scalar(value) and pd.isna(value):
        return ""
    return str(value) if value is not None else ""


def _first_lookup_text(*values):
    return next((text for value in values if (text := _lookup_text(value))), "")


def _master_authoritative():
    return os.getenv("ETHICALARMOR_MASTER_AUTHORITATIVE", "").lower() in {"1", "true", "yes"}


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    return current_account(token, db)


@router.get("/sdr/{mobile_number}", response_model=schemas.SDRProfileOut)
def lookup_sdr(
    mobile_number: str,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    normalized = normalize_mobile_number(mobile_number) or mobile_number.strip()
    subscriber = None
    if not _master_authoritative():
        subscriber = (
            db.query(models.SDRSubscriber)
            .filter(models.SDRSubscriber.mobile_number.in_([normalized, mobile_number.strip()]))
            .first()
        )
    if subscriber:
        return subscriber

    local_result = lookup_sdr_profile(normalized)
    if local_result.get("status") == "DATABASE_ERROR":
        raise HTTPException(status_code=503, detail="Master database is unavailable or busy; retry after the current operation finishes")
    if local_result.get("found") and local_result.get("record"):
        record = local_result["record"]
        return schemas.SDRProfileOut(
            mobile_number=str(record.get("mobile_number", normalized)),
            subscriber_name=record.get("subscriber_name", ""),
            father_name=record.get("father_name", ""),
            address=_first_lookup_text(record.get("raw_address"), record.get("clean_address")),
            id_type=record.get("id_type", ""),
            id_number=record.get("id_number", ""),
            operator=_first_lookup_text(record.get("operator_or_source_category"), record.get("operator")),
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

    for start in range(0, 0 if _master_authoritative() else len(cleaned), 1000):
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
            df = lookup_sdr_subscribers(missing)
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    if str(row.get("sdr_found", "")).upper() != "YES":
                        continue
                    mob = str(row.get("lookup_mobile", "")).strip()
                    if mob and mob not in found_map:
                        found_map[mob] = schemas.SDRProfileOut(
                            mobile_number=mob,
                            subscriber_name=_lookup_text(row.get("subscriber_name", "")),
                            father_name=_lookup_text(row.get("father_name", "")),
                            address=_lookup_text(row.get("subscriber_address", "")),
                            id_type=_lookup_text(row.get("id_type", "")),
                            id_number=_lookup_text(row.get("id_number", "")),
                            operator=_lookup_text(row.get("operator", "")),
                            circle=_lookup_text(row.get("circle", "")),
                            activation_date=_lookup_text(row.get("activation_date", "")),
                            caf_number=_lookup_text(row.get("caf_number", "")),
                            source_file=_lookup_text(row.get("source_file", "")),
                        )
        except Exception as error:
            raise HTTPException(status_code=503, detail="Master database lookup failed; retry after checking database access") from error

    records = list(found_map.values())
    return schemas.SDRBatchLookupResponse(records=records, count=len(records))


@router.get("/cgi/{cgi_value}", response_model=schemas.CGIProfileOut)
def lookup_cgi(
    cgi_value: str,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    normalized = normalize_cgi(cgi_value) or cgi_value.strip()
    tower = None
    if not _master_authoritative():
        tower = (
            db.query(models.CGIAddress)
            .filter(models.CGIAddress.cgi.in_([normalized, cgi_value.strip()]))
            .first()
        )
    if tower:
        return tower

    local_result = lookup_cgi_profile(normalized)
    if local_result.get("status") == "DATABASE_ERROR":
        raise HTTPException(status_code=503, detail="Master database is unavailable or busy; retry after the current operation finishes")
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

    for start in range(0, 0 if _master_authoritative() else len(cleaned), 1000):
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
            df = lookup_cgi_addresses(missing)
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    key = str(row.get("cgi", "")).strip()
                    if key and key not in found_map:
                        row_dict = row.to_dict()
                        found_map[key] = schemas.CGIProfileOut(
                            cgi=key,
                            operator=_lookup_text(row_dict.get("operator", "")),
                            circle=_lookup_text(row_dict.get("circle", "")),
                            state=_lookup_text(row_dict.get("state", "")),
                            district=_lookup_text(row_dict.get("district", "")),
                            police_station=_lookup_text(row_dict.get("police_station", "")),
                            address=_lookup_text(row_dict.get("address", "")),
                            latitude=row_dict.get("latitude"),
                            longitude=row_dict.get("longitude"),
                            site_name=_lookup_text(row_dict.get("site_name", "")),
                            town=_lookup_text(row_dict.get("town", "")),
                            source_file=_lookup_text(row_dict.get("source_file", "")),
                        )
        except Exception as error:
            raise HTTPException(status_code=503, detail="Master database lookup failed; retry after checking database access") from error

    records = list(found_map.values())
    return schemas.CGIBatchLookupResponse(records=records, count=len(records))


