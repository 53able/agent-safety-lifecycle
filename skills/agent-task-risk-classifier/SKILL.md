---
name: agent-task-risk-classifier
description: AIエージェントへ渡すタスクの入力、コマンド、データ、外部通信、副作用を分類し、no-exec、read-only、isolated-execution、brokered-write、human-gated-impactから必要最小限の実行profileを選ぶ。Use when AIへ開発タスクを任せる前に必要な権限と実行場所を決めるとき。Don't use for VM構築、成果物検査、実行後の事故分析。
---

# Agent Task Risk Classifier

## 手順

**Step 1: タスク事実を収集する**
1. `assets/task-risk-input.template.json`をコピーする。
2. コマンド実行、書込み、秘密情報、外部通信、外部副作用、不可逆操作の要否を事実として入力する。
3. 不明な項目を`false`で埋めず、`unknown_fields`へ記録する。

**Step 2: Profileを分類する**
1. `references/profile-rules.md`を読む。
2. `python3 scripts/classify-task.py <task-risk.json>`を実行する。
3. `human-gated-impact`が選ばれた場合は、不可逆操作の直前に人間承認を残す。
4. `brokered-write`が選ばれた場合は、外部操作をguestへ直接許可せずhost-side brokerを要求する。
5. `isolated-execution`が選ばれた場合は、短命なguest環境を要求する。

**Step 3: 分類根拠を記録する**
1. 選択profile、必要能力、不要能力、保護対象、昇格条件をSafety Caseへ記録する。
2. unknown fieldが残る場合はprofileを拡張せず、`UNVERIFIED`として停止条件へ追加する。

## Error Handling

- JSONが不正な場合はテンプレートから作り直す。
- 分類結果が実際の副作用より小さい場合は、入力事実を修正して再分類する。
- 人間承認が必要な操作を低いprofileへ手動変更しない。
