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

[リアルタイム可視化設計](realtime-visualization-design.md)の最初のincrementは、Python 3.11以降をsupport targetとし、標準ライブラリだけを使用します。CIはPython 3.11を指定していますが、実行結果は各CI runで確認します。以下のlocal commandをPython 3.11で実行したという意味ではありません。

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

### Full-history replayの計算量回帰

自動回帰テストは16,000件のalternating historyを使い、producer ID accumulatorへの追加がeventごとに1回、immutable `frozenset`化がreplay終了時に1回だけであることを構造的に検査します。wall-clock値は環境差で不安定なためassertせず、性能保証も行いません。filesystem read、NDJSON parse、renderを含む再現可能な性能benchmarkは後続課題です。
