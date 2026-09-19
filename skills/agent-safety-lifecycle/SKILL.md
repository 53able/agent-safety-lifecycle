---
name: agent-safety-lifecycle
description: AIエージェントへタスクを渡す前のリスク分類から、隔離、境界検証、成果物検査、失敗の再発防止までを専門スキルへ振り分け、単一のsafety caseへ状態を集約する。Use when AIにコード実行、依存関係の導入、ファイル変更、外部通信、成果物の取り込みを任せる前後の安全工程を管理するとき。Don't use for プロンプト表現だけの安全レビュー、隔離しない本番操作、通常のコードレビュー。
---

# Agent Safety Lifecycle

## 手順

**Step 1: Safety Caseを開始する**
1. `assets/agent-safety-case.template.md`を作業領域へコピーする。
2. タスク、期待する成果物、保護対象、許可された副作用を記録する。
3. 既存のSafety Caseがある場合は新規作成せず、現在の状態と証拠を読み込む。

**Step 2: 現在の工程を判定する**
1. `references/routing-matrix.md`を読み、次に必要な専門スキルを一つ選ぶ。
2. タスクの実行profileが未決定なら`agent-task-risk-classifier`へ渡す。
3. profileは決定済みだが能力境界が未固定なら`agent-autonomy-envelope`へ渡す。
4. 実行環境が未検証なら`agent-host-isolation`へ渡す。
5. 実行準備が完了しているなら`agent-run-supervisor`へ渡す。
6. profileの新規作成または境界変更があるなら`agent-boundary-adversary`へ渡す。
7. 成果物をホストへ移す場合は`agent-result-gate`へ渡す。
8. 具体的な失敗が観測された場合だけ`failure-to-guardrail`へ渡す。
9. 事故またはヒヤリハットがあった場合だけ`agent-near-miss-review`へ渡す。

**Step 3: 状態を集約する**
1. 専門スキルの判定、証拠パス、未検証事項、残存リスクをSafety Caseへ追記する。
2. `python3 scripts/validate-safety-case.py <safety-case>`を実行する。
3. 検証に失敗した場合は、不足セクションを補い、検証を再実行する。

**Step 4: ハンドオフを制御する**
1. Autonomy Envelope内の正常系では、人間への逐次確認を追加しない。
2. 権限拡張、不可逆操作、境界違反、証拠不足の場合だけ状態を`PAUSED`または`BLOCKED`にする。
3. 人間への依頼には、要求能力、目的、範囲、有効期限、代替案、許可しない場合の影響を記載する。
4. `COMPLETED`は、成果物検査と必要な承認が完了した場合だけ記録する。

## Error Handling

- profileを一意に選べない場合は、より小さいprofileを選び、不足能力を`UNVERIFIED`として記録する。
- 専門スキルが利用できない場合は、工程を省略せず`BLOCKED`として記録する。
- Safety Caseの証拠パスが存在しない場合は、完了判定を停止する。
