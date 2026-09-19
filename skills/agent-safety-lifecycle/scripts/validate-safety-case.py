#!/usr/bin/env python3
import sys
from pathlib import Path

REQUIRED = [
    "## タスクと期待する成果", "## 保護対象", "## リスク分類",
    "## Autonomy Envelope", "## 実行環境", "## 境界テスト",
    "## 実行履歴", "## 成果物検査", "## 昇格判断",
    "## 未検証事項", "## 残存リスク",
]

def main():
    if len(sys.argv) != 2:
        print("Usage: validate-safety-case.py <agent-safety-case.md>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"ERROR: Safety Case not found: {path}", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8")
    missing = [item for item in REQUIRED if item not in text]
    if missing:
        print("Safety Case validation FAILED:", file=sys.stderr)
        for item in missing:
            print(f"- Missing section: {item}", file=sys.stderr)
        return 1
    if "replace-me" in text:
        print("Safety Case validation FAILED:\n- Replace placeholder task identifiers.", file=sys.stderr)
        return 1
    print(f"Safety Case validation PASSED: {path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
