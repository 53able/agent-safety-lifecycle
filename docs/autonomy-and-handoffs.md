# 自律実行とハンドオフ

[設計概要](design.md) · [アーキテクチャ](architecture.md) · [スキルカタログ](skill-catalog.md) · [自律実行とハンドオフ](autonomy-and-handoffs.md) · [検証](validation.md) · [実装ロードマップ](implementation-roadmap.md)

Autonomy Envelope内では処理を自動化し、権限拡張、不可逆操作、境界違反、証拠不足の場合だけ人間へ渡す方針を定義します。

## ハンドオフ設計

### 自動化する操作

次の操作は、envelope内であれば人間の逐次承認なしで実行できます。

- コード調査
- コード編集
- 承認済みregistryからの依存関係導入
- build
- test
- lint
- 失敗分析
- retry budget内の修正と再実行
- patch生成
- test log生成
- 境界テスト
- result gateへの提出

### 条件付きで自動化する操作

- 一時worktreeへのpatch適用
- task固有branchへのcommit
- 固定されたrepositoryとbranchへのpush
- stagingへのdeploy

これらは、task-scoped broker、短命な認証情報、宛先固定、監査記録、rollbackを条件とします。

### 人間承認を残す操作

- production deploy
- データ削除
- 課金
- 公開・送信
- 権限変更
- protected branchへの反映
- envelope自体の拡張
- 検査不能な成果物の取り込み

## 例外時ハンドオフの形式

人間への依頼は自由文ではなく、次の構造で出します。

```yaml
request-type: capability-elevation
status: paused
task: frontend-test-fix
requested-capability: network-access
destination: registry.example.com
protocol: https
port: 443
purpose: download locked dependencies
scope: current-task-only
expires-after: 20m
alternatives-attempted:
  - offline-cache
risk-if-approved:
  - external-content-enters-guest
risk-if-denied:
  - build-cannot-continue
resume-action: rerun-dependency-install
```

利用者は、何を許可するのか、許可しない場合に何が止まるのかを一度で判断できます。
