"""Minimal, idempotent EthicalArmor CLI+GUI integration with no file replacement.

Run from the repository root, after extracting only new files from the ZIP.
Fails closed before any source files are modified if expected anchors do not exist.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def insert_once(source: str, needle: str, replacement: str, guard: str) -> str:
    if guard in source:
        return source
    if source.count(needle) != 1:
        raise RuntimeError(f"Cannot identify unique integration point: {needle[:90]!r}")
    return source.replace(needle, replacement, 1)


def main() -> int:
    gui = ROOT / "gui/main_window.py"
    cli = ROOT / "modules/controllers/app_controller.py"
    if not gui.is_file() or not cli.is_file():
        print("ERROR: Run this in an EthicalArmor source checkout; missing GUI/CLI files")
        return 2
    if not (ROOT / "gui/pages/universal_evidence_page.py").is_file():
        print("ERROR: New patch files not extracted. Unzip into repository first.")
        return 2
    edits = {}
    try:
        text = gui.read_text(encoding="utf-8")
        text = insert_once(text, 'from gui.pages.tower_dump_page import TowerDumpPage',
                           'from gui.pages.tower_dump_page import TowerDumpPage\nfrom gui.pages.universal_evidence_page import UniversalEvidencePage',
                           'from gui.pages.universal_evidence_page import UniversalEvidencePage')
        text = insert_once(text, '    NavigationItem(\n        key="lookup",',
                           '    NavigationItem(\n        key="universal_evidence",\n'
                           '        title="Universal Evidence Preflight",\n'
                           '        description="Detect CDR, Tower, IPDR and IMEI formats before analysis.",\n'
                           '    ),\n    NavigationItem(\n        key="lookup",',
                           'key="universal_evidence"')
        text = insert_once(text, '            "lookup": LookupPage,',
                           '            "lookup": LookupPage,\n            "universal_evidence": UniversalEvidencePage,',
                           '"universal_evidence": UniversalEvidencePage')
        edits[gui] = text
        text = cli.read_text(encoding="utf-8")
        text = insert_once(text, '    print("7. View Case Reports")',
                           '    print("7. View Case Reports")\n    print("8. Universal Evidence Preflight")',
                           'print("8. Universal Evidence Preflight")')
        match = '''            elif choice == "7":
                show_case_reports(
                    case_id
                )
'''
        text = insert_once(text, match,
                           match + '''\n            elif choice == "8":
                from modules.controllers.universal_controller import handle_universal_evidence
                handle_universal_evidence()
''',
                           'from modules.controllers.universal_controller import handle_universal_evidence')
        text = insert_once(text, '"Select 0 to 7."', '"Select 0 to 8."', '"Select 0 to 8."')
        edits[cli] = text
    except (OSError, RuntimeError) as exc:
        print("ABORTED: no source files changed. Reason:", exc)
        return 3
    for path, content in edits.items():
        if path.read_text(encoding="utf-8") != content:
            path.write_text(content, encoding="utf-8")
            print("Updated:", path.relative_to(ROOT))
        else:
            print("Already integrated:", path.relative_to(ROOT))
    print("Integration source update complete. Run tests and open CLI/GUI to verify.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
