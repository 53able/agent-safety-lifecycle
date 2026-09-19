# 検証戦略

[設計概要](design.md) · [アーキテクチャ](architecture.md) · [スキルカタログ](skill-catalog.md) · [自律実行とハンドオフ](autonomy-and-handoffs.md) · [検証](validation.md) · [実装ロードマップ](implementation-roadmap.md)

代表ケース、意図的に危険なbad-version、受入条件、残存リスクをまとめます。未実施の検査は合格として扱いません。

## 代表ケース

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

## Bad-versionテスト

スキル群の評価では、意図的に危険な版も用意します。

- すべてのタスクを`isolated-execution`へ送る分類器
- credentialをそのままguestへ渡すenvelope
- AIが拒否しただけで`PASS`にする境界テスト
- `UNVERIFIED`を`IMPORTABLE`へ変えるresult gate
- retry上限のないsupervisor
- 失敗証拠なしでガードレールを作るスキル
- production deployを正常系として自動承認するrouter

危険な版を確実に拒否できることを評価します。

## 受入条件

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

## 残存リスク

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

## Replay-first monitor prototypeの検証

[リアルタイム可視化設計](realtime-visualization-design.md)の最初のincrementは、Python 3.11以降をsupport targetとし、標準ライブラリだけを使用します。CI結果は各runで確認します。以下は再現用の一般形であり、この変更に対して実行したPython 3.11.14と3.14.6のlocal matrix結果は後段の検証記録に明記します。

```bash
python3 scripts/validate-project.py
python3 -m unittest discover -s tests -v

DEMO_ROOT="$(mktemp -d)"
python3 -m tools.safety_monitor vertical-slice \
  --allowed-parent "$DEMO_ROOT" \
  --event-root "$DEMO_ROOT/events" \
  --artifact-root "$DEMO_ROOT/artifacts" \
  --task-id demo-task \
  --run-id demo-run \
  --envelope-hash "sha256:0000000000000000000000000000000000000000000000000000000000000000"
python3 -m tools.safety_monitor snapshot \
  --allowed-parent "$DEMO_ROOT" \
  --event-root "$DEMO_ROOT/events" \
  --run-id demo-run
python3 -m tools.safety_monitor watch \
  --allowed-parent "$DEMO_ROOT" \
  --event-root "$DEMO_ROOT/events" \
  --run-id demo-run
# Ctrl-C: exit status 130
```

期待値は2 event、sequence `1, 2`、source `validator`、最終state `RUNNING`、stream `OK`です。ここで`OK`はschema、連続sequence、projectionの構造検査に通ったことだけを表し、logの真正性や改ざん耐性を証明しません。snapshotとwatchはevent storeへ書き込みません。testsは、control/bidi文字、既知secret pattern、unknown field、source spoof、bad token、unsafe/overlapping root、audit pathのsymlink、oversized request、bounded replay、cursor以前の破損、欠番、不完全tail、初回append失敗後のretry、terminal後event、result-gate v2なしのcompletionを反証します。

watch component testsはwall-clock sleepを使わず、reader、waiter、output、ANSI modeを注入します。initial replay、idle時のduplicate suppression、一時read failure後の同一cursorからの復帰、batch単位のprojection commit、run isolation、100件timeline、固定ANSI prefix、非TTY/`NO_COLOR`のANSI-free出力、terminal injection、Ctrl-C 130を検査します。手動確認では、TTY上のredrawとCtrl-C、pipeおよび`NO_COLOR=1`でのESC byte不在を確認し、それぞれの前後で`events.ndjson`のSHA-256が同一であることを確認します。

対象はPOSIX owner-only `AF_UNIX` ingress、単一writer、1 runのread-only pollingです。replay上限は1行64 KiB、1 log 8 MiBで、pollごとにbounded log全体を検査します。同一event rootへの複数writer、ack喪失時の再送、partial-tail修復/quarantine、cryptographic tamper detection、heartbeat、操作keybinding、browser、runtime固有adapterは未対応です。現行schemaはcapability/result-gate eventを持たないため、表示は静的なunavailable placeholderだけです。既知のcredential patternは保存前に拒否しますが、未知形式の秘密情報は検出できません。恒久的な破損と`COMPLETED`はfail closedにします。この開発toolはsandbox、承認、result-gate v2、Skills CLI配布を検証しません。

### Phase 3.1 OpenTUI adapterの検証

Python 3.14とBun 1.3.14で次を実行する。Node 24はOpenTUI 0.5.11の要求（Node 26.4.0以上）を満たさないため使用しない。

```bash
python3 scripts/validate-project.py
python3 -m unittest discover -s tests -v
python3 -m compileall -q tools tests scripts skills
cd tools/opentui_monitor
bun install --frozen-lockfile
bun run typecheck
bun test
```

2026-09-20のDarwin arm64実測ではvalidator、Python full suite、compileall、frozen install、typecheck、Bun full suiteが成功した。Bun testsはOpenTUI test renderer上のin-memory 40/80/120 columns（実PTY resizeではない）、strict protocolのsplit/multiple/invalid UTF-8/oversize/partial/injection、update/resize/init/child failure、bounded shutdownとcleanup順序を含む。Python bridgeを直接起動するintegration testでは、前後のevent bytes・SHA-256・directory tree不変を確認した。process testsはすべて`src/main.ts`のpublic entryを起動する。実PTYかつ`NO_COLOR`なしではOpenTUI固有出力を確認し、SIGINT/SIGTERMを無視するchildへの反復SIGINTでstatus 130とchild消滅、uncooperative childのprotocol failureでstatus 1を確認した。PTY slave fdをprocess起動前に複製し、process終了後に`tcgetattr`全体が起動前と一致することをterminal restoration invariantとして両経路でassertし、`ICANON`と`ECHO`も個別にassertした。実PTYの`NO_COLOR`と非TTYではraw text出力によりpublic fallbackを確認した。public-entry PTY/non-TTY経路と実event storeを組み合わせた不変性検査は未実施である。Windows、Linux、Nodeでの実行は未検証である。

### Existing-run viewer launcherの検証

公開entryは次で検証する。通常suiteはtmuxの有無へ依存せず、real tmux検査だけを明示opt-inにする。

```bash
python3 -m unittest tests.test_monitor_viewer_launcher -v
RUN_REAL_TMUX_TESTS=1 python3 -m unittest \
  tests.test_monitor_viewer_launcher.ViewerLauncherTests.test_real_tmux_detached_split \
  tests.test_monitor_viewer_launcher.ViewerLauncherTests.test_real_tmux_rejects_cross_session_pane_on_same_server -v
```

通常testはmissing/corrupt/invalid runでlaunchしないこと、`manual`/`off`、tmux不在時のshell-safe manual result、strictな`TMUX` identity、same-server cross-session pane拒否、確認済みtmuxでのdetached split、current paneとの分離、pane tagによるduplicate suppressionを検査する。spaceとshell metacharacterを含むpathはcommandとして評価せずdataとして扱い、run IDは既存schemaのstrict ID検証を維持する。control manifestについてowner-only directory/file、artifact rootを含むstrict field集合、canonical parent/event/artifact/runの再検証、symlink・permission・schema・path attackの拒否、consume後のunlinkを検査する。event/artifact rootは既存owner-only・相互非包含を要求し、作成もchmodもせず、予約control directoryとのexact/nested collisionを拒否する。

initial skill bootstrapはhost/config提供のabsolute trusted checkoutにある`tools/safety_monitor_bootstrap.py`をabsolute trusted Pythonから`-I`で起動する。checkoutはsupervised agentのwritable root外、expected owner、group/other書込み不可、承認済みpinned revisionまたはdigest一致を前提とし、不足・検証不能時はeventを合成せず`monitor unavailable`とする。通常suiteのpublic-entry integration testはhostile cwdとhostile `PYTHONPATH` shadow packageからこのexact bootstrap subprocessを`manual` modeで起動し、sentinel非実行を確認する。

信頼済みinitial bootstrapの後、Bun missingとfrozen dependency missingではviewer child用のabsolute bootstrapを`python -I`で実行するPython text watchへfallbackし、利用可能なBun経路は既存OpenTUI public entryだけをexecする。child bootstrapの隔離はinitial bootstrapのtrust前提を代替しない。viewer process環境は必要な非secret変数だけへallowlistし、任意credentialを除外する。public `open-viewer` integration testはeventとartifact双方のtree、file bytes、SHA-256、mode・owner・size・mtime metadataが前後で同一であることを検査する。control manifestはevent/artifact rootの外にある専用directoryだけへ一時作成される。real tmux testsは`RUN_REAL_TMUX_TESTS=1`かつtmuxがある場合だけtemporary sessionsを使う。detached split testもhostile cwd/PYTHONPATHからexact initial bootstrap subprocessを起動し、shadow package非実行、canonical repository cwdを確認する。もう1件はsame-server cross-sessionを拒否する。通常suiteでは両方をskipする。

2026-09-20のDarwin arm64実測では、Python 3.11.14と3.14.6のfull suiteはいずれも109 tests中107成功・通常のreal-tmux 2件skipで、既存91 testsを含めて成功した。real tmux opt-in testsも2件成功した。project validator、compileall、diff-checkも成功した。Bun 1.3.14はfrozen install（16 installs / 24 packages、変更なし）、typecheck、24 testsが成功した。

この検査はpane optionをsecurity boundaryや排他的lockとして証明しない。同時launcher間のrace、tmux以外のterminal multiplexer、Terminal.app/iTerm、generic Claude/Codex hook、agent command execution、approval/control操作は対象外である。viewer availabilityと失敗はrun stateへ影響しない。

### Full-history replayの計算量回帰

自動回帰テストは16,000件のalternating historyを使い、producer ID accumulatorへの追加がeventごとに1回、immutable `frozenset`化がreplay終了時に1回だけであることを構造的に検査します。wall-clock値は環境差で不安定なためassertせず、性能保証も行いません。filesystem read、NDJSON parse、renderを含む再現可能な性能benchmarkは後続課題です。
