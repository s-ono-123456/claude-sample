# 既知の課題

## js_actions のセレクタが解決できず FIXME になる — 解消済み（2025-05-23）

### 経緯

当初、`generate_pom.py` 実行時に以下の問題が発生していた。

1. `js_actions` にボタンの `id`/`selector` が付いていない → Locator が `FIXME` になる
2. JS ファイルを複数 JSP で共有しているため、当該 JSP にボタンがない関数も `js_actions` に含まれる（誤検知）

### 対処内容（`extract_metadata.py`）

**問題 1 の対処**: `collect_onclick_map(soup)` を追加し、JSP の `onclick` ボタンから `{関数名: {id or selector}}` のマップを構築して `js_actions` に付与。

**問題 2 の対処**: `parse_js_for_screen` 内で、`onclick_map` に含まれる関数名（その JSP で実際に呼ばれているもの）のみを `js_actions` に残すフィルタを追加。

```python
onclick_map = collect_onclick_map(soup)
js_actions = [a for a in js_actions if a.get('js_fn') in onclick_map]  # 誤検知除外
for action in js_actions:
    fn = action.get('js_fn')
    if fn in onclick_map:
        action.update(onclick_map[fn])  # id/selector を付与
```

### 結果

FIXME は全画面でゼロになった。

---

## ProductDetailPage.waitForLoad() のタイトルアサーションが失敗する — 解消済み（2026-05-23）

### 症状

`ProductDetailPage.waitForLoad()` 内の以下のアサーションが失敗する。

```typescript
await expect(this.page).toHaveTitle('商品詳細 -');
// 実際のタイトル: '商品詳細 - ノートPC'（商品名が動的に付加される）
```

### 原因

Playwright の `toHaveTitle(string)` は完全一致を要求する。  
しかし商品詳細の `<title>` は `商品詳細 - ${product.name}` の動的テキストのため、  
`screens.yaml` の `assertions.on_load.value: 商品詳細 -`（前方一致を意図したプレフィックス）と一致しない。

### 対処方針

`generate_pom.py` のテンプレートで、`type: title` かつ value が末尾スペースや `-` で終わる場合は  
正規表現に変換して出力するよう対処する。

```typescript
// 修正後イメージ
await expect(this.page).toHaveTitle(/^商品詳細 -/);
```

### 暫定回避策（テストコード側）

`ProductDetailPage.waitForLoad()` を呼ばず、URL と h1 で代替確認する。

```typescript
// ProductDetailPage.waitForLoad() の代わりに使う
await expect(page).toHaveURL(/\/product\/detail\/\d+/);
await expect(page.locator('h1')).toHaveText('商品詳細');
```

---

## ProductListPage.検索() が select 要素に機能しない — 解消済み（2026-05-23）

### 症状

`ProductListPage.検索(category)` の内部で `fill()` を使っているが、  
`<select>` 要素に対して `fill()` は機能しない。

```typescript
// 生成された POM（誤り）
async 検索(categorySelect: string) {
  await this.categorySelectInput.fill(String(categorySelect));  // select には効かない
  await this.searchBtn.click();
}
```

### 対処方針

`generate_pom.py` の `⑦ フォームアクションメソッド生成` で、  
`input.type == 'select'` の場合は `fill()` ではなく `selectOption()` を生成するよう修正する。

```typescript
// 修正後イメージ
async 検索(categorySelect: string) {
  await this.categorySelectInput.selectOption(categorySelect);
  await this.searchBtn.click();
}
```

### 暫定回避策（テストコード側）

POM のメソッドを使わず、Locator に直接 `selectOption()` を呼ぶ。

```typescript
await products.categorySelectInput.selectOption('electronics');
await products.searchBtn.click();
```

---

## ProductDetailPage / OrderDetailPage の goto() がパスパラメータ非対応 — 解消済み（2026-05-23）

### 症状

```typescript
// 生成された POM（パスパラメータなし）
async goto() { await this.page.goto(`/product/detail`); }
// 正しくは /product/detail/{id} が必要
```

### 原因

`screens_index.yaml` の URL が `/product/detail`（パスパラメータなし）で登録されているため、  
`generate_pom.py` がパスパラメータありの `goto(id: number)` を生成しない。

### 対処方針

`screens_master.yaml` または `screens_index.yaml` の URL を `/product/detail/{id}` と記述し、  
`generate_pom.py` が `{id}` を検出したら `goto(id: number)` を生成するようにする（設計書に記載済み）。

### 暫定回避策（テストコード側）

`page.goto()` で直接遷移する。

```typescript
await page.goto(`/product/detail/${productId}`);
```

---

## data.sql のカテゴリ値と JSP の option value が不一致 — 解消済み（2026-05-23）

### 症状

カテゴリ絞り込み検索を実行すると結果が 0 件になる。

### 原因

| 箇所 | カテゴリ値 |
|---|---|
| `data.sql` の products テーブル | `電子機器` / `衣類` / `食品`（日本語）|
| `list.jsp` の `<option value="...">` | `electronics` / `clothing` / `food`（英語）|

形式が異なるため `WHERE category = 'electronics'` が一致しない。

### 対処方針

`data.sql` の category 値を英語に統一する、または `list.jsp` の option value を日本語に統一する。
