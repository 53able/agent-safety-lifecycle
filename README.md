# Agent Safety Lifecycle

AIエージェントへ**最小限の能力境界の内側で、最大限の自律性を与える**ためのAgent Skills集です。

人間がコマンドごとに承認する代わりに、タスク開始時に許可範囲を固定します。その範囲内では、調査、編集、依存関係の導入、ビルド、テスト、修正、再試行までAIが自律的に進めます。人間へのハンドオフは、権限の拡張、不可逆な副作用、境界違反、証拠不足が発生した場合に限定します。

> Maximum autonomy inside a minimum capability envelope.

## インストール

このリポジトリは、Vercel Labsの[`skills`](https://github.com/vercel-labs/skills) CLIからインストールする前提で構成しています。Node.jsが利用できる環境で、`npx`から実行してください。

### 収録スキルを確認する

インストール前に、検出されるスキルを一覧表示できます。

```bash
npx skills add 53able/agent-safety-lifecycle --list
```

このリポジトリからは10個のスキルが検出されます。

### すべてのスキルをプロジェクトへインストールする

スキル同士が連携するため、通常は一式のインストールを推奨します。

```bash
npx skills add 53able/agent-safety-lifecycle --skill '*'
```

プロジェクトインストールが既定です。CLIが利用可能なコーディングエージェントを検出し、インストール先とsymlinkまたはcopyを選択する画面を表示します。

確認なしで、検出したエージェントへ一式をインストールする場合は次のようにします。

```bash
npx skills add 53able/agent-safety-lifecycle --all
```

### 対象エージェントを指定する

`--agent`または`-a`でインストール先を限定できます。

```bash
# Claude Code
npx skills add 53able/agent-safety-lifecycle --skill '*' -a claude-code

# Codex
npx skills add 53able/agent-safety-lifecycle --skill '*' -a codex

# Cursor
npx skills add 53able/agent-safety-lifecycle --skill '*' -a cursor

# Pi
npx skills add 53able/agent-safety-lifecycle --skill '*' -a pi
```

エージェント名とインストール先は、[`skills`のSupported Agents一覧](https://github.com/vercel-labs/skills#supported-agents)で確認できます。

### グローバルにインストールする

複数のプロジェクトから利用する場合は、`--global`または`-g`を付けます。

```bash
npx skills add 53able/agent-safety-lifecycle --skill '*' -g
```

チームで同じ構成を共有する場合は、まずプロジェクトインストールを選び、インストールされた設定と`skills-lock.json`をリポジトリで管理する方法が向いています。

### 特定のスキルだけをインストールする

個別に試す場合は、`--skill`を指定します。

```bash
npx skills add 53able/agent-safety-lifecycle \
  --skill agent-task-risk-classifier \
  --skill agent-autonomy-envelope \
  --skill agent-host-isolation
```

`agent-safety-lifecycle`は他の収録スキルへ処理を振り分けるルーターです。ルーターを使う場合は、原則として全スキルをインストールしてください。

### CIやセットアップスクリプトからインストールする

`--yes`で確認を省略できます。対象エージェントを明示すると、非対話環境でもインストール先が曖昧になりません。

```bash
npx skills add 53able/agent-safety-lifecycle \
  --skill '*' \
  --agent codex \
  --yes
```

### インストールを確認する

```bash
npx skills list
```

特定エージェントだけを確認する場合は、`--agent`を付けます。

```bash
npx skills list --agent codex
```

### 更新する

プロジェクトへインストールしたスキルを更新します。

```bash
npx skills update -p
```

特定スキルだけを更新する場合は名前を指定します。

```bash
npx skills update agent-autonomy-envelope agent-result-gate -p
```

## 推奨する使い始め方

インストール後は、コーディングエージェントへ次のように依頼します。

```text
このタスクをagent-safety-lifecycleで分類し、
必要最小限のAutonomy Envelopeを作成してください。
境界内で完了できる処理は自律的に進め、
権限拡張または不可逆操作が必要な場合だけ停止してください。
```

小さく試す場合は、次の順番で始めます。

1. `agent-task-risk-classifier`でタスクを分類する
2. `agent-autonomy-envelope`で許可能力と禁止能力を固定する
3. `agent-host-isolation`で実行境界を設計・検証する
4. `agent-run-supervisor`で境界内の実行と再試行を管理する
5. `agent-result-gate`で成果物を検査する

## 収録スキル

| Skill | Responsibility |
|---|---|
| `agent-safety-lifecycle` | ワークフロー全体のルーティングとsafety caseの管理 |
| `agent-task-risk-classifier` | タスクに必要な最小実行profileの選択 |
| `agent-autonomy-envelope` | タスク単位の許可能力・禁止能力・上限の固定 |
| `agent-host-isolation` | host、mount、network、credential、resource境界の設計と検証 |
| `agent-run-supervisor` | 自律実行、再試行、pause/resume、停止条件の管理 |
| `agent-boundary-adversary` | 境界を意図的に攻撃する否定テスト |
| `agent-result-gate` | 未信頼成果物の検査と取り込み判定 |
| `failure-to-guardrail` | 観測した失敗の回帰テスト・制約への変換 |
| `agent-near-miss-review` | ヒヤリハットの非懲罰的な分析 |
| `agent-safety-onboarding` | 初心者向けの段階的な権限拡張演習 |

各スキルは`skills/<skill-name>/SKILL.md`にあります。スキル固有のテンプレート、参照資料、決定的な検査CLIは、それぞれの`assets/`、`references/`、`scripts/`に配置しています。

設計ドキュメントは[設計概要](docs/design.md)を入口に、[アーキテクチャ](docs/architecture.md)、[スキルカタログ](docs/skill-catalog.md)、[自律実行とハンドオフ](docs/autonomy-and-handoffs.md)、[検証戦略](docs/validation.md)、[実装ロードマップ](docs/implementation-roadmap.md)、[リアルタイム可視化設計](docs/realtime-visualization-design.md)へ分割しています。

## バージョニング

このリポジトリ全体を一つのスキルスイートとして[Semantic Versioning](https://semver.org/lang/ja/)で管理します。`pyproject.toml`の`project.version`をバージョンの正本とし、Gitタグには`v`接頭辞を付けます。

`1.0.0`より前は、次の基準で更新します。

- **minor**：スキルの追加、公開契約やschemaの互換性を壊す変更
- **patch**：後方互換な修正、検証強化、ドキュメント更新

`1.0.0`以降は、互換性を壊す変更でmajorを更新します。変更履歴と未検証事項は[CHANGELOG](CHANGELOG.md)で確認できます。

## Security boundary

Agent Skillsは手順と判断規則を提供しますが、OSレベルの強制境界ではありません。実際の隔離には、guest VM、read-only mount、network policy、credential broker、resource limit、host-side result gateなどが必要です。

次を安全性の根拠にしないでください。

- プロンプトで禁止したこと
- AIが危険な操作を拒否したこと
- コンテナを使用したことだけ
- 正常なbuildが一度成功したこと
- 未実施の検査

検証結果は、対象host、runtime、manifest、テスト条件の組み合わせに限定してください。

## リポジトリの開発

ここからは、スキルを利用する人ではなく、このリポジトリ自体を変更する人向けです。Python 3.11以降と標準ライブラリだけを使用します。

```bash
git clone https://github.com/53able/agent-safety-lifecycle.git
cd agent-safety-lifecycle
python3 scripts/validate-project.py
python3 -m unittest discover -s tests -v
```

### Read-only safety monitor development tool

`tools.safety_monitor`はリポジトリ開発者向けのPOSIX-oriented development toolです。Skills CLIの配布物やinstalled console scriptではありません。次のコマンドは、認証済みUnix socket経由で`RUN_CREATED`と`PLANNED -> RUNNING`を記録し、保存ログのone-shot snapshotを表示した後、同じ1 runをread-onlyで追従します。

```bash
MONITOR_PARENT="$(mktemp -d)"
EVENT_ROOT="$MONITOR_PARENT/events"
ARTIFACT_ROOT="$MONITOR_PARENT/artifacts"
python3 -m tools.safety_monitor vertical-slice \
  --allowed-parent "$MONITOR_PARENT" \
  --event-root "$EVENT_ROOT" \
  --artifact-root "$ARTIFACT_ROOT" \
  --task-id demo-task \
  --run-id demo-run \
  --envelope-hash "sha256:0000000000000000000000000000000000000000000000000000000000000000"
python3 -m tools.safety_monitor snapshot \
  --allowed-parent "$MONITOR_PARENT" \
  --event-root "$EVENT_ROOT" \
  --run-id demo-run
python3 -m tools.safety_monitor watch \
  --allowed-parent "$MONITOR_PARENT" \
  --event-root "$EVENT_ROOT" \
  --run-id demo-run
# Ctrl-Cで終了します（exit status 130）。
```

`--allowed-parent`は既存の明示的なallowlist境界です。event/artifact rootはその配下で互いに重ならないowner-only directoryに限定され、`/`、home、allowlist外、symlinkは拒否されます。既存rootのpermissionは変更しません。

このincrementはPOSIX、single writer、現行の`RUN_CREATED` / `STATE_TRANSITION` schemaだけを対象とします。`watch`は1 runをsequence cursorでpollし、毎回8 MiB以下のlog全体を1回のcoherent readで取得して完全にreplayします。commit済みcursor以前のeventがin-memory historyと完全一致することも確認し、その後でcursor後のsuffixだけをcommitします。timelineは最新100件です。完全な新規batchがvalidな場合だけ表示とcursorを更新し、idle pollではframeを重複出力しません。不完全な末尾や一時的なread failureでは最後のvalid表示とcursorを保ち、同じcursorから再開します。恒久的な破損や同一process中のprefix rewriteは非zeroで終了し、新しいframeを出しません。tail修復やquarantineは行いません。

TTYかつ`NO_COLOR`が未設定の場合だけ、固定ANSI clear/home prefixで再描画します。非TTYまたは`NO_COLOR`が存在する場合は、ANSI-free snapshotを追記します。どちらもevent由来のcontrol文字をescapeします。viewerはread-onlyで、heartbeat、keybinding、承認・停止・retry操作、browser、複数run、runtime固有adapterを持ちません。capability eventとresult-gate event/v2 evidenceは現行schemaにないため、画面には利用不可の静的placeholderを表示し、観測したとは扱いません。

任意のPhase 3.1 OpenTUI表示はprivateなBun開発packageです。Python側が検証・replay・sanitization・projectionを引き続き単独で所有し、OpenTUI側はversioned JSONL view modelだけを読みます。Bun 1.3.0以上（検証版1.3.14）が必要で、Node 24は非対応です。

```bash
cd tools/opentui_monitor
bun install --frozen-lockfile
bun run src/main.ts \
  --allowed-parent "$MONITOR_PARENT" \
  --event-root "$EVENT_ROOT" \
  --run-id demo-run
```

TTYでは40/80/120 columnsに応答するread-only OpenTUIを表示します。非TTYまたは`NO_COLOR`ではrendererを作らず、既存Python text watchへ委譲します。操作はCtrl-Cによる終了だけです。直接bridge contractを確認する場合はPython watchへ`--format view-model-jsonl`を指定します。

replayは1行64 KiB、合計8 MiBを上限とします。`Stream: OK`はschema、連続sequence、状態遷移が構造上validであり、同一`watch` processがすでにcommitしたprefixも変化していないという意味です。これはin-processの履歴整合性検出であってdurable tamper proofではありません。process再起動時は、その時点のvalidなbounded historyを現在履歴として信頼します。result-gate report v2がないため`COMPLETED`は拒否します。monitorはsandbox、承認機構、完了証明を提供しません。既知のcredential patternは保存前に拒否しますが、未知形式の秘密情報は検出できない残存リスクがあります。

## 関連資料

- [`skills` CLI](https://github.com/vercel-labs/skills)
- [Agent Skills specification](https://agentskills.io)
- [設計概要](docs/design.md)
- [アーキテクチャ](docs/architecture.md)
- [スキルカタログ](docs/skill-catalog.md)
- [自律実行とハンドオフ](docs/autonomy-and-handoffs.md)
- [検証戦略](docs/validation.md)
- [実装ロードマップ](docs/implementation-roadmap.md)
- [リアルタイム可視化設計](docs/realtime-visualization-design.md)
- [変更履歴](CHANGELOG.md)

## License

[MIT](LICENSE)
