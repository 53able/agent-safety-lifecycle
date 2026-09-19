---
name: failure-to-guardrail
description: AIエージェントの失敗ログ、境界違反、ヒヤリハットから最小再現条件を抽出し、回帰テスト、権限制約、network rule、承認条件、停止条件へ変換して再検証する。Use when AI実行や境界テストで具体的な失敗が観測され、再発防止策を機械的なガードレールへ落とすとき。Don't use for 失敗証拠のない一般的な安全助言、責任追及、未実行の対策を検証済みと宣言するとき。
---

# Failure to Guardrail

## 手順

**Step 1: 観測事実を固定する**
1. `assets/guardrail-record.template.json`をコピーする。
2. command、入力、期待結果、実際の結果、exit code、環境識別子、証拠パスを記録する。
3. 推測を観測事実へ混ぜない。

**Step 2: 最小再現ケースを作る**
1. 正常系を残しながら、違反を再現する最小入力へ縮小する。
2. 再現できない場合は`UNREPRODUCED`とし、一般的な対策を検証済みとして扱わない。
3. `references/guardrail-mapping.md`を読み、失敗に対応する制約候補を選ぶ。

**Step 3: ガードレールへ変換する**
1. 可能な場合は文章ではなく回帰テスト、mount、network rule、limit、approval conditionへ変換する。
2. 変更対象、owner、undo方法を記録する。
3. 正常系を壊す可能性がある場合は受入ケースを追加する。

**Step 4: 再検証する**
1. 同じ再現条件で新しいガードレールを検証する。
2. 違反が再発せず、正常系が通ることを確認する。
3. `python3 scripts/validate-guardrail-record.py <record.json>`を実行する。
4. 実行していない検査を`VERIFIED`にしない。

## Error Handling

- 証拠がない場合は`BLOCKED`として追加観測を要求する。
- 再現できない場合は対策候補と検証済み対策を分離する。
- 修正によって新しい権限が必要になる場合はAutonomy Envelopeへ戻す。
