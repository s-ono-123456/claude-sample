# 単体テスト設計資料

sample-app（Spring MVC + MyBatis + H2 の EC サイト）に対する単体テスト設計資料。

## ドキュメント一覧

| ファイル | 内容 | 状態 |
|---|---|---|
| [test-strategy.md](test-strategy.md) | テスト設計方針（対象・種別・基準・ツール） | Phase 1 |
| [whitebox-case-derivation.md](whitebox-case-derivation.md) | ホワイトボックステストケース導出方法論（JaCoCo ベース） | Phase 1 |
| [whitebox-ast-implementation-policy.md](whitebox-ast-implementation-policy.md) | AST 分岐抽出ツール実装方針（branch_extractor.py 設計） | Phase 1 |
| [blackbox-case-derivation.md](blackbox-case-derivation.md) | ブラックボックステストケース導出方法論（外部設計書ベース） | Phase 1 |
| [blackbox-excel-extractor-policy.md](blackbox-excel-extractor-policy.md) | Excel 設計書抽出ツール実装方針（openpyxl 版） | Phase 1 |
| testcases-service.md | サービス層テストケース詳細 | Phase 2（未作成） |
| testcases-controller.md | コントローラー層テストケース詳細 | Phase 2（未作成） |
| testcases-dao.md | DAO 層テストケース詳細（MyBatis 統合テスト） | Phase 2（未作成） |
| testcases-js.md | JavaScript テストケース詳細 | Phase 2（未作成） |

## 対象アプリケーション

`ast-analyzer/sample-app/` — Spring MVC 5 + MyBatis 3 + H2 インメモリ DB の EC サイト

| 層 | クラス数 | 主な責務 |
|---|---|---|
| Controller | 3 | HTTP リクエスト受付・セッション管理 |
| Service | 3 実装クラス | ビジネスロジック・トランザクション |
| DAO | 3 | MyBatis マッパー・DB アクセス |
| JavaScript | 3 ファイル | AJAX・カート管理・バリデーション |

## 作業フロー

```
Phase 1: 方針書（本フォルダ）
  ├── test-strategy.md      ← テスト設計の基準を定義
  └── whitebox-branch-analysis.md ← AST 解析で分岐を列挙

Phase 2: テストケース詳細（本フォルダに追加予定）
  ├── testcases-service.md
  ├── testcases-controller.md
  ├── testcases-dao.md
  └── testcases-js.md
```
