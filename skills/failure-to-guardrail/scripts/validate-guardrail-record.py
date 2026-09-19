#!/usr/bin/env python3
import json,sys
from pathlib import Path
VALID={"OBSERVED","UNREPRODUCED","IMPLEMENTED","VERIFIED","BLOCKED"}
def main():
    if len(sys.argv)!=2: print("Usage: validate-guardrail-record.py <record.json>",file=sys.stderr); return 2
    try: d=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as e: print(f"ERROR: Cannot read record: {e}",file=sys.stderr); return 2
    errors=[]
    if d.get("status") not in VALID: errors.append("Invalid status.")
    if not d.get("evidence"): errors.append("At least one failure evidence path is required.")
    if d.get("status")=="VERIFIED":
        v=d.get("verification",{})
        if v.get("negative_case")!="PASS" or v.get("positive_case")!="PASS" or not v.get("evidence"): errors.append("VERIFIED requires passing negative and positive cases with evidence.")
    if "replace-me" in str(d.get("failure_id")): errors.append("Replace failure_id placeholder.")
    if errors:
        print("Guardrail record validation FAILED:",file=sys.stderr)
        for e in errors: print("- "+e,file=sys.stderr)
        return 1
    print("Guardrail record validation PASSED"); return 0
if __name__=="__main__": raise SystemExit(main())
