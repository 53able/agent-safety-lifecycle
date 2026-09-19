---
name: agent-boundary-adversary
description: 隔離済みのAI実行環境に対して、ファイル、認証情報、ネットワーク、コマンド、リソース、依存関係、副作用の境界テストを行い、実測結果を記録する。Use when guest VM、sandbox、restricted interpreterの境界を本番利用前または設定変更後に検証するとき。Don't use for 隔離されていないホスト、実データを使う破壊試験、AIが命令を拒否したことだけを根拠とする安全判定。
---

# Agent Boundary Adversary

## 手順

**Step 1: テスト前提を確認する**
1. 隔離環境、manifest、保護対象、停止手段が存在することを確認する。
2. 実データ、実credential、本番endpointを使用しない。
3. `assets/adversarial-report.template.json`をコピーする。
4. 隔離が未確認のhostでは実行せず`BLOCKED`にする。

**Step 2: テスト計画を作る**
1. `references/test-classes.md`を読む。
2. 各test classについて、攻撃入力、期待する拒否結果、観測方法、cleanupを記録する。
3. AIの拒否応答ではなく、技術的な境界による拒否をoracleにする。

**Step 3: 実行して記録する**
1. mount、credential、network、command、resource、supply chain、side effect、duplicate execution、cleanupを順に実行する。
2. command、exit code、stdout、stderr、保護対象の変化を保存する。
3. 未実行を`PASS`にせず`UNVERIFIED`と記録する。
4. 境界外へ到達した場合は即時停止して`FAIL`とする。

**Step 4: 報告を検証する**
1. `python3 scripts/validate-adversarial-report.py <report.json>`を実行する。
2. 全required classが`PASS`の場合だけ、対象構成を`verified for tested configuration`と記録する。
3. manifestまたはruntime変更後は以前の結果を流用せず再検証する。

## Error Handling

- cleanupが確認できない場合は`BLOCKED`とする。
- 観測方法がないテストは実行せず`UNVERIFIED`とする。
- protected assetへ到達した場合は証拠を保存し、profile rolloutを停止する。
