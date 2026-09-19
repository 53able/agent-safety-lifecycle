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
