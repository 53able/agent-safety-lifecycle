# AIへ大きな裁量を渡しながら、ハンドオフを減らすスキル群の設計

## 1. 概要

この文書は、AIエージェントへ開発タスクを任せる際に、最終成果物までの人間によるハンドオフを減らすスキル群を設計するものです。

目標は、AIへ無制限の権限を渡すことではありません。タスクごとに被害範囲を閉じ込め、その境界内では調査、編集、依存関係の導入、ビルド、テスト、失敗分析、修正、再試行まで自律的に進められる状態を作ります。

設計原則は次の一文に集約できます。

> **Maximum autonomy inside a minimum capability envelope.**
> 最小限の能力境界の内側で、最大限の自律性を与える。

通常の実行では、人間の関与を次の2回に近づけます。

1. タスクの目的と、自律実行を許可する範囲を承認する
2. 検査済みの最終成果物を確認する

途中で人間を呼ぶのは、許可範囲の変更、不可逆な副作用、境界違反、証拠不足が発生した場合に限ります。

### 1.1 配布とインストールの前提

このスキル群は、Vercel Labsの[`skills`](https://github.com/vercel-labs/skills) CLIからインストールする構成とします。CLIはリポジトリの`skills/`を探索し、各`SKILL.md`を個別のスキルとして検出します。

通常は、内部ルーティングに必要なスキルを欠かさないよう、一式をプロジェクトへインストールします。

```bash
npx skills add 53able/agent-safety-lifecycle --skill '*'
```

特定のエージェントへ限定する場合は`--agent`を指定します。

```bash
npx skills add 53able/agent-safety-lifecycle --skill '*' --agent codex
```

`agent-safety-lifecycle`は同じリポジトリ内の専門スキルへ処理を振り分けるため、ルーターだけを単独でインストールする構成は標準運用にしません。個別インストールは、専門スキルを単独で試す場合に限定します。

## 2. 想定利用者

主な利用者は、AIエージェントへコード変更やコマンド実行を任せたい開発者と、チーム向けのAI実行基盤を整備する担当者です。

特に、次の状況を対象とします。

- AIにbuildやtestまで任せたい
- 依存関係の導入を含む作業を自律化したい
- 逐次承認を減らしたい
- AIの成果物を安全にリポジトリへ取り込みたい
- 失敗を次回のテストや制約へ反映したい
- AI利用のヒヤリハットを組織学習につなげたい

## 3. 解決する問題

AIエージェントへ大きな裁量を渡すと、作業速度は上がります。しかし、同じ端末上でホームディレクトリ、認証情報、ネットワーク、本番環境へ到達できる状態では、ひとつの誤操作が広い範囲へ影響します。

反対に、すべてのコマンドやファイル変更を人間が承認すると、AIは自律的に試行錯誤できません。承認待ちが増え、最終成果物までのハンドオフも増えます。

本設計では、この問題を「権限を与えるか、与えないか」の二択にしません。

```text
広い常設権限 + 逐次確認
```

ではなく、次の構造へ変えます。

```text
狭く固定した被害範囲 + 境界内での広い裁量 + 例外時だけ確認
```

## 4. 非目標

このスキル群は、次の用途を対象にしません。

- AIへroot権限や本番認証情報を常設する
- プロンプトだけで安全性を担保する
- コンテナを使っただけで安全と判定する
- 実データを使って破壊試験を行う
- 未実施の検査を合格扱いする
- AI自身に最終承認を任せる
- 法的責任、懲戒、セキュリティ認証を判断する

`SKILL.md`は実行手順を示せますが、OSレベルの強制境界にはなりません。mount、network policy、credential broker、resource limit、host-side gateなどの実行基盤が別途必要です。

## 5. 基本原則

### 5.1 プロンプトを境界にしない

「このディレクトリ以外は触らないで」という指示は、作業方針としては使えます。しかし、技術的なアクセス制御の代わりにはなりません。

### 5.2 AIが止まることを合格条件にしない

危険な操作をAIが拒否しても、境界が有効だとは証明できません。AIが操作を続けても、保護対象へ到達できないことを確認します。

### 5.3 成果物も未信頼として扱う

隔離環境で生成したコード、patch、アーカイブ、ログ、依存関係は、ホストへ持ち込む前に検査します。

### 5.4 教訓をAIの記憶へ預けない

失敗は、回帰テスト、権限制約、network rule、承認条件、停止条件へ変換します。会話履歴が消えても残る形にします。

### 5.5 正常系は自動、例外だけ人間へ渡す

既定の許可範囲内では自律実行を継続します。人間への質問や承認依頼も、自由文ではなく構造化されたイベントとして記録します。

### 5.6 検証範囲を明示する

「安全」とは表現せず、「このhost、runtime、manifest、テスト条件について検証した」と報告します。

## 6. 全体アーキテクチャ

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

## 7. 正本となる状態文書

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

## 8. 実行profile

### 8.1 `no-exec`

AIは説明、コード案、patch案だけを生成します。コマンドは実行しません。

### 8.2 `read-only`

AIは限定された入力を検索・解析できますが、書込みと任意コマンド実行は許可しません。

### 8.3 `isolated-execution`

短命なguest環境内で、編集、install、build、test、修正、再試行を許可します。ホスト側の認証情報と書込み権限は渡しません。

### 8.4 `brokered-write`

検査済みの一件の操作だけを、host-side brokerが代理実行します。対象、宛先、期限、操作内容を固定します。

### 8.5 `human-gated-impact`

production deploy、削除、課金、公開、権限変更など、影響が大きい操作です。最終操作の前に人間の承認を要求します。

## 9. スキル一覧

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

## 10. 各スキルの設計

### 10.1 `agent-safety-lifecycle`

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

### 10.2 `agent-task-risk-classifier`

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

### 10.3 `agent-autonomy-envelope`

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

### 10.4 `agent-host-isolation`

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

### 10.5 `agent-run-supervisor`

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

### 10.6 `agent-boundary-adversary`

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

### 10.7 `agent-result-gate`

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

### 10.8 `failure-to-guardrail`

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

### 10.9 `agent-near-miss-review`

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

### 10.10 `agent-safety-onboarding`

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

## 11. ハンドオフ設計

### 11.1 自動化する操作

次の操作は、envelope内であれば人間の逐次承認なしで実行できます。

- コード調査
- コード編集
- 承認済みregistryからの依存関係導入
- build
- test
- lint
- 失敗分析
- retry budget内の修正と再実行
- patch生成
- test log生成
- 境界テスト
- result gateへの提出

### 11.2 条件付きで自動化する操作

- 一時worktreeへのpatch適用
- task固有branchへのcommit
- 固定されたrepositoryとbranchへのpush
- stagingへのdeploy

これらは、task-scoped broker、短命な認証情報、宛先固定、監査記録、rollbackを条件とします。

### 11.3 人間承認を残す操作

- production deploy
- データ削除
- 課金
- 公開・送信
- 権限変更
- protected branchへの反映
- envelope自体の拡張
- 検査不能な成果物の取り込み

## 12. 例外時ハンドオフの形式

人間への依頼は自由文ではなく、次の構造で出します。

```yaml
request-type: capability-elevation
status: paused
task: frontend-test-fix
requested-capability: network-access
destination: registry.example.com
protocol: https
port: 443
purpose: download locked dependencies
scope: current-task-only
expires-after: 20m
alternatives-attempted:
  - offline-cache
risk-if-approved:
  - external-content-enters-guest
risk-if-denied:
  - build-cannot-continue
resume-action: rerun-dependency-install
```

利用者は、何を許可するのか、許可しない場合に何が止まるのかを一度で判断できます。

## 13. ディレクトリ構成

各スキルは、agentskills.ioの構成に合わせます。

```text
agent-safety-lifecycle/
├─ SKILL.md
├─ assets/
│  └─ agent-safety-case.template.md
├─ references/
│  └─ routing-matrix.md
└─ scripts/
   └─ validate-safety-case.py

agent-autonomy-envelope/
├─ SKILL.md
├─ assets/
│  └─ autonomy-envelope.template.json
├─ references/
│  └─ capability-catalog.md
└─ scripts/
   └─ validate-envelope.py
```

同じ方針で、各スキルに必要なファイルだけを置きます。人間向けの`README.md`や`CHANGELOG.md`は作りません。

## 14. Progressive Disclosure

各`SKILL.md`には、通常の実行に必要な判断と手順だけを書きます。

次の内容は`references/`へ分離します。

- capability一覧
- リスク分類表
- test classの詳細
- 判定基準
- platform固有の制約
- schema全文
- 長い失敗例

次の内容は`assets/`へ置きます。

- safety case template
- autonomy envelope template
- result gate report template
- near-miss review template

決定的な検査は`scripts/`へ置きます。

- metadata検証
- envelope schema検証
- safety case整合性検証
- artifact path検査
- hash生成
- 状態遷移検証

## 15. 代表ケース

### Case 1：フロントエンドのテスト修正

期待する経路：

```text
isolated-execution
→ build・test・修正を自律実行
→ patchとtest logをresult gateへ提出
→ 合格後に一時worktreeへ取り込み
```

人間の確認は、最初のenvelopeと最終diffを基本とします。

### Case 2：依存関係を調査するだけ

期待する経路：

```text
read-only
→ package metadataを調査
→ 推奨案を出力
```

コマンド実行やVMは不要です。

### Case 3：staging deploy

期待する経路：

```text
isolated-execution
→ build・test
→ result gate
→ brokered-write
→ stagingへ限定deploy
```

宛先、artifact hash、期限、rollbackを固定します。

### Case 4：productionのデータ削除

期待する経路：

```text
human-gated-impact
→ 影響範囲とrollbackを提示
→ pause
→ 人間の明示承認
```

完全自動化しません。

### Case 5：無関係な文章校正

安全実行スキル群を起動しません。通常の文章編集として扱います。

## 16. Bad-versionテスト

スキル群の評価では、意図的に危険な版も用意します。

- すべてのタスクを`isolated-execution`へ送る分類器
- credentialをそのままguestへ渡すenvelope
- AIが拒否しただけで`PASS`にする境界テスト
- `UNVERIFIED`を`IMPORTABLE`へ変えるresult gate
- retry上限のないsupervisor
- 失敗証拠なしでガードレールを作るスキル
- production deployを正常系として自動承認するrouter

危険な版を確実に拒否できることを評価します。

## 17. 受入条件

### 機能面

- タスクから最小profileを選べる
- envelope外の操作を停止できる
- 正常系では途中の人間確認なしで完了できる
- 例外時には構造化された承認依頼を出せる
- 成果物を未信頼として検査できる
- 失敗を再現可能なテストまたは制約へ変換できる

### 証拠面

- host、runtime、manifest、コマンド、結果を記録する
- 未実施項目を`UNVERIFIED`として残す
- 設定変更後に同じ条件で再検証する
- 最終判断が証拠へ追跡できる

### UX面

- 正常系の人間確認は原則2回以下
- 承認依頼は一度で判断できる情報を持つ
- 初心者が`no-exec`から開始できる
- スキル名と出力状態が一貫している

## 18. 実装順序

### Phase 1：最小の自律実行ループ

1. `agent-task-risk-classifier`
2. `agent-autonomy-envelope`
3. `agent-run-supervisor`
4. `agent-safety-lifecycle`

既存の`agent-host-isolation`を利用し、分類から隔離実行、最終成果物までをつなぎます。

### Phase 2：昇格と境界検証

5. `agent-result-gate`
6. `agent-boundary-adversary`

成果物と実行境界の検査を独立させます。

### Phase 3：学習ループ

7. `failure-to-guardrail`
8. `agent-near-miss-review`

失敗を再発防止策へ変換します。

### Phase 4：導入支援

9. `agent-safety-onboarding`

初心者向けの演習と段階的な権限拡張を追加します。

## 19. 残存リスク

- 実行基盤自体に脆弱性がある可能性
- result gateで未知の悪意ある成果物を検出できない可能性
- supply chain経由で危険なコードが入る可能性
- 自動検査への過信
- 大量差分によるレビュー疲労
- policy設定者の誤り
- brokerの権限が広すぎる可能性
- ログへ秘密情報が残る可能性
- 利便性の低い統制を利用者が迂回する可能性

これらは、スキルの存在だけでは解消しません。対象環境での実測、短命な権限、監査、定期的な境界テストが必要です。

## 20. 未決定事項

- 最初に対応する実行基盤をVM、Apple Container、Dockerのどれにするか
- `agent-run-supervisor`を特定のエージェントランタイムへ依存させるか
- branchへの自動commitを既定で許可するか
- staging deployを標準profileに含めるか
- safety caseのschemaをMarkdown中心にするか、JSON中心にするか
- 複数エージェントが同じenvelopeを共有できるか
- profileの有効期限と再検証間隔をどう決めるか

## 21. 次のアクション

最初に`agent-task-risk-classifier`、`agent-autonomy-envelope`、`agent-run-supervisor`の3スキルを試作します。

試作時には、次の最小ケースだけを対象にします。

```text
機密情報を含まない小規模リポジトリ
+ 短命な隔離環境
+ buildとtest
+ patchとtest logの出力
+ 外部書込みなし
```

このケースで、最初の承認後にAIが修正と再試行を自律的に進め、最後に検査可能なpatchを提示できるかを評価します。

## 関連資料

実行場所、権限、成果物の取り込み口に関する既存の説明は、[Agent Host Isolation](https://github.com/53able/agent-host-isolation)で確認できます。

境界を実測する際の考え方は、[adversarial testと検証状態](https://github.com/53able/agent-host-isolation/blob/main/docs/ja-JP/mechanisms/06-adversarial-verification.md)を参照します。成果物や外部操作をホスト側で仲介する構成は、[result gateとhost-side broker](https://github.com/53able/agent-host-isolation/blob/main/docs/ja-JP/mechanisms/04-result-gate-and-broker.md)に対応します。
