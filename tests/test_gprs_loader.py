from pathlib import Path

from modules.loader.gprs_dump_loader import (
    FORMAT_AIRTEL_GPRS_SESSION,
    load_gprs_dump_file,
)


def test_airtel_gprs_sample(sample_path: Path):
    result = load_gprs_dump_file(sample_path)

    assert result["ok"] is True
    assert result["source_format"] == FORMAT_AIRTEL_GPRS_SESSION
    assert len(result["df"]) > 0
    assert "session_start" in result["df"].columns
    assert "session_end" in result["df"].columns
