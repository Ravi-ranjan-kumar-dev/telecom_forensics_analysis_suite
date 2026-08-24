from __future__ import annotations

import inspect
import os
from pathlib import Path

import pandas as pd

os.environ.setdefault(
    "QT_QPA_PLATFORM",
    "offscreen",
)

from gui.app import build_application
from gui.pages.cdr_page import CdrPage
from gui.workers.cdr_worker import (
    collect_cdr_report_paths,
)
from modules.controllers import (
    app_controller,
    cdr_controller,
)


def test_cdr_controller_accepts_optional_input_folder():
    single_parameters = inspect.signature(
        cdr_controller.run_single
    ).parameters

    multiple_parameters = inspect.signature(
        cdr_controller.run_multiple
    ).parameters

    assert single_parameters[
        "folder"
    ].default is None

    assert multiple_parameters[
        "folder"
    ].default is None


def test_case_aware_handlers_accept_optional_input_folder():
    single_parameters = inspect.signature(
        app_controller.handle_single_cdr
    ).parameters

    multiple_parameters = inspect.signature(
        app_controller.handle_multiple_cdr
    ).parameters

    assert single_parameters[
        "input_folder"
    ].default is None

    assert multiple_parameters[
        "input_folder"
    ].default is None

    assert callable(
        app_controller.get_direct_analysis_workspace
    )


def test_run_single_uses_selected_folder(
    tmp_path,
    monkeypatch,
):
    dataframe = pd.DataFrame(
        {
            "a_party": [
                "9000000001",
            ],
            "b_party": [
                "8000000001",
            ],
        }
    )

    observed = {}

    def fake_loader(
        folder,
    ):
        observed[
            "folder"
        ] = Path(
            folder
        )
        return dataframe.copy()

    monkeypatch.setattr(
        cdr_controller,
        "get_single_file",
        fake_loader,
    )
    monkeypatch.setattr(
        cdr_controller,
        "auto_detect_single_target",
        lambda folder, df: "9000000001",
    )
    monkeypatch.setattr(
        cdr_controller,
        "realign_target_and_b_party",
        lambda df, target: df.assign(
            target_number=target
        ),
    )

    loaded, target = cdr_controller.run_single(
        tmp_path
    )

    assert observed[
        "folder"
    ] == tmp_path.resolve()

    assert target == "9000000001"
    assert loaded.iloc[
        0
    ][
        "target_number"
    ] == "9000000001"


def test_collect_cdr_report_paths_preserves_useful_order(
    tmp_path,
):
    common = tmp_path / "common.xlsx"
    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"

    paths = collect_cdr_report_paths(
        "multiple",
        {
            "multiple_common_report": common,
            "individual_reports": {
                "one": {
                    "excel": first,
                },
                "two": {
                    "excel": second,
                },
            },
        },
    )

    assert paths == [
        str(
            common.resolve()
        ),
        str(
            first.resolve()
        ),
        str(
            second.resolve()
        ),
    ]


def test_cdr_page_validates_single_and_multiple_folders(
    tmp_path,
):
    build_application(
        [
            "cdr-gui-test",
        ]
    )

    page = CdrPage()

    single_folder = (
        tmp_path
        / "single"
    )
    single_folder.mkdir()
    (
        single_folder
        / "single.csv"
    ).write_text(
        "a,b\n1,2\n",
        encoding="utf-8",
    )

    page.set_mode(
        "single"
    )
    page.set_selected_folder(
        single_folder
    )

    assert page.validation_error() == ""

    multiple_folder = (
        tmp_path
        / "multiple"
    )
    multiple_folder.mkdir()

    for number in (
        1,
        2,
    ):
        (
            multiple_folder
            / f"{number}.csv"
        ).write_text(
            "a,b\n1,2\n",
            encoding="utf-8",
        )

    page.set_mode(
        "multiple"
    )
    assert not page._individual_reports_box.isHidden()
    assert not page._individual_reports_box.isChecked()
    page.set_selected_folder(
        multiple_folder
    )

    assert page.validation_error() == ""

    page.close()
