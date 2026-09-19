#!/usr/bin/env python3
import argparse, json, os, stat
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("root"); p.add_argument("--max-files",type=int,default=1000); p.add_argument("--max-bytes",type=int,default=100_000_000); a=p.parse_args()
    root=Path(a.root)
    if not root.is_dir(): print(f"ERROR: Artifact directory not found: {root}",file=__import__('sys').stderr); return 2
    issues=[]; files=0; total=0
    for path in root.rglob("*"):
        files+=1
        try: st=path.lstat()
        except OSError as e: issues.append(f"cannot-stat:{path}:{e}"); continue
        if stat.S_ISLNK(st.st_mode): issues.append(f"symlink:{path.relative_to(root)}"); continue
        if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)): issues.append(f"special-file:{path.relative_to(root)}")
        if stat.S_ISREG(st.st_mode):
            total+=st.st_size
            if st.st_mode & 0o111: issues.append(f"executable:{path.relative_to(root)}")
    if files>a.max_files: issues.append(f"file-count:{files}>{a.max_files}")
    if total>a.max_bytes: issues.append(f"total-bytes:{total}>{a.max_bytes}")
    decision="REJECTED" if issues else "REVIEW_REQUIRED"
    print(json.dumps({"files":files,"bytes":total,"issues":issues,"decision":decision},indent=2))
    return 1 if issues else 0
if __name__=="__main__": raise SystemExit(main())
