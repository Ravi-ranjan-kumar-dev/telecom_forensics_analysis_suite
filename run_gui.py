"""Desktop GUI launcher for Telecom Forensics Analysis Suite."""

from __future__ import annotations

import sys
import os

os.environ["TELECOM_GUI_MODE"] = "1"
os.environ["TELECOM_GUI_FAST_MODE"] = "1"
os.environ.setdefault("QT_LOGGING_RULES", "qt.accessibility.atspi*=false")
os.environ.setdefault("QT_LINUX_ACCESSIBILITY_ALWAYS_ON", "0")

try:
    from gui.app import main
    if __name__ == "__main__":
        sys.exit(main())
except Exception as e:
    print(f"[!] Critical GUI Startup Error: {e}")
    sys.exit(1)
