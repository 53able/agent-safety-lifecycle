#!/usr/bin/env python3
import json,sys
from pathlib import Path
VALID={"NOT_STARTED","UNVERIFIED","PASS","FAIL","BLOCKED"}
def main():
    if len(sys.argv)!=2: print("Usage: validate-onboarding-progress.py <progress.json>",file=sys.stderr); return 2
    try: d=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as e: print(f"ERROR: Cannot read progress: {e}",file=sys.stderr); return 2
    errors=[]; levels=d.get("levels",[])
    if [x.get("level") for x in levels]!=list(range(1,7)): errors.append("Levels 1 through 6 are required in order.")
    for x in levels:
        if x.get("status") not in VALID: errors.append(f"Invalid status at level {x.get('level')}")
        if x.get("status")=="PASS" and not x.get("evidence"): errors.append(f"PASS without evidence at level {x.get('level')}")
    current=d.get("current_level")
    if not isinstance(current,int) or current not in range(1,7): errors.append("current_level must be 1 through 6.")
    if errors:
        print("Onboarding validation FAILED:",file=sys.stderr)
        for e in errors: print("- "+e,file=sys.stderr)
        return 1
    print("Onboarding validation PASSED"); return 0
if __name__=="__main__": raise SystemExit(main())
