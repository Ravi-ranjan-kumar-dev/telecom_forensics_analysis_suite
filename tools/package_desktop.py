"""Archive a native PyInstaller bundle while retaining executable permissions."""

from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version
import hashlib
import json
from pathlib import Path
import platform
import sys
import tarfile
import zipfile


def package(root):
    root = Path(root).resolve()
    source = root / "dist" / ("EthicalArmor.app" if sys.platform == "darwin" else "EthicalArmor")
    executable = (
        source / "Contents/MacOS/EthicalArmor"
        if sys.platform == "darwin"
        else source / ("EthicalArmor.exe" if sys.platform == "win32" else "EthicalArmor")
    )
    if not executable.is_file():
        raise FileNotFoundError(f"Native executable not found: {executable}")
    output = root / "release"
    output.mkdir(exist_ok=True)
    architecture = platform.machine().lower().replace("amd64", "x86_64")
    name = f"EthicalArmor-{platform.system().lower()}-{architecture}"
    versions = {}
    for dependency in ("PyInstaller", "PySide6", "pandas", "numpy", "duckdb", "pyarrow"):
        try:
            versions[dependency] = version(dependency)
        except PackageNotFoundError:
            versions[dependency] = "unknown"
    metadata = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "dependencies": versions,
        "client_only": True,
        "authentication_api": "External service; configure TELECOM_API_URL",
        "existing_data": "Set ETHICALARMOR_DATA_DIR to the existing EthicalArmor project directory to reuse its selected master/cases.",
    }
    info = output / "build-info.json"
    info.write_text(json.dumps(metadata, indent=2) + "\n")
    instructions = output / "RUNNING.txt"
    instructions.write_text("""EthicalArmor native desktop client

Extract the whole archive before launching. Keep the executable with its _internal directory (or keep the macOS .app bundle intact).

Authentication API is a separate running service. TELECOM_API_URL defaults to http://127.0.0.1:8000. Configure it if using another API host.

To reuse your existing Kali project, launch from a terminal:
ETHICALARMOR_DATA_DIR="$HOME/Desktop/EthicalArmor" ./EthicalArmor/EthicalArmor

The master database, case evidence and credentials are not embedded in this client bundle. Keep using your verified shared-master Docker configuration for the local API.

This build is unsigned. Windows and macOS archives must be built on their corresponding native runners. Linux compatibility depends on the build host's glibc and the target system libraries. See build-info.json for the actual build platform.
""")
    if sys.platform == "win32":
        archive = output / (name + ".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as writer:
            for path in source.rglob("*"):
                if path.is_file():
                    writer.write(path, path.relative_to(source.parent))
            writer.write(info, info.name)
            writer.write(instructions, instructions.name)
    else:
        archive = output / (name + ".tar.gz")
        with tarfile.open(archive, "w:gz", compresslevel=5, dereference=False) as writer:
            writer.add(source, arcname=source.name)
            writer.add(info, arcname=info.name)
            writer.add(instructions, arcname=instructions.name)
    digest = hashlib.sha256()
    with archive.open("rb") as reader:
        for block in iter(lambda: reader.read(1024 * 1024), b""):
            digest.update(block)
    archive.with_name(archive.name + ".sha256").write_text(
        digest.hexdigest() + "  " + archive.name + "\n"
    )
    print(archive)
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    package(parser.parse_args().project)
