from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import re

import pandas as pd

from .cgi_repository import normalize_cgi


SUPPORTED_CGI_SUFFIXES = {".csv", ".txt", ".tsv", ".xlsx", ".xls", ".xlsb"}

CGI_OUTPUT_COLUMNS = [
    "cgi",
    "operator",
    "circle",
    "state",
    "district",
    "police_station",
    "address",
    "latitude",
    "longitude",
    "source_file",
    "site_name",
    "town",
    "landmark",
    "azimuth",
    "technology",
    "status",
    "status_change_date",
    "mcc_mnc",
    "lac",
    "cid",
    "tac_id",
    "site_id",
    "gnb_id",
    "cell_id",
]

CGI_KEY_ALIASES = [
    "cgi",
    "CGI",
    "CGI (Code in Order of CMCC/MNC/LAC/CI)",
    "CGI (MCC-MNC-CID)",
    "CGI with GCI (MCC-MNC-TAC-GCI)",
    "CGI with GCI\n(MCC-MNC-TAC-GCI)",
    "CI to GCI Conversion",
    "ECGI",
    "CELLA CGI",
    "Cell Global ID",
    "Cell Global Id",
    "Cell Global Identity",
]

FIELD_ALIASES = {
    "operator": ["operator", "TSP", "TSP NAME", "TSP Name", "Service provider", "Service Provider"],
    "circle": ["circle", "Circle", "Zone/ Circle", "Zone Circle", "Circle ID", "Circle Name", "SSA", "BA_NAME"],
    "state": ["state", "State"],
    "district": ["district", "District", "DIST", "LDCA"],
    "town": ["town", "Town", "Towns", "Town Name", "SDCA", "city"],
    "site_name": ["Site Name", "SITE NAME", "SITENAME", "Seg Name", "BTS NAME", "BTS_SYS_NAME", "BCF NAME", "SITE"],
    "police_station": ["Police Station", "PS", "ps", "thana"],
    "address": ["address", "Address", "Site Address", "BTS_AREA", "Tower Address", "location", "Location"],
    "landmark": ["Land Mark", "landmark", "land_mark"],
    "latitude": ["Latitude", "LATITUDE", "lat", "LAT"],
    "longitude": ["Longitude", "LONGITUDE", "long", "LONG", "lng"],
    "azimuth": ["Azimuth", "Azimuth angle", "Azimuth Angle", "Azimuth Deg"],
    "technology": ["Technology", "tech", "BTS TYPE", "BTS_TYPE", "SITE_TYPE"],
    "status": ["Status", "SITE STATUS", "Status (In-serv.ice/De-commissioned)", "Status (In-service/De-commissioned)"],
    "status_change_date": ["Status Change Date", "ON AIR DATE", "On Air Date"],
    "mcc_mnc": ["MCC-MNC", "mcc_mnc", "mcc mnc"],
    "lac": ["LAC", "lac", "Location(LAC)"],
    "cid": ["CID", "cid", "CI", "Cell Id Code"],
    "tac_id": ["TAC ID", "TAC ID (Decimal)", "TAC ID\n(Decimal)", "TAC"],
    "site_id": ["Site ID", "SiteID", "UniqueSiteID", "BTS_ID", "BTS ID", "SITE_ID", "LNBTS_OID", "LNCEL_OID"],
    "gnb_id": ["GNB ID", "GNB_ID"],
    "cell_id": ["Cell ID", "Updated Cell ID", "Lcell ID", "LCELL_ID", "CELL_ID"],
}

HEADER_ALIASES = []
for values in FIELD_ALIASES.values():
    HEADER_ALIASES.extend(values)
HEADER_ALIASES.extend(CGI_KEY_ALIASES)


def _norm(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"__dup\d+$", "", text)
    text = text.replace("\ufeff", "")
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    text = re.sub(r"_\d+$", "", text)
    return text


def _matches(value: object, aliases: Iterable[str]) -> bool:
    normal = _norm(value)
    return normal in {_norm(alias) for alias in aliases}


def _matching_columns(df: pd.DataFrame, aliases: Iterable[str]) -> List[str]:
    return [column for column in df.columns if _matches(column, aliases)]


def _first_column(df: pd.DataFrame, aliases: Iterable[str]) -> Optional[str]:
    matches = _matching_columns(df, aliases)
    return matches[0] if matches else None


def _clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "nat"}:
        return ""
    return text


def _clean_cgi(value) -> str:
    text = normalize_cgi(value)
    if not text:
        return ""

    text = str(text).strip().strip("'").strip('"')
    text = re.sub(r"\s+", "", text)

    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]

    if text.lower() in {"nan", "none", "null", "na", "n/a", "-", "--", "0"}:
        return ""

    return text.upper()


def _looks_like_cgi(value: str, source_column: str = "") -> bool:
    if not value:
        return False

    text = str(value).strip().upper()
    compact = re.sub(r"[\s_]+", "", text)

    if len(compact) < 6:
        return False

    if not re.search(r"\d", compact):
        return False

    if compact in {"COMMISSIONED", "DECOMMISSIONED", "ACTIVE", "INACTIVE", "INSERVICE"}:
        return False

    if re.fullmatch(r"\d{3}-\d{2,3}-[A-Z0-9]+-[A-Z0-9]+(?:-[A-Z0-9]+)?", compact):
        return True

    if re.fullmatch(r"[0-9A-F]{8,24}", compact) and compact.startswith(("404", "405")):
        return True

    if re.fullmatch(r"\d{6,20}", compact):
        if len(compact) == 10 and compact[0] in {"6", "7", "8", "9"}:
            return False
        return True

    return False


def _dedupe_columns(columns: Iterable[object]) -> List[str]:
    seen: Dict[str, int] = {}
    output: List[str] = []

    for column in columns:
        name = str(column).strip().replace("\ufeff", "")
        if not name or name.lower().startswith("unnamed"):
            name = "unnamed"

        count = seen.get(name, 0)
        output.append(name if count == 0 else f"{name}__dup{count}")
        seen[name] = count + 1

    return output


def _header_score(values: Iterable[object]) -> int:
    score = 0

    for value in values:
        text = _clean_text(value)
        if not text:
            continue

        normal = _norm(text)

        if _matches(text, CGI_KEY_ALIASES):
            score += 100

        if _matches(text, HEADER_ALIASES):
            score += 10

        if "cgi" in normal or "ecgi" in normal:
            score += 25

        if any(key in normal for key in ["latitude", "longitude", "address", "district", "circle", "site", "azimuth", "technology", "lac", "cid", "tac", "gnb"]):
            score += 5

    return score


def _excel_engine(path: Path):
    return "pyxlsb" if path.suffix.lower() == ".xlsb" else None


def _infer_operator(source_file: str) -> str:
    text = source_file.lower()

    if "airtel" in text or "bharti" in text:
        return "AIRTEL"
    if "jio" in text or "rjil" in text or "reliance" in text:
        return "RJIL"
    if "vodafone" in text or "voda" in text or "vi" in text:
        return "VODAFONE IDEA"
    if "bsnl" in text:
        return "BSNL"

    return ""


def _series(df: pd.DataFrame, aliases: Iterable[str], default: str = "") -> pd.Series:
    column = _first_column(df, aliases)
    if column is None:
        return pd.Series([default] * len(df), index=df.index)
    return df[column].map(_clean_text)


def _combine_mcc_mnc(df: pd.DataFrame) -> pd.Series:
    mcc = _first_column(df, ["MCC", "MCC-Mobile Country Code"])
    mnc = _first_column(df, ["MNC", "MNC-Mobile Network Code"])

    if mcc and mnc:
        return (
            df[mcc].map(_clean_text).str.replace(r"\.0$", "", regex=True)
            + "-"
            + df[mnc].map(_clean_text).str.replace(r"\.0$", "", regex=True)
        )

    return _series(df, FIELD_ALIASES["mcc_mnc"])


def prepare_standard_cgi_dataframe(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    df = df.copy()
    df.columns = _dedupe_columns(df.columns)

    key_columns = _matching_columns(df, CGI_KEY_ALIASES)

    if not key_columns:
        return pd.DataFrame(columns=CGI_OUTPUT_COLUMNS)

    base = pd.DataFrame(index=df.index)

    for output_column in [
        "operator", "circle", "state", "district", "police_station", "address",
        "site_name", "town", "landmark", "azimuth", "technology", "status",
        "status_change_date", "lac", "cid", "tac_id", "site_id", "gnb_id", "cell_id",
    ]:
        base[output_column] = _series(df, FIELD_ALIASES.get(output_column, []))

    inferred_operator = _infer_operator(source_file)
    if inferred_operator:
        base["operator"] = base["operator"].where(base["operator"].astype(str).str.strip().ne(""), inferred_operator)

    base["mcc_mnc"] = _combine_mcc_mnc(df)
    base["latitude"] = pd.to_numeric(_series(df, FIELD_ALIASES["latitude"]), errors="coerce")
    base["longitude"] = pd.to_numeric(_series(df, FIELD_ALIASES["longitude"]), errors="coerce")
    base["source_file"] = source_file

    parts = []

    for key_column in key_columns:
        part = base.copy()
        part["cgi"] = df[key_column].map(_clean_cgi)
        part = part[part["cgi"].map(lambda value: _looks_like_cgi(value, key_column))].copy()
        if not part.empty:
            parts.append(part)

    if not parts:
        return pd.DataFrame(columns=CGI_OUTPUT_COLUMNS)

    output = pd.concat(parts, ignore_index=True)
    output["_quality_score"] = (
        output["address"].astype(str).str.len().clip(upper=100)
        + output["latitude"].notna().astype(int) * 20
        + output["longitude"].notna().astype(int) * 20
        + output["district"].astype(str).str.len().clip(upper=20)
    )

    output = output.sort_values("_quality_score").drop_duplicates("cgi", keep="last")
    output = output.drop(columns=["_quality_score"])

    return output[CGI_OUTPUT_COLUMNS]


def _looks_like_column_headers(values: Iterable[object]) -> bool:
    names = [_norm(value) for value in values if _clean_text(value)]
    return len(names) >= 8 and all(name.startswith("column") for name in names[:8])


def _detect_positional_layout(df: pd.DataFrame):
    """
    Detect CGI, latitude and longitude columns in Column1/Column2... sheets.

    Normal Jio positional layout:
    Column1  = CGI
    Column2  = Operator
    Column3  = Circle
    Column4  = Town
    Column5  = Site Name
    Column6  = Site Address
    Column7  = Landmark
    Column8  = Latitude
    Column9  = Longitude
    Column10 = Azimuth
    Column11 = Status
    Column12 = Status Change Date

    Some state files contain extra columns or shifted columns, so this
    function checks sample rows and chooses the best likely columns.
    """
    columns = list(df.columns)
    sample = df.head(200).copy()

    best_cgi_col = None
    best_cgi_score = -1

    for column in columns:
        score = sample[column].map(lambda value: _looks_like_cgi(_clean_cgi(value), str(column))).sum()

        if score > best_cgi_score:
            best_cgi_score = score
            best_cgi_col = column

    numeric_columns = []

    for column in columns:
        values = pd.to_numeric(sample[column].map(_clean_text), errors="coerce")
        valid_count = values.notna().sum()

        if valid_count <= 0:
            continue

        min_value = values.min()
        max_value = values.max()

        numeric_columns.append((column, valid_count, min_value, max_value))

    lat_candidates = [
        item for item in numeric_columns
        if -90 <= item[2] <= 90 and -90 <= item[3] <= 90
    ]

    lon_candidates = [
        item for item in numeric_columns
        if -180 <= item[2] <= 180 and -180 <= item[3] <= 180
    ]

    latitude_col = None
    longitude_col = None

    for lat_item in lat_candidates:
        lat_col = lat_item[0]
        lat_index = columns.index(lat_col)

        for lon_item in lon_candidates:
            lon_col = lon_item[0]
            lon_index = columns.index(lon_col)

            if lon_index == lat_index + 1:
                latitude_col = lat_col
                longitude_col = lon_col
                break

        if latitude_col and longitude_col:
            break

    return {
        "cgi": best_cgi_col if best_cgi_score > 0 else None,
        "latitude": latitude_col,
        "longitude": longitude_col,
    }


def _value_by_index(values: List[str], index: int) -> str:
    return values[index] if index < len(values) else ""


def _prepare_positional_dataframe(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    df = df.copy()
    df.columns = _dedupe_columns(df.columns)

    layout = _detect_positional_layout(df)

    cgi_column = layout.get("cgi")
    latitude_column = layout.get("latitude")
    longitude_column = layout.get("longitude")

    rows = []

    for _, row in df.iterrows():
        values = [_clean_text(value) for value in row.tolist()]

        # If a row is actually caret-packed, handle it here also.
        caret_parts = _split_caret_row(values)
        if caret_parts:
            if _header_score(caret_parts) >= 80:
                continue

            temp = pd.DataFrame(
                [caret_parts],
                columns=[
                    "CGI (Code in Order of CMCC/MNC/LAC/CI)",
                    "Service provider",
                    "Zone/ Circle",
                    "Town",
                    "Site Name",
                    "Site Address",
                    "Land Mark",
                    "Latitude",
                    "Longitude",
                    "Azimuth angle",
                    "Status (In-serv.ice/De-commissioned)",
                    "Status Change Date",
                ][:len(caret_parts)]
            )
            prepared = prepare_standard_cgi_dataframe(temp, source_file)
            if prepared is not None and not prepared.empty:
                rows.extend(prepared.to_dict("records"))
            continue

        if cgi_column:
            cgi = _clean_cgi(row.get(cgi_column, ""))
        else:
            cgi = _clean_cgi(_value_by_index(values, 0))

        if not _looks_like_cgi(cgi, str(cgi_column or "Column1")):
            continue

        if latitude_column and longitude_column:
            latitude = pd.to_numeric(_clean_text(row.get(latitude_column, "")), errors="coerce")
            longitude = pd.to_numeric(_clean_text(row.get(longitude_column, "")), errors="coerce")
        else:
            latitude = pd.to_numeric(_value_by_index(values, 7), errors="coerce")
            longitude = pd.to_numeric(_value_by_index(values, 8), errors="coerce")

        rows.append(
            {
                "cgi": cgi,
                "operator": _value_by_index(values, 1),
                "circle": _value_by_index(values, 2),
                "state": "",
                "district": "",
                "police_station": "",
                "town": _value_by_index(values, 3),
                "site_name": _value_by_index(values, 4),
                "address": _value_by_index(values, 5),
                "landmark": _value_by_index(values, 6),
                "latitude": latitude,
                "longitude": longitude,
                "azimuth": _value_by_index(values, 9),
                "technology": "",
                "status": _value_by_index(values, 10),
                "status_change_date": _value_by_index(values, 11),
                "mcc_mnc": "",
                "lac": "",
                "cid": "",
                "tac_id": "",
                "site_id": "",
                "gnb_id": "",
                "cell_id": "",
                "source_file": source_file,
            }
        )

    if not rows:
        return pd.DataFrame(columns=CGI_OUTPUT_COLUMNS)

    return pd.DataFrame(rows)[CGI_OUTPUT_COLUMNS].drop_duplicates("cgi", keep="last")


def _split_caret_row(values: Iterable[object]) -> List[str]:
    cells = [_clean_text(value) for value in values if _clean_text(value)]
    if not cells:
        return []

    joined = " ".join(cells)
    if "^" not in joined:
        return []

    return [part.strip() for part in joined.split("^")]


def _prepare_caret_dataframe(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    header = None
    records = []

    for _, row in df.iterrows():
        parts = _split_caret_row(row.tolist())
        if not parts:
            continue

        if header is None:
            if _header_score(parts) >= 80:
                header = _dedupe_columns(parts)
            continue

        if _header_score(parts) >= 80:
            continue

        if len(parts) < len(header):
            parts = parts + [""] * (len(header) - len(parts))

        records.append({header[index]: parts[index] if index < len(parts) else "" for index in range(len(header))})

    if not records:
        return pd.DataFrame(columns=CGI_OUTPUT_COLUMNS)

    return prepare_standard_cgi_dataframe(pd.DataFrame(records), source_file)


def _detect_standard_header_row(preview: pd.DataFrame):
    best_score = 0
    best_row = None

    for pos in range(len(preview)):
        row_values = preview.iloc[pos].tolist()
        caret_parts = _split_caret_row(row_values)
        values_for_score = caret_parts if caret_parts else row_values

        score = _header_score(values_for_score)

        if score > best_score:
            best_score = score
            best_row = int(preview.index[pos])

    return best_score, best_row


def inspect_cgi_master_file(file_path) -> List[Dict[str, Any]]:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix not in SUPPORTED_CGI_SUFFIXES:
        raise ValueError(f"Unsupported CGI file type: {path}")

    if suffix not in {".xlsx", ".xls", ".xlsb"}:
        return [{"sheet": "", "status": "TEXT_FILE", "mode": "text", "header_row": None, "score": None, "cgi_columns": []}]

    excel = pd.ExcelFile(path, engine=_excel_engine(path))
    results = []

    for sheet in excel.sheet_names:
        try:
            preview = pd.read_excel(excel, sheet_name=sheet, header=None, dtype=str, nrows=100).dropna(how="all")
        except Exception as exc:
            results.append({"sheet": sheet, "status": "FAILED", "mode": "", "header_row": None, "score": 0, "cgi_columns": [], "error": str(exc)})
            continue

        if preview.empty:
            results.append({"sheet": sheet, "status": "SKIPPED_EMPTY", "mode": "", "header_row": None, "score": 0, "cgi_columns": []})
            continue

        first_row = preview.iloc[0].tolist()

        caret_header_row = None
        for position in range(len(preview)):
            row_values = preview.iloc[position].tolist()
            caret_parts = _split_caret_row(row_values)

            if caret_parts and _header_score(caret_parts) >= 80:
                caret_header_row = int(preview.index[position])
                break

        if caret_header_row is not None:
            results.append({
                "sheet": sheet,
                "status": "OK",
                "mode": "caret_packed",
                "header_row": caret_header_row + 1,
                "score": 100,
                "cgi_columns": ["packed ^ header"],
            })
            continue

        if _looks_like_column_headers(first_row):
            results.append({
                "sheet": sheet,
                "status": "OK",
                "mode": "positional",
                "header_row": 1,
                "score": 100,
                "cgi_columns": ["Column1"],
            })
            continue

        score, header_row = _detect_standard_header_row(preview)

        if header_row is None or score < 80:
            results.append({"sheet": sheet, "status": "SKIPPED_NO_HEADER", "mode": "", "header_row": None, "score": score, "cgi_columns": []})
            continue

        header_values = [value for value in preview.loc[header_row].tolist() if _clean_text(value)]
        cgi_columns = [value for value in _dedupe_columns(header_values) if _matches(value, CGI_KEY_ALIASES)]

        results.append(
            {
                "sheet": sheet,
                "status": "OK" if cgi_columns else "NO_CGI_COLUMN",
                "mode": "standard",
                "header_row": header_row + 1,
                "score": score,
                "cgi_columns": cgi_columns,
            }
        )

    return results


def _read_excel_cgi_file(path: Path) -> List[pd.DataFrame]:
    excel = pd.ExcelFile(path, engine=_excel_engine(path))
    frames = []

    for info in inspect_cgi_master_file(path):
        if info.get("status") != "OK":
            continue

        sheet = info["sheet"]
        mode = info["mode"]
        source = f"{path.name}::{sheet}"

        if mode == "caret_packed":
            raw = pd.read_excel(excel, sheet_name=sheet, header=None, dtype=str).dropna(how="all")
            prepared = _prepare_caret_dataframe(raw, source)

        elif mode == "positional":
            raw = pd.read_excel(excel, sheet_name=sheet, header=0, dtype=str).dropna(how="all").dropna(axis=1, how="all")
            prepared = _prepare_positional_dataframe(raw, source)

        else:
            header_row = int(info["header_row"]) - 1
            raw = pd.read_excel(excel, sheet_name=sheet, header=header_row, dtype=str).dropna(how="all").dropna(axis=1, how="all")
            raw.columns = _dedupe_columns(raw.columns)
            prepared = prepare_standard_cgi_dataframe(raw, source)

        if prepared is not None and not prepared.empty:
            frames.append(prepared)

    return frames


def _read_text_cgi_file(path: Path) -> List[pd.DataFrame]:
    best_line = 0
    best_score = 0
    best_sep = ","

    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        for line_no, line in enumerate(handle):
            if line_no > 100:
                break

            for sep in ["|", "\t", ",", ";", "^"]:
                values = line.rstrip("\n").split(sep)
                score = _header_score(values)
                if score > best_score:
                    best_score = score
                    best_line = line_no
                    best_sep = sep

    raw = pd.read_csv(path, header=best_line, sep=best_sep, dtype=str, engine="python", encoding_errors="ignore")
    raw = raw.dropna(how="all").dropna(axis=1, how="all")
    raw.columns = _dedupe_columns(raw.columns)

    prepared = prepare_standard_cgi_dataframe(raw, path.name)
    return [prepared] if prepared is not None and not prepared.empty else []


def read_cgi_master_file(file_path) -> List[pd.DataFrame]:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix not in SUPPORTED_CGI_SUFFIXES:
        raise ValueError(f"Unsupported CGI file type: {path}")

    if suffix in {".xlsx", ".xls", ".xlsb"}:
        return _read_excel_cgi_file(path)

    return _read_text_cgi_file(path)
