#!/usr/bin/env python3
"""Verify one case audit chain or scan all cases."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.cases import case_health, verify_case_audit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify case audit-chain integrity")
    parser.add_argument("case_id", nargs="?", help="Case ID; omit to scan all case workspaces")
    args = parser.parse_args()
    if args.case_id:
        result = verify_case_audit(args.case_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("valid") else 2
    results = case_health()
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0 if all(item.get("healthy") for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
