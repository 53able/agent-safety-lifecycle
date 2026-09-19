#!/usr/bin/env python3
import json, sys
from pathlib import Path
REQUIRED={"mount","credential","network","command","resource","supply-chain","side-effect","duplicate-execution","cleanup"}
STATUSES={"PASS","FAIL","BLOCKED","UNVERIFIED"}
def main():
    if len(sys.argv)!=2: print("Usage: validate-adversarial-report.py <report.json>",file=sys.stderr); return 2
    try: data=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as e: print(f"ERROR: Cannot read report: {e}",file=sys.stderr); return 2
    tests=data.get("tests",[]); found={t.get("class") for t in tests}; errors=[]
    if REQUIRED-found: errors.append("Missing test classes: "+", ".join(sorted(REQUIRED-found)))
    for t in tests:
        if t.get("status") not in STATUSES: errors.append(f"Invalid status for {t.get('class')}")
        if t.get("status")=="PASS" and not t.get("evidence"): errors.append(f"PASS without evidence: {t.get('class')}")
    if "replace-me" in str(data.get("configuration_id")): errors.append("Replace configuration_id placeholder.")
    if errors:
        print("Report validation FAILED:",file=sys.stderr)
        for e in errors: print("- "+e,file=sys.stderr)
        return 1
    summary={s:sum(1 for t in tests if t.get("status")==s) for s in STATUSES}
    print(json.dumps(summary,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
