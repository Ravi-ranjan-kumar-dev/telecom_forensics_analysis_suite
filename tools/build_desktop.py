"""Build on each target OS: python tools/build_desktop.py [--install]."""
from pathlib import Path
import argparse
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Native EthicalArmor desktop build (run separately on Windows, Linux and macOS).")
    parser.add_argument("--install", action="store_true", help="Install project requirements and PyInstaller into this Python environment first.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.install:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(root / "requirements.txt"), "pyinstaller>=6,<7"], check=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", str(root / "ethicalarmor.spec"), "--clean", "--noconfirm"], cwd=root, check=True)
    print("Native build saved in", root / "dist")
    print("Authentication API is a separate service. Configure TELECOM_API_URL for your deployment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
