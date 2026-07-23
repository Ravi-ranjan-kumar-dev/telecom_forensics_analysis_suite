from __future__ import annotations

from pathlib import Path

import pandas as pd


def test_spot_layout_uses_immediate_subfolders_deterministically(
    tmp_path,
):
    from modules.loader.tower_spot_layout import (
        build_tower_spot_layout,
    )

    spot_b = tmp_path / "Second Spot" / "airtel"
    spot_a = tmp_path / "Event Spot"
    spot_a.mkdir(parents=True)
    spot_b.mkdir(parents=True)

    file_a = spot_a / "jio.csv"
    file_b = spot_b / "airtel.csv"
    file_a.write_text("x\n", encoding="utf-8")
    file_b.write_text("x\n", encoding="utf-8")

    layout = build_tower_spot_layout(
        tmp_path,
        [file_b, file_a],
    )

    assignments = layout["assignments"]

    assert layout["input_mode"] == "MULTI_SPOT"
    assert layout["spot_count"] == 2

    assert assignments[str(file_a.resolve())]["spot_id"] == "SPOT-01"
    assert assignments[str(file_a.resolve())]["spot_name"] == "Event Spot"

    assert assignments[str(file_b.resolve())]["spot_id"] == "SPOT-02"
    assert assignments[str(file_b.resolve())]["spot_name"] == "Second Spot"

    # Deeper operator folders remain under the immediate Spot folder.
    assert assignments[str(file_b.resolve())]["spot_folder"] == "Second Spot"


def test_spot_layout_marks_root_files_unassigned(tmp_path):
    from modules.loader.tower_spot_layout import (
        ROOT_SPOT_ID,
        build_tower_spot_layout,
    )

    spot = tmp_path / "Spot One"
    spot.mkdir()

    assigned = spot / "assigned.csv"
    loose = tmp_path / "loose.csv"

    assigned.write_text("x\n", encoding="utf-8")
    loose.write_text("x\n", encoding="utf-8")

    layout = build_tower_spot_layout(
        tmp_path,
        [assigned, loose],
    )

    assert layout["spot_count"] == 1
    assert layout["root_level_file_count"] == 1
    assert (
        layout["assignments"][str(loose.resolve())]["spot_id"]
        == ROOT_SPOT_ID
    )
    assert any(
        "UNASSIGNED-ROOT" in warning
        for warning in layout["warnings"]
    )


def test_case_loader_attaches_spot_identity_to_every_record(
    tmp_path,
    monkeypatch,
):
    from modules.loader import tower_dump_loader

    spot_1 = tmp_path / "Spot Alpha"
    spot_2 = tmp_path / "Spot Beta"
    spot_1.mkdir()
    spot_2.mkdir()

    file_1 = spot_1 / "airtel.csv"
    file_2 = spot_2 / "jio.csv"

    file_1.write_text("placeholder\n", encoding="utf-8")
    file_2.write_text("placeholder\n", encoding="utf-8")

    def fake_load_tower_dump(path, enrich_cgi=True):
        path = Path(path)

        return {
            "file": path.name,
            "operator": path.stem,
            "searched_cell_id": f"CELL-{path.stem}",
            "df": pd.DataFrame(
                [
                    {
                        "subscriber_number": (
                            "9000000001"
                            if "airtel" in path.name
                            else "9000000002"
                        ),
                        "operator": path.stem,
                        "searched_cell_id": f"CELL-{path.stem}",
                        "call_datetime": pd.Timestamp(
                            "2026-06-29 21:55:00"
                        ),
                        "source_file": path.name,
                    }
                ]
            ),
            "metadata": {},
            "rejected_rows": pd.DataFrame(),
            "warnings": [],
            "errors": [],
            "ok": True,
        }

    monkeypatch.setattr(
        tower_dump_loader,
        "load_tower_dump",
        fake_load_tower_dump,
    )

    result = tower_dump_loader.load_tower_dump_case(
        tmp_path,
        enrich_cgi=False,
        recursive=True,
    )

    assert result["ok"] is True
    assert result["metadata"]["input_mode"] == "MULTI_SPOT"
    assert result["metadata"]["spot_count"] == 2

    dataframe = result["df"]

    assert dataframe["spot_id"].notna().all()
    assert dataframe["spot_name"].notna().all()
    assert dataframe["spot_folder"].notna().all()
    assert dataframe["source_relative_path"].notna().all()

    assert set(dataframe["spot_id"]) == {
        "SPOT-01",
        "SPOT-02",
    }
    assert set(dataframe["spot_name"]) == {
        "Spot Alpha",
        "Spot Beta",
    }

    assert len(result["spot_summary"]) == 2
    assert result["spot_summary"]["files_found"].sum() == 2


def test_explicit_no_data_report_is_valid_empty(tmp_path):
    from modules.loader.tower_dump_loader import (
        load_tower_dump,
    )

    path = tmp_path / "empty_airtel_tower.csv"

    path.write_text(
        "\n".join(
            [
                "BHARTI AIRTEL LIMITED",
                "",
                "BIHAR JHARKHAND",
                "",
                (
                    "Call Details of CELL ID "
                    "'405-52-8192-12769369399' "
                    "from '21-Jun-2026 00:00:00' "
                    "to '29-Jun-2026 23:59:59'"
                ),
                "",
                (
                    "Target No,Call Type,TOC,B Party No,"
                    "LRN No,LRN TSP-LSA,Date,Time,Dur(s),"
                    "First CGI Lat/Long,First CGI,"
                    "Last CGI Lat/Long,Last CGI,"
                    "SMSC No,Service Type,IMEI,IMSI,"
                    "Call Fow No,Roam Nw,SW & MSC ID,"
                    "IN TG,OUT TG,Vowifi First UE IP,"
                    "Port1,Vowifi Last UE IP,Port2"
                ),
                "",
                "No Data Found",
                "",
                (
                    "This is System generated report "
                    "and needs no signature."
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = load_tower_dump(
        path,
        enrich_cgi=False,
    )

    assert result["ok"] is True
    assert result["data_status"] == "EMPTY_NO_DATA"
    assert result["has_records"] is False
    assert result["errors"] == []
    assert result["df"].empty
    assert result["operator"] == "airtel"
    assert (
        result["searched_cell_id"]
        == "405-52-8192-12769369399"
    )
