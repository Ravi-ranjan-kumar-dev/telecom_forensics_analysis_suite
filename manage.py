from __future__ import annotations

import runpy
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
TOOLS_DIR = PROJECT_ROOT / "tools"

COMMANDS = {
    "cgi-import": TOOLS_DIR / "import_cgi_data.py",
    "cgi-status": TOOLS_DIR / "import_cgi_data.py",
    "cgi-verify": TOOLS_DIR / "verify_cgi_database.py",
    "case-audit-verify": TOOLS_DIR / "verify_case_audit.py",
    "release-check": TOOLS_DIR / "release_check.py",
}

AUTH_COMMANDS = {
    "auth-create-admin": "create-admin",
    "auth-reset-token": "reset-token",
    "auth-reset-password": "reset-password",
}


def main() -> int:
    if len(sys.argv) < 2:
        print("Commands:")
        print("  python manage.py cgi-import data/cgi/raw")
        print("  python manage.py cgi-status")
        print("  python manage.py cgi-verify <CGI>")
        print("  python manage.py case-audit-verify [CASE_ID]")
        print("  python manage.py release-check [--with-db]")
        print("  python manage.py auth-create-admin <USERNAME>")
        print("  python manage.py auth-reset-token <USERNAME>")
        print("  python manage.py auth-reset-password <USERNAME>")
        print("  python main.py")
        return 0

    command = sys.argv[1]
    auth_command = AUTH_COMMANDS.get(command)
    if auth_command is not None:
        from backend.app.cli import main as auth_main

        return auth_main(
            [auth_command, *sys.argv[2:]]
        )

    script = COMMANDS.get(command)
    if script is None:
        print(f"Unknown command: {command}")
        return 1
    if not script.exists():
        print(f"Required tool not found: {script}")
        return 1

    if command == "cgi-status":
        sys.argv = [str(script), "--status"]
    else:
        sys.argv = [str(script), *sys.argv[2:]]

    sys.path.insert(0, str(PROJECT_ROOT))
    runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
