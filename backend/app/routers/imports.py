# backend/app/routers/imports.py
"""Advanced SDR/CGI master data import into PostgreSQL."""

import sys
import os
import tempfile
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import pandas as pd

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ..database import get_db
from ..auth import oauth2_scheme, decode_token
from .. import models

from modules.database.master_import_service import detect_master_data_type
from modules.database.master_importer import _read_input_file, _prepare_sdr_dataframe
from modules.database.cgi_master_reader import read_cgi_master_file

router = APIRouter(prefix="/api/import", tags=["Import"])


@router.post("/master")
async def import_master_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    """Upload and import SDR or CGI master data file using advanced parsers."""
    decode_token(token)

    content = await file.read()
    filename = file.filename.lower()

    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        detection = detect_master_data_type(tmp_path)
        detected_type = detection.get("import_type")

        if detected_type == "SDR":
            raw_df = _read_input_file(tmp_path)
            prepared = _prepare_sdr_dataframe(raw_df, file.filename)

            for _, row in prepared.iterrows():
                subscriber = models.SDRSubscriber(
                    mobile_number=str(row.get("mobile_number", "")).strip(),
                    subscriber_name=str(row.get("subscriber_name", "")).strip(),
                    father_name=str(row.get("father_name", "")).strip(),
                    address=str(row.get("address", "")).strip(),
                    id_type=str(row.get("id_type", "")).strip(),
                    id_number=str(row.get("id_number", "")).strip(),
                    operator=str(row.get("operator", "")).strip(),
                    circle=str(row.get("circle", "")).strip(),
                    activation_date=str(row.get("activation_date", "")).strip(),
                    caf_number=str(row.get("caf_number", "")).strip(),
                    source_file=file.filename,
                )
                db.add(subscriber)
            db.commit()
            return {"status": "success", "type": "SDR", "rows": len(prepared)}

        elif detected_type == "CGI":
            prepared_frames = read_cgi_master_file(tmp_path)
            combined = pd.concat(prepared_frames, ignore_index=True) if prepared_frames else pd.DataFrame()

            for _, row in combined.iterrows():
                tower = models.CGIAddress(
                    cgi=str(row.get("cgi", "")).strip(),
                    operator=str(row.get("operator", "")).strip(),
                    circle=str(row.get("circle", "")).strip(),
                    state=str(row.get("state", "")).strip(),
                    district=str(row.get("district", "")).strip(),
                    police_station=str(row.get("police_station", "")).strip(),
                    address=str(row.get("address", "")).strip(),
                    latitude=float(row.get("latitude")) if pd.notna(row.get("latitude")) else None,
                    longitude=float(row.get("longitude")) if pd.notna(row.get("longitude")) else None,
                    site_name=str(row.get("site_name", "")).strip(),
                    town=str(row.get("town", "")).strip(),
                    landmark=str(row.get("landmark", "")).strip(),
                    azimuth=str(row.get("azimuth", "")).strip(),
                    technology=str(row.get("technology", "")).strip(),
                    status=str(row.get("status", "")).strip(),
                    status_change_date=str(row.get("status_change_date", "")).strip(),
                    mcc_mnc=str(row.get("mcc_mnc", "")).strip(),
                    lac=str(row.get("lac", "")).strip(),
                    cid=str(row.get("cid", "")).strip(),
                    tac_id=str(row.get("tac_id", "")).strip(),
                    site_id=str(row.get("site_id", "")).strip(),
                    gnb_id=str(row.get("gnb_id", "")).strip(),
                    cell_id=str(row.get("cell_id", "")).strip(),
                    source_file=file.filename,
                )
                db.add(tower)
            db.commit()
            return {"status": "success", "type": "CGI", "rows": len(combined)}

        else:
            raise HTTPException(status_code=400, detail="Could not detect SDR or CGI columns")

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parsing failed: {str(e)}")
    finally:
        os.unlink(tmp_path)