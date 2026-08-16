"""Regression tests for installable application metadata."""

from __future__ import annotations

import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"


def load_pyproject() -> dict:
    with PYPROJECT_PATH.open("rb") as handle:
        return tomllib.load(handle)


def test_runtime_dependencies_cover_application_imports() -> None:
    project = load_pyproject()["project"]
    dependencies = project["dependencies"]

    required_prefixes = {
        "numpy",
        "pandas",
        "openpyxl",
        "duckdb",
        "pyarrow",
        "pyxlsb",
        "pytz",
        "PySide6",
    }

    declared_names = {
        dependency.split("=", 1)[0]
        .split("<", 1)[0]
        .split(">", 1)[0]
        .strip()
        for dependency in dependencies
    }

    assert required_prefixes <= declared_names


def test_cli_and_gui_entry_points_are_declared() -> None:
    project = load_pyproject()["project"]

    assert project["scripts"]["telecom-forensics"] == "main:main"
    assert (
        project["gui-scripts"]["telecom-forensics-gui"]
        == "gui.app:main"
    )


def test_distribution_includes_application_packages() -> None:
    metadata = load_pyproject()

    assert metadata["tool"]["setuptools"]["py-modules"] == ["main"]

    package_patterns = set(
        metadata["tool"]["setuptools"]["packages"]["find"]["include"]
    )

    assert {"modules*", "gui*"} <= package_patterns
