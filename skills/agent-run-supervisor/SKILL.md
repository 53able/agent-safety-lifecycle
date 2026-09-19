---
name: agent-run-supervisor
description: 承認済みのautonomy envelope内でAIタスクを実行し、状態、再試行、タイムアウト、pause、resume、失敗、成果物提出を決定的な制御フローで管理する。Use when AIへ複数ステップの編集、build、test、修正をまとめて任せ、例外時だけ人間へ引き継ぐとき。Don't use for envelope外の権限取得、不可逆操作の自動承認、状態を保存できない一回限りの危険操作。
---

# Agent Run Supervisor

## 手順

**Step 1: 実行前提を固定する**
1. 検証済みAutonomy Envelope、実行環境、停止条件、retry budget、期待成果物を読み込む。
2. `assets/run-state.template.json`をコピーし、task IDとenvelope hashを記録する。
3. envelopeまたは実行環境が未検証なら開始せず`BLOCKED`にする。

**Step 2: 状態遷移を管理する**
1. `references/state-machine.md`に定義された遷移だけを使用する。
2. 外部実行基盤またはtrusted adapterがdurableな`RUN_CREATED`をすでに作成し、monitor用の`allowed-parent`、`event-root`、`artifact-root`を固定したconfigが明示的に承認されている場合、supervisor/lifecycleは`<trusted-python> -I <trusted-monitor-checkout>/tools/safety_monitor_bootstrap.py open-viewer --allowed-parent <monitor-parent> --event-root <event-root> --artifact-root <artifact-root> --run-id <run-id> --mode auto`を**MUST（必ず）**自動実行する。`<trusted-python>`と`<trusted-monitor-checkout>`はhost/configが提供するabsolute pathでなければならない。checkoutはsupervised agentのwritable root外に置き、expected ownerでありgroup/otherから書込み不可であること、かつhostが承認したpinned revisionまたはdigestとの一致を起動前に検証する。durable run、承認済みconfig、absolute path、配置、owner、permission、revision/digestのいずれかが欠ける、または検証できない場合は、eventを合成せず`monitor unavailable`を**MUST（必ず）**記録する。cwdから解決されるmodule entrypointを使用してはならない。
3. skill-issued viewer launcherは、信頼済みのinitial bootstrapで既存runを開く任意の読み取り専用表示である。その後のtmux/viewer child bootstrapにもabsolute pathと`-I`を使用するが、これはinitial bootstrapの信頼要件を代替しない。agent commandの実行、汎用runtime観測、Claude Code/Codex hook coverageではない。viewerの失敗や不在は非致命的かつ非 authoritativeで、run stateを変更しない。
4. 実行開始時に`PLANNED`から`RUNNING`へ遷移する。
5. retry可能な失敗では、budget内に限り`RETRYING`へ遷移する。
6. 追加能力が必要なら`AWAITING_ELEVATION`へ遷移し、実行をpauseする。
7. 成果物が完成したら`AWAITING_RESULT_GATE`へ遷移する。
8. 境界違反では即時に`STOPPED`へ遷移し、証拠を保存する。

**Step 3: 遷移を検証する**
1. 状態変更ごとに`python3 scripts/validate-transition.py <from> <to>`を実行する。
2. 不正な遷移を検出した場合は状態を書き換えず、`BLOCKED`として報告する。
3. retry回数と経過時間はモデルの判断ではなく実行コードで計測する。

**Step 4: 完了またはハンドオフする**
1. result gateが`IMPORTABLE`を返した場合だけ`COMPLETED`へ遷移する。
2. 人間へ渡す場合は、必要能力、理由、範囲、有効期限、代替案を構造化して提示する。
3. raw logを丸ごとLLMへ戻さず、retry判断に必要な短いエラーへ圧縮する。

## Error Handling

- state fileを復元できない場合は再実行せず`BLOCKED`にする。
- retry budgetを消費した場合は`FAILED`へ遷移する。
- cleanupに失敗した場合は`COMPLETED`にせず`BLOCKED`として残す。
