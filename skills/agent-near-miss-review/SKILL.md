---
name: agent-near-miss-review
description: AIエージェント利用中の事故やヒヤリハットについて、観測事実、影響範囲、停止要因、偶然守られた点、再現条件、恒久対策を整理し、ガードレール改善へ接続する。Use when AIによる想定外の変更、外部通信、秘密情報アクセス、権限逸脱が発生または発生しかけたとき。Don't use for 個人評価、懲戒判断、法的責任の確定、証拠のない原因断定。
---

# Agent Near Miss Review

## 手順

**Step 1: 非懲罰的な記録を開始する**
1. `assets/near-miss.template.md`をコピーする。
2. 人物評価ではなく、タスク、能力、環境、状態遷移、観測結果を記録する。
3. 事実、推測、未確認事項を分離する。

**Step 2: 影響と停止要因を確認する**
1. 何をしようとしていたか、AIへ何を渡したか、どこまで到達できたかを記録する。
2. 実際に被害を止めた制御と、偶然無事だっただけの条件を分ける。
3. credential、network、data、repository、external side effectへの影響を確認する。

**Step 3: 再現可能性を評価する**
1. `references/review-questions.md`を使用して不足情報を洗い出す。
2. 実データを使わず再現できる場合は、最小再現条件を記録する。
3. 再現できない場合は原因を断定しない。

**Step 4: ガードレール改善へ接続する**
1. 具体的な失敗証拠がある場合だけ`failure-to-guardrail`へ渡す。
2. 即時対応、恒久対策候補、owner、期限、再検証条件を記録する。
3. `python3 scripts/validate-near-miss.py <near-miss.md>`を実行する。

## Error Handling

- 証拠が保全されていない場合は、確認できる事実だけを記録する。
- 法的責任や懲戒判断が必要な場合は、このスキルで結論を出さない。
- active incidentの場合は振り返りより先に停止、credential失効、影響封じ込めを行う。
