"""Common cryptographic hashing helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_fingerprint(path: str | Path) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve(strict=False)
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    stat = file_path.stat()
    return {
        "file_name": file_path.name,
        "file_size_bytes": int(stat.st_size),
        "sha256": sha256_file(file_path),
    }
