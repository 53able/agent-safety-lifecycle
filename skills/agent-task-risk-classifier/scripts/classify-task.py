#!/usr/bin/env python3
import json, sys
from pathlib import Path

REQUIRED = {"task_id", "needs_command_execution", "needs_file_write", "needs_secrets", "needs_external_network", "needs_external_write", "irreversible_or_high_impact", "unknown_fields"}

def main():
    if len(sys.argv) != 2:
        print("Usage: classify-task.py <task-risk.json>", file=sys.stderr); return 2
    path=Path(sys.argv[1])
    try: data=json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError: print(f"ERROR: Input not found: {path}", file=sys.stderr); return 2
    except json.JSONDecodeError as e: print(f"ERROR: Invalid JSON at line {e.lineno}: {e.msg}", file=sys.stderr); return 2
    missing=REQUIRED-data.keys()
    if missing: print("ERROR: Missing keys: "+", ".join(sorted(missing)), file=sys.stderr); return 1
    bool_keys=REQUIRED-{"task_id","unknown_fields"}
    invalid=[k for k in bool_keys if not isinstance(data[k],bool)]
    if invalid: print("ERROR: Boolean fields required: "+", ".join(sorted(invalid)), file=sys.stderr); return 1
    if not isinstance(data["unknown_fields"],list): print("ERROR: unknown_fields must be an array.", file=sys.stderr); return 1
    if data["irreversible_or_high_impact"]: profile="human-gated-impact"
    elif data["needs_external_write"] or data["needs_secrets"]: profile="brokered-write"
    elif data["needs_command_execution"] or data["needs_file_write"]: profile="isolated-execution"
    elif data["needs_external_network"]: profile="read-only"
    else: profile="no-exec"
    result={"task_id":data["task_id"],"profile":profile,"unknown_fields":data["unknown_fields"],"requires_human_gate":profile=="human-gated-impact"}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())
