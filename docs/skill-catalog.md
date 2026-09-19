# スキルカタログ

[設計概要](design.md) · [アーキテクチャ](architecture.md) · [スキルカタログ](skill-catalog.md) · [自律実行とハンドオフ](autonomy-and-handoffs.md) · [検証](validation.md) · [実装ロードマップ](implementation-roadmap.md)

各スキルの責務、発火条件、入力、成功条件、非対象を定義します。ルーターを利用する標準構成では、10スキルを一式でインストールします。

## 各スキルの設計

### `agent-safety-lifecycle`

#### 目的

現在の状態から必要なスキルを選び、実行結果を`agent-safety-case.md`へ集約します。

#### description案

```yaml
description: AIエージェントへタスクを渡す前のリスク分類から、隔離、境界検証、成果物検査、失敗の再発防止までを専門スキルへ振り分け、単一のsafety caseへ状態を集約する。Use when AIにコード実行、依存関係の導入、ファイル変更、外部通信、成果物の取り込みを任せる前後の安全工程を管理するとき。Don't use for プロンプト表現だけの安全レビュー、隔離しない本番操作、通常のコードレビュー。
```

#### 入力

- タスクの目的
- 期待する成果物
- 現在の工程
- 既存のsafety case
- 利用可能な実行基盤

#### 成功条件

- 次の工程が一意に決まる
- 必要なスキルだけを呼び出す
- すべての状態変更がsafety caseに残る
- 正常系で不要な人間確認を増やさない

#### 非対象

- 境界の実装
- 成果物の技術的検査
- 外部操作の承認代行

### `agent-task-risk-classifier`

#### 目的

最初に「実行権限が本当に必要か」を判断し、最小のprofileを選びます。

#### description案

```yaml
description: AIエージェントへ渡すタスクの入力、コマンド、データ、外部通信、副作用を分類し、no-exec、read-only、isolated-execution、brokered-write、human-gated-impactから必要最小限の実行profileを選ぶ。Use when AIへ開発タスクを任せる前に必要な権限と実行場所を決めるとき。Don't use for VM構築、成果物検査、実行後の事故分析。
```

#### 必須確認

1. コマンド実行が必要か
2. 読み取りだけで完了できるか
3. 書込み先はどこか
4. 秘密情報が必要か
5. 外部通信が必要か
6. 外部システムへ副作用を起こすか
7. 失敗時に破棄・復旧できるか

#### 出力

- 推奨profile
- 必要な能力
- 不要な能力
- 保護対象
- 人間承認が必要になる条件

### `agent-autonomy-envelope`

#### 目的

タスク単位の許可能力、禁止能力、上限、成果物契約を固定します。

#### description案

```yaml
description: AIエージェントへタスク単位の入力、許可能力、禁止能力、ネットワーク、認証情報、リソース上限、成果物契約を割り当て、自律実行できる範囲を固定する。Use when 逐次確認を減らしながら、AIへ編集、build、test、修正、再試行の裁量を与えるとき。Don't use for 無期限の常設権限、対象を限定しない認証情報、本番への無条件アクセス、強制境界のない環境。
```

#### envelope例

```yaml
task: frontend-test-fix
profile: isolated-execution
execution_host: short-lived-guest-vm

inputs:
  - source-snapshot: read-only

allowed:
  - edit-guest-scratch
  - install-from-approved-registry
  - run-build
  - run-tests
  - retry-failed-tests
  - export-patch
  - export-test-log

denied:
  - read-host-home
  - inherit-host-environment
  - use-ssh-agent
  - access-control-socket
  - git-push
  - deploy
  - access-production
  - arbitrary-external-network

limits:
  wall-time: 30m
  retry-count: 3
  output-size: 100MB

outputs:
  - patch
  - test-log
  - dependency-diff
```

#### 人間の確認点

- envelopeの初回承認
- 保護対象の追加
- 外部書込み能力の追加
- profileの昇格

### `agent-host-isolation`

#### 目的

既存スキルを再利用し、envelopeをOS・VM・network・credential・resourceの実効的な境界へ変換します。

#### 責務

- execution hostの選択
- read-only input snapshot
- guest-local scratch
- network default deny
- credential非注入
- host integration無効化
- resource limit
- watchdogとcleanup
- host-side result gate
- 対象構成での境界検証

#### 再編方針

新しいスキル群を評価するまでは、既存の境界テストやresult gateの手順を削除しません。責務の重複を計測してから、独立スキルへ段階的に移します。

### `agent-run-supervisor`

#### 目的

envelope内での実行、再試行、停止、pause/resumeを管理し、正常系では人間へ質問せず最終成果物まで進めます。

#### description案

```yaml
description: 承認済みのautonomy envelope内でAIタスクを実行し、状態、再試行、タイムアウト、pause、resume、失敗、成果物提出を決定的な制御フローで管理する。Use when AIへ複数ステップの編集、build、test、修正をまとめて任せ、例外時だけ人間へ引き継ぐとき。Don't use for envelope外の権限取得、不可逆操作の自動承認、状態を保存できない一回限りの危険操作。
```

#### 状態

```text
planned
→ running
→ retrying
→ awaiting-elevation
→ awaiting-result-gate
→ completed
→ failed
→ blocked
→ stopped
```

#### 制御ルール

```text
IF envelope内で処理できる:
  自律実行を継続

IF retry可能な失敗が起きた:
  retry budget内で修正・再実行

IF envelopeにない能力が必要:
  pauseして構造化された権限申請を作成

IF 境界違反を検出:
  即時停止して証拠を保存

IF 不可逆な副作用が必要:
  人間承認へ移行

IF 成果物が完成:
  result gateへ提出
```

LLMは修正候補を生成できますが、再試行回数、タイムアウト、権限判定、停止条件は決定的なコードで管理します。

### `agent-boundary-adversary`

#### 目的

AIが自制しなくても、境界外へ影響が出ないことを確認します。

#### description案

```yaml
description: 隔離済みのAI実行環境に対して、ファイル、認証情報、ネットワーク、コマンド、リソース、依存関係、副作用の境界テストを行い、実測結果を記録する。Use when guest VM、sandbox、restricted interpreterの境界を本番利用前または設定変更後に検証するとき。Don't use for 隔離されていないホスト、実データを使う破壊試験、AIが命令を拒否したことだけを根拠とする安全判定。
```

#### テストクラス

- mount
- credential
- network
- command path
- resource exhaustion
- supply chain
- external side effect
- duplicate execution
- interruption and cleanup

#### 判定

- `PASS`
- `FAIL`
- `BLOCKED`
- `UNVERIFIED`

`PASS`は、対象host、runtime、manifest、テスト条件の組み合わせに限定します。

### `agent-result-gate`

#### 目的

隔離環境から出てくる成果物を未信頼として検査し、取り込み可否を決めます。

#### description案

```yaml
description: AIエージェントが生成したpatch、コード、アーカイブ、依存関係、ログ、実行要求を未信頼成果物として検査し、取り込み、要レビュー、拒否、未検証を判定する。Use when 隔離環境の成果物をホスト、リポジトリ、CI、外部システムへ移す前に確認するとき。Don't use for 生成したAI自身による最終承認、検査なしの自動適用、一般的なスタイルレビュー。
```

#### 検査対象

- path traversal
- symlink
- ファイル形式・サイズ・数
- 実行可能ファイル
- 秘密情報
- 依存関係とinstall script
- 外部通信
- 削除・上書き処理
- Git差分
- テスト結果
- 実行権限
- ロールバック可能性

#### 判定

| 状態 | 意味 |
|---|---|
| `IMPORTABLE` | 定義済み条件を満たす |
| `REVIEW_REQUIRED` | 人間の判断が必要 |
| `REJECTED` | 明確な違反がある |
| `UNVERIFIED` | 必要な検査を実行できていない |

### `failure-to-guardrail`

#### 目的

観測した失敗を、次回も機能するテストと制約へ変換します。

#### description案

```yaml
description: AIエージェントの失敗ログ、境界違反、ヒヤリハットから最小再現条件を抽出し、回帰テスト、権限制約、network rule、承認条件、停止条件へ変換して再検証する。Use when AI実行や境界テストで具体的な失敗が観測され、再発防止策を機械的なガードレールへ落とすとき。Don't use for 失敗証拠のない一般的な安全助言、責任追及、未実行の対策を検証済みと宣言するとき。
```

#### 変換例

| 観測した失敗 | ガードレール |
|---|---|
| 許可外パスへの書込み | mount設定と境界テスト |
| credential読取り | secret非注入とダミーcredentialテスト |
| 許可外通信 | network allowlist |
| 大量変更 | ファイル数・差分量の上限 |
| 終了しない処理 | timeoutとwatchdog |
| 二重実行 | 冪等性テスト |
| 危険なdependency | lockfile・install script検査 |
| 無断の外部書込み | brokered-writeと別承認 |

#### 完了条件

- 最小再現ケースがある
- 新しいガードレールが適用されている
- 同じ条件で違反が再発しない
- 正常系が壊れていない
- 実行ログと設定差分が保存されている

### `agent-near-miss-review`

#### 目的

事故やヒヤリハットを、個人の責任追及ではなく境界改善へつなげます。

#### description案

```yaml
description: AIエージェント利用中の事故やヒヤリハットについて、観測事実、影響範囲、停止要因、偶然守られた点、再現条件、恒久対策を整理し、ガードレール改善へ接続する。Use when AIによる想定外の変更、外部通信、秘密情報アクセス、権限逸脱が発生または発生しかけたとき。Don't use for 個人評価、懲戒判断、法的責任の確定、証拠のない原因断定。
```

#### 出力

- 観測事実
- 推測と未確認事項
- 影響範囲
- 停止要因
- 偶然無事だった点
- 再現条件
- 即時対応
- 恒久対策候補
- `failure-to-guardrail`への引き継ぎ条件

### `agent-safety-onboarding`

#### 目的

初心者へ一度に大きな権限を渡さず、段階的にAIエージェントの扱いを学習させます。

#### description案

```yaml
description: AIに慣れていない開発者へ、no-exec、read-only、isolated-execution、result gateの順で安全な利用方法を演習させ、各段階の理解と境界確認を記録する。Use when 開発チームへAIエージェントを段階的に導入し、実行権限を広げる前に基本操作とリスクを学んでもらうとき。Don't use for 本番権限の自動付与、セキュリティ認証、経験だけを根拠とする隔離工程の省略。
```

#### 学習段階

1. 説明とコード案
2. 読み取り専用の調査
3. 隔離環境でpatch生成
4. 隔離環境でbuild・test
5. result gateを通した取り込み
6. 個別承認を伴う外部操作
