---
name: agent-autonomy-envelope
description: AIエージェントへタスク単位の入力、許可能力、禁止能力、ネットワーク、認証情報、リソース上限、成果物契約を割り当て、自律実行できる範囲を固定する。Use when 逐次確認を減らしながら、AIへ編集、build、test、修正、再試行の裁量を与えるとき。Don't use for 無期限の常設権限、対象を限定しない認証情報、本番への無条件アクセス、強制境界のない環境。
---

# Agent Autonomy Envelope

## 手順

**Step 1: Envelopeを作成する**
1. `assets/autonomy-envelope.template.json`をコピーする。
2. task ID、profile、入力、許可能力、禁止能力、network、credentials、limits、outputsを記録する。
3. 許可能力ごとに目的を対応させる。

**Step 2: 境界を最小化する**
1. `references/capability-catalog.md`を読む。
2. 指定されていない能力を既定で拒否する。
3. host home、継承環境変数、control socket、長命credential、任意外部networkを禁止する。
4. 外部書込みはguestへ与えず、task-scoped brokerへ分離する。

**Step 3: 検証する**
1. `python3 scripts/validate-envelope.py <envelope.json>`を実行する。
2. 失敗した項目だけを修正し、検証を再実行する。
3. 検証済みenvelopeのhashをSafety Caseへ記録する。

**Step 4: 変更を制御する**
1. 実行中に追加能力が必要になった場合はenvelopeを暗黙に拡張しない。
2. 実行をpauseし、能力、目的、範囲、期限、代替案を含む昇格要求を作成する。
3. 承認後は新しいenvelopeを検証し、以前のhashを上書きせず履歴へ残す。

## Error Handling

- allowedとdeniedが重複する場合は、許可を削除するまで実行しない。
- limitが欠落または非正数の場合は、既定値を推測せず入力を要求する。
- profileと能力が矛盾する場合は、より小さいprofileへ戻して再分類する。
