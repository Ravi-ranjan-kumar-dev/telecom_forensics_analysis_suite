"""Stage/commit/push project source to the verified GitHub branch; omit case data."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

EXPECTED_REPO = "ravi-ranjan-kumar-dev/telecom_forensics_analysis_suite"
EXPECTED_BRANCH = "hardening/postgres-multiuser-foundation"
SOURCE_DIRS = {"modules", "gui", "backend", "tools", "tests", ".github", "assets"}
EXTENSIONS = {
    ".py",
    ".js",
    ".css",
    ".svg",
    ".ico",
    ".toml",
    ".yml",
    ".yaml",
    ".sh",
    ".bat",
    ".ps1",
    ".spec",
}
ROOT_FILES = {
    "run_gui.py",
    "main.py",
    "manage.py",
    "ethicalarmor.spec",
    "pyproject.toml",
    "requirements.txt",
    "build_app.sh",
    ".gitignore",
    ".dockerignore",
    ".gitattributes",
    "README.md",
    "LICENSE",
}
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "database",
    "data",
    "cases",
    "reports",
    "output",
    "logs",
    "build",
    "dist",
    "release",
}
IGNORE_RULES = [
    ".env",
    ".env.*",
    ".venv/",
    "**/__pycache__/",
    "*.py[cod]",
    "/database/",
    "/data/",
    "/cases/",
    "/reports/",
    "/output/",
    "/logs/",
    "/build/",
    "/dist/",
    "/release/",
    "*.duckdb",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.parquet",
    "backend/docker-compose.shared-master.json",
]


def redacted(text):
    return re.sub(r"(https?://)[^/\s]*@", r"\1", text)


def git(project, *args, check=True, input=None):
    result = subprocess.run(
        ["git", "-C", str(project), *args], input=input, text=True, capture_output=True
    )
    if check and result.returncode:
        raise RuntimeError(
            redacted(result.stderr.strip() or result.stdout.strip())
            or "Git command failed: " + args[0]
        )
    return result


def remote_repository(url):
    if url.startswith("git@github.com:"):
        return url.split(":", 1)[1].removesuffix(".git").strip("/").lower()
    parsed = urlsplit(url)
    if parsed.hostname != "github.com" or parsed.scheme not in {"https", "ssh"}:
        return ""
    return parsed.path.strip("/").removesuffix(".git").lower()


def allowed_source(name):
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        return False
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    if path.name == ".env" or path.name.startswith(".env."):
        return False
    if len(path.parts) == 1:
        return path.name in ROOT_FILES
    if path.parts[0] not in SOURCE_DIRS:
        return False
    return path.suffix.lower() in EXTENSIONS or path.name in {
        "requirements.txt",
        "Dockerfile",
        ".dockerignore",
        "Dockerfile.dockerignore",
        "README.md",
        "LICENSE",
    }


def runtime_or_secret(name):
    path = Path(name)
    if path.name == ".env" or (
        path.name.startswith(".env.")
        and path.name not in {".env.example", ".env.sample", ".env.template"}
    ):
        return True
    if path.suffix.lower() in {".duckdb", ".db", ".sqlite", ".sqlite3", ".parquet"}:
        return True
    return bool(
        path.parts
        and path.parts[0]
        in {
            "data",
            "database",
            "cases",
            "reports",
            "output",
            "logs",
            "dist",
            "release",
            "build",
            ".venv",
        }
        and path.name not in {".gitkeep", "README.md"}
    )


def publish(project, *, push=False):
    project = Path(project).expanduser().resolve(strict=True)
    git(project, "rev-parse", "--is-inside-work-tree")
    if Path(git(project, "rev-parse", "--show-toplevel").stdout.strip()).resolve() != project:
        raise ValueError("Project must be the Git repository root")
    branch = git(project, "branch", "--show-current").stdout.strip()
    if branch != EXPECTED_BRANCH:
        raise ValueError("Unexpected branch: " + branch + "; expected " + EXPECTED_BRANCH)
    remote = git(project, "remote", "get-url", "--push", "origin").stdout.strip()
    if remote_repository(remote) != EXPECTED_REPO:
        raise ValueError("origin does not match the verified repository")
    tracked = git(project, "ls-files", "-z").stdout.split("\0")
    unsafe = [p for p in tracked if p and runtime_or_secret(p)]
    if unsafe:
        raise ValueError(
            "Tracked runtime/secret files must be reviewed before a source push:\n"
            + "\n".join(unsafe[:30])
        )
    staged = git(project, "diff", "--cached", "--name-only", "-z").stdout.split("\0")
    unrelated = [p for p in staged if p and not allowed_source(p)]
    if unrelated:
        raise ValueError(
            "Unrelated staged files found; no commit was made:\n" + "\n".join(unrelated[:30])
        )
    source = []
    for directory in sorted(SOURCE_DIRS):
        folder = project / directory
        if not folder.is_dir():
            continue
        import os

        for base, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not (Path(base) / d).is_symlink()]
            for name in files:
                file = Path(base) / name
                relative = file.relative_to(project).as_posix()
                if allowed_source(relative):
                    if file.is_symlink() or not file.resolve().is_relative_to(project):
                        raise ValueError("Source symlink requires review: " + relative)
                    source.append(relative)
    for name in ROOT_FILES:
        candidate = project / name
        if candidate.is_symlink():
            raise ValueError("Source symlink requires review: " + name)
        if candidate.is_file():
            source.append(name)
    # Include deletions of tracked source files, but never runtime files.
    source.extend(p for p in tracked if p and allowed_source(p))
    print("Repository: https://github.com/" + EXPECTED_REPO)
    print("Branch:", branch)
    print("Source candidates:", len(set(source)))
    if not push:
        print("PLAN ONLY: no files staged, committed or pushed. Use --push to execute.")
        return
    ignore = project / ".gitignore"
    previous = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    missing = [r for r in IGNORE_RULES if r not in previous.splitlines()]
    if missing:
        ignore.write_text(
            previous.rstrip()
            + "\n\n# EthicalArmor runtime data and local configuration\n"
            + "\n".join(missing)
            + "\n"
        )
    source.append(".gitignore")
    source = sorted(set(source))
    ignored = git(
        project, "check-ignore", "--stdin", "-z", check=False, input="\0".join(source) + "\0"
    )
    if ignored.returncode not in {0, 1}:
        raise RuntimeError(redacted(ignored.stderr))
    ignored_paths = set(ignored.stdout.split("\0"))
    source = [name for name in source if name not in ignored_paths]
    for offset in range(0, len(source), 150):
        git(project, "add", "--", *source[offset : offset + 150])
    staged = [
        p for p in git(project, "diff", "--cached", "--name-only", "-z").stdout.split("\0") if p
    ]
    if any(not allowed_source(p) or runtime_or_secret(p) for p in staged):
        raise ValueError("Staging contains a non-source file; nothing was committed or pushed")
    if staged:
        print("Committing", len(staged), "source file changes")
        result = git(
            project, "commit", "-m", "Fix investigation workflows and add native desktop builds"
        )
        print(redacted(result.stdout))
    else:
        print("No new staged source changes; pushing current branch tip.")
    result = git(project, "push", "-u", "origin", "HEAD:refs/heads/" + EXPECTED_BRANCH)
    print(redacted(result.stdout + result.stderr))
    print("PUSHED:", git(project, "rev-parse", "HEAD").stdout.strip())
    print("Native build runs: https://github.com/" + EXPECTED_REPO + "/actions")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    try:
        publish(args.project, push=args.push)
    except Exception as error:
        parser.exit(1, "STOPPED: " + redacted(str(error)) + "\n")
