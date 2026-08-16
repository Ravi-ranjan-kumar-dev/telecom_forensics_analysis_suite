"""Regression tests for the production release gate."""

from __future__ import annotations

from pathlib import Path

from tools.release_check import compile_source


def test_compile_source_ignores_virtual_environment(
    tmp_path: Path,
) -> None:
    modules = tmp_path / "modules"
    gui = tmp_path / "gui"
    virtual_environment = tmp_path / ".venv"

    modules.mkdir()
    gui.mkdir()
    virtual_environment.mkdir()

    (modules / "valid_module.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )
    (gui / "valid_gui.py").write_text(
        "WINDOW_TITLE = 'Test'\n",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        "def main():\n    return 0\n",
        encoding="utf-8",
    )

    # This represents a third-party template that is not valid Python.
    (virtual_environment / "dependency_template.py").write_text(
        "{% for module in modules %}\n",
        encoding="utf-8",
    )

    assert compile_source(tmp_path) is True
