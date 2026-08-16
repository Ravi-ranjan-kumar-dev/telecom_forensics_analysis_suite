"""Path-boundary tests for scalable case staging."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.cases.repository import InvalidCaseError
from modules.core.paths import ACTIVE_CASES_DIR
from modules.staging import scalable_store


def test_case_staging_root_uses_canonical_active_case_directory() -> None:
    result = scalable_store.case_staging_root(
        "case-001",
        "tower_cdr",
    )

    assert result == (
        ACTIVE_CASES_DIR
        / "CASE-001"
        / "staging"
        / "tower_cdr"
    ).resolve()


@pytest.mark.parametrize(
    "case_id",
    [
        "../../outside",
        "/tmp/outside",
        r"..\..\outside",
    ],
)
def test_case_staging_root_cannot_escape_active_cases(
    case_id: str,
) -> None:
    result = scalable_store.case_staging_root(
        case_id,
        "tower_cdr",
    )

    result.relative_to(
        ACTIVE_CASES_DIR.resolve()
    )


@pytest.mark.parametrize(
    "case_id",
    [
        "",
        ".",
        "..",
        "///",
    ],
)
def test_case_staging_root_rejects_empty_invalid_case_ids(
    case_id: str,
) -> None:
    with pytest.raises(InvalidCaseError):
        scalable_store.case_staging_root(
            case_id,
            "tower_cdr",
        )


def test_case_staging_root_rejects_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_cases = tmp_path / "cases" / "active"
    outside = tmp_path / "outside"

    active_cases.mkdir(parents=True)
    outside.mkdir()

    (active_cases / "CASE-001").symlink_to(
        outside,
        target_is_directory=True,
    )

    monkeypatch.setattr(
        scalable_store,
        "ACTIVE_CASES_DIR",
        active_cases,
    )

    with pytest.raises(InvalidCaseError):
        scalable_store.case_staging_root(
            "CASE-001",
            "tower_cdr",
        )
