"""Data models for common investigation case management."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from modules.core.time_utils import DEFAULT_SOURCE_TIMEZONE, utc_now_iso

CASE_SCHEMA_VERSION = 2


@dataclass(slots=True)
class CaseMetadata:
    case_id: str
    case_name: str
    fir_number: str = ""
    incident_date: str = ""
    investigator: str = ""
    unit_name: str = ""
    incident_location: str = ""
    description: str = ""
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    schema_version: int = CASE_SCHEMA_VERSION
    source_timezone: str = DEFAULT_SOURCE_TIMEZONE

    def __post_init__(self) -> None:
        self.case_id = str(self.case_id).strip()
        self.case_name = str(self.case_name).strip()
        self.status = str(self.status or "active").strip().lower()
        self.source_timezone = (
            str(self.source_timezone).strip() or DEFAULT_SOURCE_TIMEZONE
        )
        try:
            self.schema_version = int(self.schema_version or CASE_SCHEMA_VERSION)
        except (TypeError, ValueError):
            self.schema_version = CASE_SCHEMA_VERSION

        if not self.case_id:
            raise ValueError("case_id required hai.")
        if not self.case_name:
            raise ValueError("case_name required hai.")
        if self.status not in {"active", "archived"}:
            raise ValueError(f"Invalid case status: {self.status}")
        if not self.created_at:
            self.created_at = utc_now_iso()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CaseMetadata":
        if not isinstance(value, dict):
            raise ValueError("Case metadata must be a JSON object.")

        required = ("case_id", "case_name")
        missing = [key for key in required if not str(value.get(key, "")).strip()]
        if missing:
            raise ValueError(f"Required case metadata missing: {', '.join(missing)}")

        allowed = {
            "case_id",
            "case_name",
            "fir_number",
            "incident_date",
            "investigator",
            "unit_name",
            "incident_location",
            "description",
            "status",
            "created_at",
            "updated_at",
            "schema_version",
            "source_timezone",
        }
        clean = {key: value.get(key, "") for key in allowed if key in value}
        clean.setdefault("schema_version", 1)
        clean.setdefault("source_timezone", DEFAULT_SOURCE_TIMEZONE)
        return cls(**clean)
