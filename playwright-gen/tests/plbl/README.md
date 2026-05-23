# tests/plbl/ — PL-BL 結合テスト シナリオ一覧

画面操作（Playwright）〜業務ロジック（Spring MVC + MyBatis）の結合動作を確認するシナリオ。  
サンプルアプリ（`ast-analyzer/sample-app`）を対象とする。

---

## シナリオ一覧

### scenario_01_order.spec.ts — 商品一覧 → 商品詳細 → 購入

**遷移パス:** login → product_list → product_detail → order_detail

**使用 POM:** `LoginPage` / `ProductListPage` / `ProductDetailPage` / `OrderDetailPage`

| テストケース | 確認内容 |
|---|---|
| ログイン後に商品一覧が表示される | data.sql の6商品が全件表示される |
| カテゴリ絞り込みを実行できる | `electronics` で絞り込み → 2件（ノートPC・スマートフォン）|
| 商品名リンクから商品詳細ページへ遷移できる | 一覧1行目のリンク → `/product/detail/{id}` に遷移 |
| 商品詳細から今すぐ購入すると注文詳細ページへ遷移する | `buyNow(1)` → AJAX → `/order/detail/{id}` に遷移、ステータス PENDING |
| 商品一覧でカートに追加して注文する | `.btn-cart` クリック → `#cart-panel` 表示 → `placeOrder()` → 注文詳細に遷移 |

---

### scenario_02_order_history.spec.ts — 注文履歴確認・キャンセル・受け取り完了

**遷移パス:** login → (purchase) → order_list → order_detail

**使用 POM:** `LoginPage` / `ProductDetailPage` / `OrderListPage` / `OrderDetailPage`

| テストケース | 確認内容 |
|---|---|
| 注文後に注文履歴一覧に注文が表示される | 購入後に `/order/list` を開き、PENDING 行が存在する |
| 注文一覧から詳細リンクをクリックして注文詳細ページへ遷移できる | 「詳細」リンク → `/order/detail/{id}` に遷移 |
| PENDING注文をキャンセルするとキャンセルボタンが非表示になる | confirm 承認 → `.btn-danger` が該当行から消える |
| 注文詳細で受け取り完了を実行するとステータスが COMPLETED になる | `completeOrder()` → AJAX → DOM 直接更新 → `#orderStatus` = COMPLETED |

---

## 実行コマンド

```powershell
# このディレクトリのシナリオを全て実行
npx playwright test tests/plbl/ --config playwright.plbl.config.ts

# シナリオを指定して実行
npx playwright test tests/plbl/scenario_01_order.spec.ts --config playwright.plbl.config.ts

# ヘッドあり（ブラウザ表示）で確認
npx playwright test tests/plbl/ --config playwright.plbl.config.ts --headed
```

---

## 前提条件

- サンプルアプリが起動していること（`ast-analyzer/sample-app/up.bat`）
- DB に `schema.sql` + `data.sql` が適用されていること（`data.sql` の6商品・テストユーザー `user1` が必要）
- `playwright.plbl.config.ts` の `baseURL` が設定されていること

---

## 新しいシナリオを追加するときのガイドライン

- ファイル名: `scenario_{連番}_{目的の概要}.spec.ts`（例: `scenario_03_product_edit.spec.ts`）
- `test.describe` の名前: `シナリオ{N}: {遷移パスの概要}` の形式
- このREADMEの「シナリオ一覧」に追記する
