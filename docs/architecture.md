# アーキテクチャ

[設計概要](design.md) · [アーキテクチャ](architecture.md) · [スキルカタログ](skill-catalog.md) · [自律実行とハンドオフ](autonomy-and-handoffs.md) · [検証](validation.md) · [実装ロードマップ](implementation-roadmap.md)

スキル群の構成、正本となるSafety Case、実行profile、スキル間の関係を定義します。

## 全体アーキテクチャ

```text
利用者の依頼
    │
    ▼
agent-safety-lifecycle
    │
    ├─ agent-task-risk-classifier
    │      └─ 必要な実行profileを決定
    │
    ├─ agent-autonomy-envelope
    │      └─ 自律実行できる能力の上限を固定
    │
    ├─ agent-host-isolation
    │      └─ 実行場所と技術的境界を構築・検証
    │
    ├─ agent-run-supervisor
    │      └─ 実行、再試行、停止、pause/resumeを管理
    │
    ├─ agent-boundary-adversary
    │      └─ 境界を意図的に攻撃して実測
    │
    ├─ agent-result-gate
    │      └─ 成果物を未信頼として検査
    │
    ├─ failure-to-guardrail
    │      └─ 失敗をテストや制約へ変換
    │
    └─ agent-near-miss-review
           └─ ヒヤリハットを組織学習へ変換
```

初心者向けの`agent-safety-onboarding`は、このコア経路を段階的に体験する教育スキルとして分離します。

## 正本となる状態文書

ワークフローごとに複数のMarkdownを作らず、判断と証拠への参照を一つの文書へ集約します。

```text
agent-safety-case.md
```

### 構成

```markdown
# Agent Safety Case

## タスクと期待する成果
## 保護対象
## リスク分類
## Autonomy Envelope
## 実行環境
## 境界テスト
## 実行履歴
## 成果物検査
## 検出した失敗
## 適用したガードレール
## 再検証結果
## 昇格判断
## 未検証事項
## 残存リスク
```

manifest、テストログ、hash、diffなどは機械可読な補助成果物として保存し、`agent-safety-case.md`から参照します。

## 実行profile

### `no-exec`

AIは説明、コード案、patch案だけを生成します。コマンドは実行しません。

### `read-only`

AIは限定された入力を検索・解析できますが、書込みと任意コマンド実行は許可しません。

### `isolated-execution`

短命なguest環境内で、編集、install、build、test、修正、再試行を許可します。ホスト側の認証情報と書込み権限は渡しません。

### `brokered-write`

検査済みの一件の操作だけを、host-side brokerが代理実行します。対象、宛先、期限、操作内容を固定します。

### `human-gated-impact`

production deploy、削除、課金、公開、権限変更など、影響が大きい操作です。最終操作の前に人間の承認を要求します。

## スキル一覧

| スキル | 主責務 | 正常系での利用 |
|---|---|---|
| `agent-safety-lifecycle` | 状態管理とルーティング | 必須 |
| `agent-task-risk-classifier` | タスクと必要権限の分類 | 必須 |
| `agent-autonomy-envelope` | 自律実行範囲の固定 | 必須 |
| `agent-host-isolation` | 隔離境界の設計と検証 | 実行がある場合 |
| `agent-run-supervisor` | 自律実行、再試行、停止 | 実行がある場合 |
| `agent-boundary-adversary` | 境界への攻撃的テスト | profile作成・変更時 |
| `agent-result-gate` | 成果物の検査と昇格判定 | 成果物を持ち出す場合 |
| `failure-to-guardrail` | 失敗の再発防止策への変換 | 失敗時のみ |
| `agent-near-miss-review` | ヒヤリハットの振り返り | 事故・未遂時のみ |
| `agent-safety-onboarding` | 初心者向け段階学習 | 教育時のみ |
