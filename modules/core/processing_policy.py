#scalable/normal decision logic


from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from modules.core.file_inventory import FileInventory


AnalysisType = Literal[
    "multiple_cdr",
    "tower_cdr",
    "tower_gprs",
    "tower_ipdr",
    "multiple_ipdr",
    "unknown",
]

ProcessingMode = Literal[
    "NORMAL",
    "SCALABLE",
]

PerformanceProfile = Literal[
    "normal",
    "safe_laptop",
    "balanced",
    "workstation",
]


@dataclass(frozen=True)
class ProcessingPolicy:
    analysis_type: AnalysisType
    mode: ProcessingMode
    profile: PerformanceProfile
    use_staging: bool
    use_duckdb: bool
    chunk_size: int | None
    workers: int
    console_row_limit: int
    excel_preview_rows: int
    max_excel_rows_per_sheet: int
    should_generate_full_excel: bool
    should_print_large_tables: bool
    reasons: list[str]
    warnings: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


PROFILE_SETTINGS: dict[PerformanceProfile, dict[str, int | bool | None]] = {
    "normal": {
        "chunk_size": None,
        "workers": 1,
        "console_row_limit": 20,
        "excel_preview_rows": 10000,
        "max_excel_rows_per_sheet": 200000,
        "should_generate_full_excel": True,
        "should_print_large_tables": True,
    },
    "safe_laptop": {
        "chunk_size": 50000,
        "workers": 1,
        "console_row_limit": 10,
        "excel_preview_rows": 5000,
        "max_excel_rows_per_sheet": 50000,
        "should_generate_full_excel": False,
        "should_print_large_tables": False,
    },
    "balanced": {
        "chunk_size": 100000,
        "workers": 2,
        "console_row_limit": 20,
        "excel_preview_rows": 10000,
        "max_excel_rows_per_sheet": 100000,
        "should_generate_full_excel": False,
        "should_print_large_tables": False,
    },
    "workstation": {
        "chunk_size": 250000,
        "workers": 4,
        "console_row_limit": 50,
        "excel_preview_rows": 25000,
        "max_excel_rows_per_sheet": 250000,
        "should_generate_full_excel": False,
        "should_print_large_tables": False,
    },
}


ANALYSIS_THRESHOLDS: dict[AnalysisType, dict[str, int | float]] = {
    "multiple_cdr": {
        "file_count": 10,
        "total_size_mb": 150,
        "estimated_rows": 200000,
    },
    "tower_cdr": {
        "file_count": 5,
        "total_size_mb": 150,
        "estimated_rows": 200000,
    },
    "tower_gprs": {
        "file_count": 10,
        "total_size_mb": 100,
        "estimated_rows": 150000,
    },
    "tower_ipdr": {
        "file_count": 5,
        "total_size_mb": 100,
        "estimated_rows": 300000,
    },
    "multiple_ipdr": {
        "file_count": 20,
        "total_size_mb": 150,
        "estimated_rows": 200000,
    },
    "unknown": {
        "file_count": 10,
        "total_size_mb": 150,
        "estimated_rows": 200000,
    },
}


def _get_thresholds(
    analysis_type: AnalysisType,
) -> dict[str, int | float]:
    return ANALYSIS_THRESHOLDS.get(
        analysis_type,
        ANALYSIS_THRESHOLDS["unknown"],
    )


def _large_data_reasons(
    inventory: FileInventory,
    analysis_type: AnalysisType,
) -> list[str]:
    thresholds = _get_thresholds(analysis_type)
    reasons: list[str] = []

    if inventory.supported_file_count > int(thresholds["file_count"]):
        reasons.append(
            "supported_file_count "
            f"{inventory.supported_file_count} > "
            f"{thresholds['file_count']}"
        )

    if inventory.total_size_mb > float(thresholds["total_size_mb"]):
        reasons.append(
            "total_size_mb "
            f"{inventory.total_size_mb:.3f} > "
            f"{thresholds['total_size_mb']}"
        )

    if (
        inventory.estimated_rows is not None
        and inventory.estimated_rows > int(thresholds["estimated_rows"])
    ):
        reasons.append(
            "estimated_rows "
            f"{inventory.estimated_rows} > "
            f"{thresholds['estimated_rows']}"
        )

    if analysis_type == "tower_ipdr" and inventory.supported_file_count >= 1:
        reasons.append(
            "tower_ipdr is treated as heavy by default"
        )

    return reasons


def _select_profile(
    *,
    mode: ProcessingMode,
    preferred_profile: PerformanceProfile | None,
) -> PerformanceProfile:
    if mode == "NORMAL":
        return "normal"

    if preferred_profile in {
        "safe_laptop",
        "balanced",
        "workstation",
    }:
        return preferred_profile

    return "safe_laptop"


def decide_processing_policy(
    inventory: FileInventory,
    *,
    analysis_type: AnalysisType = "unknown",
    preferred_profile: PerformanceProfile | None = None,
    force_scalable: bool = False,
    force_normal: bool = False,
) -> ProcessingPolicy:
    """Decide normal vs scalable processing mode.

    This function does not run analysis. It only gives a safe processing
    decision based on file count, size and estimated rows.
    """

    reasons = _large_data_reasons(
        inventory,
        analysis_type,
    )

    warnings: list[str] = []

    if inventory.supported_file_count == 0:
        warnings.append(
            "No supported input files found."
        )

    if inventory.unsupported_file_count > 0:
        warnings.append(
            f"{inventory.unsupported_file_count} unsupported file(s) found."
        )

    should_use_scalable = bool(reasons)

    if force_scalable:
        should_use_scalable = True
        reasons.append("force_scalable=True")

    if force_normal:
        should_use_scalable = False
        warnings.append(
            "force_normal=True used. Large dataset safeguards are bypassed."
        )

    mode: ProcessingMode = (
        "SCALABLE"
        if should_use_scalable
        else "NORMAL"
    )

    profile = _select_profile(
        mode=mode,
        preferred_profile=preferred_profile,
    )

    settings = PROFILE_SETTINGS[profile]

    use_staging = mode == "SCALABLE"
    use_duckdb = mode == "SCALABLE"

    return ProcessingPolicy(
        analysis_type=analysis_type,
        mode=mode,
        profile=profile,
        use_staging=use_staging,
        use_duckdb=use_duckdb,
        chunk_size=settings["chunk_size"],  # type: ignore[arg-type]
        workers=int(settings["workers"]),
        console_row_limit=int(settings["console_row_limit"]),
        excel_preview_rows=int(settings["excel_preview_rows"]),
        max_excel_rows_per_sheet=int(settings["max_excel_rows_per_sheet"]),
        should_generate_full_excel=bool(settings["should_generate_full_excel"]),
        should_print_large_tables=bool(settings["should_print_large_tables"]),
        reasons=reasons,
        warnings=warnings,
    )


def print_processing_policy(
    policy: ProcessingPolicy,
) -> None:
    print("\nPROCESSING POLICY")
    print("-" * 70)
    print(f"Analysis type          : {policy.analysis_type}")
    print(f"Mode                   : {policy.mode}")
    print(f"Profile                : {policy.profile}")
    print(f"Use staging            : {policy.use_staging}")
    print(f"Use DuckDB             : {policy.use_duckdb}")
    print(f"Chunk size             : {policy.chunk_size}")
    print(f"Workers                : {policy.workers}")
    print(f"Console row limit      : {policy.console_row_limit}")
    print(f"Excel preview rows     : {policy.excel_preview_rows}")
    print(f"Max Excel rows/sheet   : {policy.max_excel_rows_per_sheet}")
    print(f"Generate full Excel    : {policy.should_generate_full_excel}")
    print(f"Print large tables     : {policy.should_print_large_tables}")

    if policy.reasons:
        print("\nReasons:")
        for reason in policy.reasons:
            print(f"  - {reason}")

    if policy.warnings:
        print("\nWarnings:")
        for warning in policy.warnings:
            print(f"  - {warning}")