#!/usr/bin/env python3
import sys
from pathlib import Path
REQ=["## タスク","## 観測事実","## 推測","## 未確認事項","## 影響範囲","## 停止要因","## 偶然守られた点","## 再現条件","## 即時対応","## 恒久対策候補","## Ownerと期限","## 再検証条件"]
def main():
    if len(sys.argv)!=2: print("Usage: validate-near-miss.py <near-miss.md>",file=sys.stderr); return 2
    p=Path(sys.argv[1])
    if not p.is_file(): print(f"ERROR: Review not found: {p}",file=sys.stderr); return 2
    text=p.read_text(encoding="utf-8"); missing=[x for x in REQ if x not in text]
    if missing:
        print("Near-miss validation FAILED:",file=sys.stderr)
        for x in missing: print(f"- Missing section: {x}",file=sys.stderr)
        return 1
    print("Near-miss validation PASSED"); return 0
if __name__=="__main__": raise SystemExit(main())
