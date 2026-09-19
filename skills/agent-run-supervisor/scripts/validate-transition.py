#!/usr/bin/env python3
import sys
ACTIVE={"PLANNED","RUNNING","RETRYING","AWAITING_ELEVATION","AWAITING_RESULT_GATE"}
TERMINAL={"COMPLETED","FAILED","BLOCKED","STOPPED"}
ALLOWED={
("PLANNED","RUNNING"),("RUNNING","RETRYING"),("RETRYING","RUNNING"),
("RUNNING","AWAITING_ELEVATION"),("AWAITING_ELEVATION","RUNNING"),
("RUNNING","AWAITING_RESULT_GATE"),("AWAITING_RESULT_GATE","COMPLETED"),
}
def main():
    if len(sys.argv)!=3: print("Usage: validate-transition.py <from> <to>",file=sys.stderr); return 2
    source,target=sys.argv[1:]
    if source in ACTIVE and target in TERMINAL: ok=True
    else: ok=(source,target) in ALLOWED
    if not ok: print(f"INVALID transition: {source} -> {target}",file=sys.stderr); return 1
    print(f"VALID transition: {source} -> {target}"); return 0
if __name__=="__main__": raise SystemExit(main())
