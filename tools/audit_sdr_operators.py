"""Run with: python -m tools.audit_sdr_operators [--sample 10000]"""
from __future__ import annotations
import argparse
import json
from modules.database.db_paths import master_duckdb_path
from modules.database.sdr_operator_audit import audit_sdr_operator_labels

def main():
    parser=argparse.ArgumentParser(description="Read-only SDR operator label quality audit")
    parser.add_argument("--sample",type=int,default=10000)
    args=parser.parse_args()
    result=audit_sdr_operator_labels(master_duckdb_path(),sample_rows=args.sample)
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__ == "__main__":
    main()
