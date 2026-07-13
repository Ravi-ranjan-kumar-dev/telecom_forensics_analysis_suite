from __future__ import annotations

import json
from pathlib import Path


def test_case_models_import():
    from modules.cases.models import CaseMetadata

    case = CaseMetadata(
        case_id="TEST-001",
        case_name="Test Case",
    )

    assert case.case_id == "TEST-001"
    assert case.status == "active"


def test_case_id_normalization():
    from modules.cases.repository import normalize_case_id

    assert normalize_case_id("stf 2026 001") == "STF-2026-001"
