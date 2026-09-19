---
name: agent-safety-onboarding
description: AIに慣れていない開発者へ、no-exec、read-only、isolated-execution、result gateの順で安全な利用方法を演習させ、各段階の理解と境界確認を記録する。Use when 開発チームへAIエージェントを段階的に導入し、実行権限を広げる前に基本操作とリスクを学んでもらうとき。Don't use for 本番権限の自動付与、セキュリティ認証、経験だけを根拠とする隔離工程の省略。
---

# Agent Safety Onboarding

## 手順

**Step 1: 開始レベルを選ぶ**
1. `references/levels.md`を読み、最小の学習レベルから開始する。
2. 経験年数だけを理由に境界演習を省略しない。
3. `assets/onboarding-progress.template.json`をコピーする。

**Step 2: レベルごとの演習を実行する**
1. Level 1では説明とコード案だけを扱う。
2. Level 2ではread-only入力を調査する。
3. Level 3では隔離環境でpatchを生成する。
4. Level 4では隔離環境でbuildとtestを実行する。
5. Level 5ではresult gateを通して成果物を取り込む。
6. Level 6ではbrokered-writeと人間承認を体験する。

**Step 3: 合格証拠を記録する**
1. 各レベルの演習、期待結果、観測結果、証拠を記録する。
2. AIが指示へ従ったことではなく、境界と停止手順を説明・実演できたことを確認する。
3. `python3 scripts/validate-onboarding-progress.py <progress.json>`を実行する。

**Step 4: 次のレベルへ進める**
1. 現在レベルのrequired exerciseがすべて`PASS`の場合だけ次へ進める。
2. 本番権限を自動付与しない。
3. 実行profileの検証は各専門スキルで別に行う。

## Error Handling

- 演習環境を用意できない場合はレベルを合格扱いにしない。
- 証拠がない場合は`UNVERIFIED`とする。
- 境界違反が起きた場合は進級を停止し、`failure-to-guardrail`へ接続する。
