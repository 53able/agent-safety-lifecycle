---
name: agent-result-gate
description: AIエージェントが生成したpatch、コード、アーカイブ、依存関係、ログ、実行要求を未信頼成果物として検査し、取り込み、要レビュー、拒否、未検証を判定する。Use when 隔離環境の成果物をホスト、リポジトリ、CI、外部システムへ移す前に確認するとき。Don't use for 生成したAI自身による最終承認、検査なしの自動適用、一般的なスタイルレビュー。
---

# Agent Result Gate

## 手順

**Step 1: 成果物契約を読み込む**
1. Autonomy Envelopeに宣言されたoutput名、形式、サイズ、取り込み先を確認する。
2. `assets/result-gate-report.template.json`をコピーする。
3. 宣言されていない成果物を取り込み対象に追加しない。

**Step 2: 未信頼成果物を検査する**
1. `references/inspection-rules.md`を読む。
2. `python3 scripts/inspect-artifacts.py <artifact-directory>`を実行する。
3. path traversal、symlink、実行ファイル、ファイル数、サイズを確認する。
4. patch、dependency diff、test result、secret scan、外部通信、rollback可能性を別途確認する。

**Step 3: 判定する**
1. 明確な違反がある場合は`REJECTED`とする。
2. 人間の意味判断が必要な場合は`REVIEW_REQUIRED`とする。
3. 必須検査を実行できない場合は`UNVERIFIED`とする。
4. すべての定義済み条件を満たす場合だけ`IMPORTABLE`とする。
5. 判定と証拠をreportへ記録し、`python3 scripts/validate-result-gate-report.py <report.json>`を実行する。
6. report検証に失敗した場合は取り込みを停止する。

**Step 4: 取り込みを仲介する**
1. `IMPORTABLE`でも、push、deploy、publish、delete、credential利用をguestへ許可しない。
2. 外部操作はtask-scoped brokerまたは人間承認へ渡す。
3. 取り込み後のrevision、hash、destinationをSafety Caseへ記録する。

## Error Handling

- symlinkまたは特殊ファイルを検出した場合は自動取り込みを拒否する。
- 成果物が契約上限を超えた場合は分割または再生成を要求する。
- scan toolが利用できない場合は合格とせず`UNVERIFIED`とする。
