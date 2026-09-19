# Changelog

このプロジェクトの注目すべき変更を記録します。

形式は[Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)を参考にし、バージョン番号は[Semantic Versioning](https://semver.org/lang/ja/)に従います。

## [Unreleased]

### 追加

- `RUN_CREATED`と`STATE_TRANSITION`を記録・再生するreplay-first safety monitor prototype
- owner-only Unix socket、append-only NDJSON、plain-text snapshotによるPhase 0 vertical slice
- event contract、filesystem境界、IPC認証、terminal安全性を対象とする自動テスト
- リアルタイム可視化とTUI-first方針のDesign Doc
- 1 runをsequence cursorで追従するread-only `watch` subcommand（TTY固定ANSI redraw、非TTY/`NO_COLOR` ANSI-free出力）
- batch単位commit、一時read failureからの同一cursor復帰、idle frame抑制、100件timelineを検証するdeterministic test
- immutable `MonitorViewModel` v1と512 KiB上限のsanitized JSONL watch format
- Bun専用のprivate OpenTUI 0.5.11 read-only adapter（TTY responsive表示、非TTY/`NO_COLOR` text fallback）
- strict protocol、40/80/120 columns in-memory renderer、shutdown、event-log不変性のBun tests
- durableな既存runだけを対象にするhost-only `open-viewer` launcher（`auto` / `manual` / `off`、tmux detached split、duplicate pane tag、shell-safe manual command）
- artifact rootを含むowner-only one-shot control manifestのstrict検証と、Bun/frozen dependency不在時のisolated absolute-bootstrap Python text watch fallback

### 変更

- supervisorの状態遷移を機械可読な単一定義へ移し、既存CLIとmonitorで共有

### 検証範囲

- Python 3.11と3.14でproject validatorおよび自動テストを実行（最新件数はvalidation実行結果を参照）
- Bun 1.3.14でOpenTUI adapterのfrozen install、typecheck、自動テストを実行
- vertical slice、read-only snapshot replay、TTY/非TTYのone-run live watchが成功
- launcherのinvalid run拒否、no-tmux/manual/off、strict tmux session identity、detached split、duplicate suppression、root/control分離、environment scrub、fallback、event/artifact tree・metadata不変性を自動検証。shadow moduleとcross-sessionを含むreal tmux testはopt-in

### 未検証事項

- Claude Code／Codex固有adapter、browser UI、heartbeat、watchからの操作
- capability eventとresult-gate report v2に基づく表示および`COMPLETED`判定
- Windows IPC、複数writer、ack喪失時の再送、partial-tail修復/quarantine
- OpenTUI adapterのWindows、Linux、Node実行とpackage配布
- launcherのWindows、tmux以外のmultiplexer、同時launch raceに対する排他的なduplicate保証

## [0.1.0] - 2026-09-19

### 追加

- 境界内での自律実行を管理する10個のAgent Skills
- タスク分類、Autonomy Envelope、host隔離、実行監督、境界テスト、成果物検査、再発防止、ヒヤリハット分析、オンボーディングの各ワークフロー
- Safety Case、Autonomy Envelope、result gate、境界テスト、状態遷移のテンプレートと検証CLI
- プロジェクト構造とmetadataを検査する`validate-project.py`
- 26件の自動テストとGitHub Actions CI
- Vercel Labsの`skills` CLIを使ったインストール手順
- 目的別に分割した設計ドキュメント

### 検証範囲

- 10個のスキルが`skills` CLIから検出・インストールできることを確認
- Python 3.11以降の標準ライブラリだけで検証CLIとテストが動作することを確認
- 他プロジェクトのAgent Skillへ依存しないことを確認

### 未検証事項

- guest VMまたはコンテナを使ったOSレベルの境界
- credential brokerとnetwork policyの統合
- host-side result gateを含む実環境でのend-to-end実行

[0.1.0]: https://github.com/53able/agent-safety-lifecycle/releases/tag/v0.1.0
