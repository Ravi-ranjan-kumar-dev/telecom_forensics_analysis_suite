"""CLI demonstration: prints metadata/counters, never subscriber rows.

Execute from EthicalArmor project root:
python tools/demo_universal_engine.py <file> --profiles-dir ./.format_profiles
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# Also allow: python tools/demo_universal_engine.py <file>
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.loader.universal_evidence import load_universal_evidence
from modules.loader.universal_bridge import module_preview

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("--profiles-dir",default=".ethicalarmor_format_profiles")
    parser.add_argument("--module",choices=["CDR","TOWER_DUMP","IPDR","IMEI"])
    parser.add_argument("--type",dest="evidence_type")
    parser.add_argument("--no-native",action="store_true")
    parser.add_argument("--operator",choices=["Jio","Airtel","Vi","BSNL","MTNL"],
                        help="Analyst-verified operator (not auto-detected). Conflicting source evidence will be held for review.")
    args=parser.parse_args()
    result=load_universal_evidence(args.file,profiles_dir=args.profiles_dir,
        selected_module=args.module,selected_type=args.evidence_type,
        selected_operator=args.operator,allow_native=not args.no_native)
    print(json.dumps({"ok":result["ok"],"source_sha256":result["source_sha256"],
        "file_results":module_preview(result),"errors":result["errors"]},indent=2,default=str))
if __name__=="__main__":main()
