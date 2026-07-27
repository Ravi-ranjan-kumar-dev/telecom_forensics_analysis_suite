
import pandas as pd

from modules.controllers import (
    imei_device_controller,
)


def test_dedicated_ipdr_resolver_is_canonical_and_read_only(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        imei_device_controller,
        "PROJECT_ROOT",
        tmp_path,
    )

    folder = (
        imei_device_controller
        .resolve_imei_ipdr_input_folder(
            "CASE-001"
        )
    )

    assert folder == (
        tmp_path
        / "data"
        / "device"
        / "imei"
        / "ipdr"
    )

    assert not folder.exists()


def test_dedicated_ipdr_inventory_uses_shared_layer(
    monkeypatch,
    tmp_path,
):
    input_folder = (
        tmp_path
        / "data"
        / "device"
        / "imei"
        / "ipdr"
    )

    captured = {}

    generic_inventory = {
        "folder": input_folder,
        "files_found": 6,
        "identifiers": [
            "862261072892730",
            "862286069717070",
        ],
        "device_frames": {
            "862261072892730": pd.DataFrame(
                [
                    {
                        "imei": "8622610728927300",
                    }
                ]
            ),
            "862286069717070": pd.DataFrame(),
        },
        "acquisition_manifest": pd.DataFrame(),
        "all_content_groups": 6,
        "supported_content_groups": 2,
        "unique_content_groups": 2,
        "non_source_acquisitions": 4,
        "duplicate_source_acquisitions": 0,
        "analytical_records": 1,
        "warnings": [],
        "errors": [],
    }

    def fake_inventory_loader(
        **kwargs,
    ):
        captured.update(
            kwargs
        )

        return generic_inventory

    monkeypatch.setattr(
        imei_device_controller,
        "resolve_imei_ipdr_input_folder",
        lambda case_id: input_folder,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "load_dedicated_evidence_inventory",
        fake_inventory_loader,
    )

    result = (
        imei_device_controller
        ._load_dedicated_imei_ipdr_inventory(
            "CASE-001"
        )
    )

    assert captured[
        "folder"
    ] == input_folder

    assert captured[
        "expected_source_type"
    ] == "IPDR"

    assert captured[
        "supported_suffixes"
    ] is (
        imei_device_controller
        .IMEI_EVIDENCE_SUFFIXES
    )

    assert captured[
        "inspect_file"
    ] is (
        imei_device_controller
        .inspect_imei_evidence_file
    )

    assert captured[
        "normalize_file"
    ] is (
        imei_device_controller
        .normalize_imei_ipdr_file
    )

    assert result[
        "supported_ipdr_content_groups"
    ] == 2

    assert result[
        "non_ipdr_acquisitions"
    ] == 4

    assert result[
        "duplicate_ipdr_acquisitions"
    ] == 0

    assert result[
        "identifiers"
    ] == [
        "862261072892730",
        "862286069717070",
    ]
