from pathlib import Path
import re

from modules.core.time_utils import new_run_id


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_ROOT = PROJECT_ROOT / "output" / "reports"


def safe_filename(value: object, fallback: str = "report") -> str:
    """Return a filesystem-safe filename component."""
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    text = text.strip("._-")
    return text or fallback


def get_single_report_path(
    target: object,
    output_dir: str | Path | None = None,
) -> Path:
    """Return the output path for one target's analyzed workbook."""
    base = Path(output_dir).expanduser().resolve() if output_dir else DEFAULT_REPORT_ROOT / "single"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{safe_filename(target, 'unknown_target')}_{new_run_id('cdr_report')}.xlsx"


def get_multi_report_path(
    case_name: object | None = None,
    output_dir: str | Path | None = None,
) -> Path:
    """Return the output path for the multiple-CDR common-analysis workbook."""
    base = Path(output_dir).expanduser().resolve() if output_dir else DEFAULT_REPORT_ROOT / "multiple"
    base.mkdir(parents=True, exist_ok=True)
    case_component = safe_filename(case_name, "Multi_CDR")
    return base / f"{case_component}_{new_run_id('multi_cdr_report')}.xlsx"

def get_imei_device_report_path(
    imei: object,
    *,
    case_id: object | None = None,
    output_dir: str | Path | None = None,
) -> Path:
    """Return the output path for one IMEI device workbook."""

    base = (
        Path(
            output_dir
        ).expanduser().resolve()
        if output_dir
        else (
            DEFAULT_REPORT_ROOT
            / "device"
            / "imei"
        )
    )

    base.mkdir(
        parents=True,
        exist_ok=True,
    )

    case_component = safe_filename(
        case_id,
        "CASE",
    )

    imei_component = safe_filename(
        imei,
        "unknown_imei",
    )

    return base / (
        f"{case_component}_"
        f"{imei_component}_"
        f"{new_run_id('imei_device_report')}.xlsx"
    )


def get_imei_common_report_path(
    case_id: object = "",
    *,
    output_dir: str | Path | None = None,
) -> Path:
    """Return a unique path for one common IMEI analysis workbook."""

    base = (
        Path(
            output_dir
        ).expanduser().resolve()
        if output_dir
        else (
            DEFAULT_REPORT_ROOT
            / "device"
            / "imei"
        )
    )

    base.mkdir(
        parents=True,
        exist_ok=True,
    )

    case_component = safe_filename(
        case_id,
        "CASE",
    )

    return base / (
        f"{case_component}_IMEI_Common_Analysis_"
        f"{new_run_id('imei_common')}.xlsx"
    )
