"""Advanced SDR/CGI master data import into PostgreSQL and local DuckDB."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from .. import models
from ..auth import InvalidTokenError, decode_token, oauth2_scheme
from ..database import get_db

from modules.database.cgi_master_reader import read_cgi_master_file
from modules.database.lookup_service import clear_all_lookup_caches
from modules.database.master_import_service import (
    detect_master_data_type,
    import_master_data_file,
)
from modules.database.master_importer import _prepare_sdr_dataframe, _read_input_file

router = APIRouter(prefix="/api/import", tags=["Import"])


def _upsert_sdr_postgres(db: Session, prepared: pd.DataFrame, filename: str) -> tuple[int, int]:
    if prepared is None or prepared.empty:
        return 0, 0

    deduped = prepared.drop_duplicates(subset=["mobile_number"], keep="last")
    numbers = [
        str(val).strip()
        for val in deduped["mobile_number"].dropna().tolist()
        if str(val).strip()
    ]
    existing_map = {}
    for start in range(0, len(numbers), 1000):
        batch = numbers[start : start + 1000]
        rows = (
            db.query(models.SDRSubscriber)
            .filter(models.SDRSubscriber.mobile_number.in_(batch))
            .all()
        )
        for obj in rows:
            existing_map[obj.mobile_number] = obj

    inserted = 0
    updated = 0
    for _, row in deduped.iterrows():
        mobile = str(row.get("mobile_number", "")).strip()
        if not mobile:
            continue
        payload = {
            "subscriber_name": str(row.get("subscriber_name", "")).strip(),
            "father_name": str(row.get("father_name", "")).strip(),
            "address": str(row.get("address", "")).strip(),
            "id_type": str(row.get("id_type", "")).strip(),
            "id_number": str(row.get("id_number", "")).strip(),
            "operator": str(row.get("operator", "")).strip(),
            "circle": str(row.get("circle", "")).strip(),
            "activation_date": str(row.get("activation_date", "")).strip(),
            "caf_number": str(row.get("caf_number", "")).strip(),
            "source_file": filename,
        }
        if mobile in existing_map:
            target = existing_map[mobile]
            for key, value in payload.items():
                setattr(target, key, value)
            updated += 1
        else:
            db.add(models.SDRSubscriber(mobile_number=mobile, **payload))
            inserted += 1

    db.commit()
    return inserted, updated


def _upsert_cgi_postgres(db: Session, combined: pd.DataFrame, filename: str) -> tuple[int, int]:
    if combined is None or combined.empty:
        return 0, 0

    deduped = combined.drop_duplicates(subset=["cgi"], keep="last")
    cgis = [
        str(val).strip()
        for val in deduped["cgi"].dropna().tolist()
        if str(val).strip()
    ]
    existing_map = {}
    for start in range(0, len(cgis), 1000):
        batch = cgis[start : start + 1000]
        rows = (
            db.query(models.CGIAddress)
            .filter(models.CGIAddress.cgi.in_(batch))
            .all()
        )
        for obj in rows:
            existing_map[obj.cgi] = obj

    inserted = 0
    updated = 0
    for _, row in deduped.iterrows():
        cgi_val = str(row.get("cgi", "")).strip()
        if not cgi_val:
            continue
        payload = {
            "operator": str(row.get("operator", "")).strip(),
            "circle": str(row.get("circle", "")).strip(),
            "state": str(row.get("state", "")).strip(),
            "district": str(row.get("district", "")).strip(),
            "police_station": str(row.get("police_station", "")).strip(),
            "address": str(row.get("address", "")).strip(),
            "latitude": float(row.get("latitude")) if pd.notna(row.get("latitude")) else None,
            "longitude": float(row.get("longitude")) if pd.notna(row.get("longitude")) else None,
            "site_name": str(row.get("site_name", "")).strip(),
            "town": str(row.get("town", "")).strip(),
            "landmark": str(row.get("landmark", "")).strip(),
            "azimuth": str(row.get("azimuth", "")).strip(),
            "technology": str(row.get("technology", "")).strip(),
            "status": str(row.get("status", "")).strip(),
            "status_change_date": str(row.get("status_change_date", "")).strip(),
            "mcc_mnc": str(row.get("mcc_mnc", "")).strip(),
            "lac": str(row.get("lac", "")).strip(),
            "cid": str(row.get("cid", "")).strip(),
            "tac_id": str(row.get("tac_id", "")).strip(),
            "site_id": str(row.get("site_id", "")).strip(),
            "gnb_id": str(row.get("gnb_id", "")).strip(),
            "cell_id": str(row.get("cell_id", "")).strip(),
            "source_file": filename,
        }
        if cgi_val in existing_map:
            target = existing_map[cgi_val]
            for key, value in payload.items():
                setattr(target, key, value)
            updated += 1
        else:
            db.add(models.CGIAddress(cgi=cgi_val, **payload))
            inserted += 1

    db.commit()
    return inserted, updated


@router.post("/master")
async def import_master_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    """Upload and import SDR or CGI master data file into PostgreSQL and DuckDB."""
    try:
        decode_token(token)
    except InvalidTokenError as error:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        ) from error

    content = await file.read()
    original_name = file.filename or "master_import.csv"
    suffix = Path(original_name.lower()).suffix

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        detection = detect_master_data_type(tmp_path)
        detected_type = detection.get("import_type")

        if detected_type == "SDR":
            raw_df = _read_input_file(tmp_path)
            prepared = _prepare_sdr_dataframe(raw_df, original_name)
            inserted, updated = _upsert_sdr_postgres(db, prepared, original_name)
            try:
                import_master_data_file(tmp_path, create_backup=False)
                clear_all_lookup_caches()
            except Exception:
                pass
            total = len(prepared)
            return {
                "status": "SUCCESS",
                "type": "SDR",
                "import_type": "SDR",
                "target_table": "sdr_subscribers",
                "source_file": original_name,
                "rows": total,
                "rows_read": len(raw_df),
                "valid_rows": total,
                "inserted_rows": inserted,
                "updated_rows": updated,
                "message": "Master SDR data imported successfully.",
            }

        elif detected_type == "CGI":
            prepared_frames = read_cgi_master_file(tmp_path)
            combined = (
                pd.concat(prepared_frames, ignore_index=True)
                if prepared_frames
                else pd.DataFrame()
            )
            inserted, updated = _upsert_cgi_postgres(db, combined, original_name)
            try:
                import_master_data_file(tmp_path, create_backup=False)
                clear_all_lookup_caches()
            except Exception:
                pass
            total = len(combined)
            return {
                "status": "SUCCESS",
                "type": "CGI",
                "import_type": "CGI",
                "target_table": "cgi_addresses",
                "source_file": original_name,
                "rows": total,
                "rows_read": total,
                "valid_rows": total,
                "inserted_rows": inserted,
                "updated_rows": updated,
                "message": "Master CGI data imported successfully.",
            }

        else:
            raise HTTPException(
                status_code=400,
                detail="Could not detect SDR or CGI columns",
            )

    except HTTPException:
        raise
    except Exception as error:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Parsing failed: {error}",
        ) from error
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
