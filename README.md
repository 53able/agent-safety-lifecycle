# Agent Safety Lifecycle

AIエージェントへ**最小限の能力境界の内側で、最大限の自律性を与える**ためのAgent Skills集です。

人間がコマンドごとに承認する代わりに、タスク開始時に許可範囲を固定し、その範囲内では調査、編集、依存関係の導入、ビルド、テスト、修正、再試行まで自律的に進めます。人間へのハンドオフは、権限の拡張、不可逆な副作用、境界違反、証拠不足が発生した場合に限定します。

> Maximum autonomy inside a minimum capability envelope.

## Skills

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

各スキルは `skills/<skill-name>/SKILL.md` にあります。スキル固有のテンプレート、参照資料、決定的な検査CLIは、それぞれの `assets/`、`references/`、`scripts/` に配置しています。

設計思想、状態遷移、ハンドオフ方針、受入条件は[設計ドキュメント](docs/design.md)にまとめています。

## Quick start

### 1. タスクを分類する

```bash
cp skills/agent-task-risk-classifier/assets/task-risk-input.template.json /tmp/task-risk.json
python3 skills/agent-task-risk-classifier/scripts/classify-task.py /tmp/task-risk.json
```

### 2. Autonomy Envelopeを検証する

```bash
cp skills/agent-autonomy-envelope/assets/autonomy-envelope.template.json /tmp/envelope.json
python3 skills/agent-autonomy-envelope/scripts/validate-envelope.py /tmp/envelope.json
```

### 3. Project全体を検証する

```bash
python3 scripts/validate-project.py
python3 -m unittest discover -s tests -v
```

## Security boundary

Agent Skillsは手順と判断規則を提供しますが、OSレベルの強制境界ではありません。実際の隔離には、guest VM、read-only mount、network policy、credential broker、resource limit、host-side result gateなどが必要です。

次を安全性の根拠にしないでください。

- プロンプトで禁止したこと
- AIが危険な操作を拒否したこと
- コンテナを使用したことだけ
- 正常なbuildが一度成功したこと
- 未実施の検査

検証結果は、対象host、runtime、manifest、テスト条件の組み合わせに限定してください。

## Development

Python 3.11以降と標準ライブラリだけを使用します。

```bash
python3 scripts/validate-project.py
python3 -m unittest discover -s tests -v
```

## License

[MIT](LICENSE)
