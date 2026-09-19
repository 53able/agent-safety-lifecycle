# Changelog

このプロジェクトの注目すべき変更を記録します。

形式は[Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)を参考にし、バージョン番号は[Semantic Versioning](https://semver.org/lang/ja/)に従います。

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
