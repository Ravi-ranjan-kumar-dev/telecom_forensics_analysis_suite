#!/usr/bin/env python3
"""Read locally stored EthicalArmor handled-error diagnostics (stdlib only)."""
from __future__ import annotations
import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / "diagnostics"


def show(event: dict) -> None:
    print(f"ERROR ID : {event.get('id', '-')}")
    print(f"TIME     : {event.get('timestamp_utc', '-')}")
    print(f"TYPE     : {event.get('type', '-')}")
    for label, attr in (("FAILED AT", "origin"), ("HANDLED AT", "caught_at")):
        site = event.get(attr) or {}
        if site:
            print(f"{label:10}: {site.get('file')}:{site.get('line')} → {site.get('function')}()")
    print("SUGGESTED: Check the FAILED AT function first, then HANDLED AT if needed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Find the module/function responsible for handled EthicalArmor errors")
    parser.add_argument("action", choices=["last", "history", "hotspots"], nargs="?", default="last")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    if args.action == "hotspots":
        # Read-only code size guide; nothing is deleted or rewritten.
        entries = []
        for tree in ("gui", "modules", "backend"):
            folder = ROOT / tree
            if not folder.exists():
                continue
            for path in folder.rglob("*.py"):
                if any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(ROOT).parts):
                    continue
                try:
                    source = path.read_text(encoding="utf-8-sig")
                    parsed = ast.parse(source, filename=str(path))
                except (OSError, UnicodeError, SyntaxError):
                    continue
                for node in ast.walk(parsed):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        span = (node.end_lineno or node.lineno) - node.lineno + 1
                        entries.append((span, path.relative_to(ROOT), node.lineno, node.name))
        print("Largest functions to review for safe refactoring (no code modified):")
        for span, path, line, name in sorted(entries, key=lambda e:e[0], reverse=True)[:20]:
            print(f"{span:>5} lines   {path}:{line}   {name}()")
        return
    if args.action == "last":
        p = DIAG / "last_handled_error.json"
        if not p.exists():
            print("No handled errors recorded yet. Start the GUI and reproduce the problem.")
            return
        show(json.loads(p.read_text(encoding="utf-8")))
    else:
        p = DIAG / "handled_errors.jsonl"
        if not p.exists():
            print("No handled-error history yet.")
            return
        from collections import deque
        with p.open(encoding="utf-8") as f:
            lines = deque(f, maxlen=max(1, min(args.limit, 50)))
        for raw in lines:
            try:
                show(json.loads(raw))
                print("-" * 54)
            except json.JSONDecodeError:
                continue


if __name__ == "__main__":
    main()
