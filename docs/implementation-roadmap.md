# 実装ロードマップ

[設計概要](design.md) · [アーキテクチャ](architecture.md) · [スキルカタログ](skill-catalog.md) · [自律実行とハンドオフ](autonomy-and-handoffs.md) · [検証](validation.md) · [実装ロードマップ](implementation-roadmap.md)

スキルのファイル構成、Progressive Disclosure、実装順、未決定事項、次のアクションをまとめます。

## ディレクトリ構成

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

## Progressive Disclosure

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

## 実装順序

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

## 未決定事項

- 最初に対応する実行基盤をVM、Apple Container、Dockerのどれにするか
- `agent-run-supervisor`を特定のエージェントランタイムへ依存させるか
- branchへの自動commitを既定で許可するか
- staging deployを標準profileに含めるか
- safety caseのschemaをMarkdown中心にするか、JSON中心にするか
- 複数エージェントが同じenvelopeを共有できるか
- profileの有効期限と再検証間隔をどう決めるか

## 次のアクション

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
