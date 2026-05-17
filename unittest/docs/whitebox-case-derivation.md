# ホワイトボックステストケース生成スキル 設計書

AST 解析 + JaCoCo ブランチカバレッジモデルを用いて、テストケースを体系的かつ漏れなく
生成するスキルの設計書。インプット・処理フロー・アウトプットを定義する。

---

## 1. スキル概要

### 目的

実システムのソースを Claude Code が直接読んでテストケースを自由生成すると、以下の省略が発生しやすい。

| 省略パターン | 具体例 |
|---|---|
| ハッピーパス偏重 | 在庫ありの注文成功ケースのみ作成し、在庫不足ケースを漏らす |
| ループ 0 回ケース漏れ | 注文アイテムが空の `placeOrder()` 呼び出しをテストしない |
| 複合条件の片パス欠落 | `A && B` で A=false の短絡ケースを作らない |
| catch ブロック未テスト | `try-catch` の例外発生側を省略する |
| if-without-else の false パス | `if (loginUser == null)` の false 側（ログイン済み）を忘れる |

### 解決アプローチ

「テストケースを生成する」という創造的タスクを、「分岐アウトカムをカバーする」という機械的タスクに分解する。

```
Step A  ソースを AST 解析 → 分岐インベントリ（B-ID 付き一覧）を作成
Step B  分岐インベントリ → テストケースを 1:1 で対応付け（Claude Code に指示）
Step C  JaCoCo で実行 → 未カバー分岐（黄/赤）を 0 にする
```

分岐インベントリが「チェックリスト」として機能するため、省略が検知可能になる。

### 適用対象

| 言語 / 形式 | 対応 |
|---|---|
| Java（`.java`） | ✓ |
| JavaScript（`.js` / `.mjs` / `.cjs`） | ✓ |
| MyBatis XML マッパー（`.xml`） | ✓（層1: 動的タグ、層2: SQL ロジック） |

---

## 2. インプット

スキル実行に必要な情報を以下に定義する。`branch-extractor` CLI のオプションと対応している。

| 項目 | CLI オプション | 必須 | 説明 |
|---|---|---|---|
| 解析対象ファイル | 位置引数 `<file>` | ✓ | `.java` / `.js` / `.mjs` / `.cjs` / `.xml` |
| 対象メソッド名 | `--method` / `-m` | ✓（常に必須） | `.java` / `.js` → メソッド名。`.xml` → SQL の `id` 属性値 |
| DAOインターフェース | `--dao <path>` | `.xml` 時のみ必須 | `SELECT` の単一 / `List<T>` 返却を判別するために使用 |
| 出力先 Markdown | `--output` / `-o` | 任意 | 省略時は標準出力 |

### 制約（違反時はエラー終了）

- `--method` は常に必須（省略不可）
- `<file>` が `.xml` の場合、`--dao` は必須
- `<file>` が `.xml` 以外の場合、`--dao` は使用不可
- `--dao` に指定するファイルは `.java` でなければならない

---

## 3. 処理フロー

### Step A — branch-extractor CLI で分岐インベントリを生成

#### セットアップ（初回のみ）

```toml
# pyproject.toml の dependencies に追記
"tree-sitter>=0.23",
"tree-sitter-java>=0.23",
"tree-sitter-javascript>=0.23",
"sqlglot>=23",              # DAO 層: SQL 本体のロジック分岐解析用
```

```powershell
uv sync
```

#### CLI コマンド例

```powershell
# Java ファイルの特定メソッドを解析して標準出力
uv run python unittest/branch-extractor/branch_extract.py `
  ast-analyzer/sample-app/src/.../OrderServiceImpl.java `
  --method placeOrder

# Java ファイルを解析して Markdown ファイルに出力
uv run python unittest/branch-extractor/branch_extract.py `
  ast-analyzer/sample-app/src/.../OrderServiceImpl.java `
  --method placeOrder `
  --output unittest/docs/branch-inventory-sample.md

# JavaScript ファイルの特定メソッドを解析
uv run python unittest/branch-extractor/branch_extract.py `
  ast-analyzer/sample-app/src/main/webapp/js/order.js `
  --method submitOrder `
  --output unittest/docs/branch-inventory-js-sample.md

# MyBatis XML マッパーを解析（DAO インターフェース指定あり）
uv run python unittest/branch-extractor/branch_extract.py `
  ast-analyzer/sample-app/src/main/resources/mapper/OrderMapper.xml `
  --method findById `
  --dao ast-analyzer/sample-app/src/main/java/.../OrderDao.java `
  --output unittest/docs/branch-inventory-order-dao.md
```

#### Step A の出力形式

Step A の成果物は「分岐インベントリ Markdown」。詳細は[セクション 4](#4-アウトプット形式) を参照。  
B-ID 採番規則の詳細は `whitebox-ast-implementation-policy.md` セクション 5-B を参照。

#### Step A 完了後の確認事項

- [ ] メソッドごとの分岐数が Cyclomatic Complexity と整合するか確認
  - Cyclomatic Complexity = 分岐数 + 1（単純な場合）
- [ ] ネストした分岐に親子関係の ID が振られているか
- [ ] `&&` / `||` の複合条件が短絡パスに分解されているか
- [ ] ループが「0回 / 1回以上」の2アウトカムで記録されているか

---

### Step B — 分岐インベントリから Claude Code でテストケースを導出

#### 対応付けルール

```
分岐インベントリの「アウトカム行（-T / -F / -0 / -N など）」1つ
に対して、最低 1 つのテストケース（TC-ID）を割り当てる。

1つのテストケースが複数のアウトカムを通過する場合は共有可能。
ただし、T/F が逆のアウトカムを同一ケースで担うことは不可。
```

分岐タイプ別の具体的な導出ルールは[付録](#付録-分岐タイプ別テストケース導出ルール)を参照。

#### Claude Code への指示プロンプトテンプレート

```
以下の分岐インベントリに基づき、テストケース一覧を作成してください。

【制約】
- インベントリの全アウトカム行（-T/-F/-0/-N など）に TC-ID を割り当てること
- 1つのアウトカムが未割り当てのまま残ることを禁止する
- テストケース作成後、最後に「カバレッジ確認表」を出力すること

【カバレッジ確認表の形式】
| B-ID（アウトカム） | 担当 TC-ID | カバー済み |
|---|---|---|
| B-04-T | TC-OS-01 | ✓ |
| B-04-F | TC-OS-02 | ✓ |
...

- カバレッジ確認表に「未割当」行が 0 件であることを確認してから終了すること
```

---

### Step C — JaCoCo でカバレッジ検証

Step B で生成したテストコードを実行し、JaCoCo レポートで分岐カバレッジを確認する。

```
□ JaCoCo レポートで黄ダイアモンド（部分カバー）が 0 件か
□ JaCoCo レポートで赤ダイアモンド（未カバー）が 0 件か
```

> **JaCoCo の注意**: MyBatis XML 動的 SQL タグ・SQL ロジック分岐はいずれも JaCoCo のブランチカバレッジに現れない。カバレッジ確認は「アウトカム確認表」を手動で維持するか、テスト件数で担保すること。

---

## 4. アウトプット形式

### 分岐インベントリ（Step A の出力）

**分岐点一覧テーブル**

```markdown
| B-ID | クラス | メソッド | 行 | 種別 | 条件式 | アウトカム数 | 祖先チェーン | 要確認 |
|---|---|---|---|---|---|---|---|---|
| B-f1a2b3 | OrderServiceImpl | getOrderById | 28 | if | order != null | 2 | - | |
| B-c4d5e6 | OrderServiceImpl | placeOrder | 38 | enhanced-for | item : order.getItems() | 2 | - | |
| B-7f8a9b | OrderServiceImpl | placeOrder | 39 | if | !checkStock(productId, quantity) | 2 | B-c4d5e6 | |
```

**アウトカム詳細テーブル**

```markdown
| アウトカム ID | B-ID | クラス | メソッド | 行 | 種別 | ラベル | 説明 | 担当 TC-ID |
|---|---|---|---|---|---|---|---|---|
| B-f1a2b3-T | B-f1a2b3 | OrderServiceImpl | getOrderById | 28 | if | T | order が存在する → items を付与して返す | |
| B-f1a2b3-F | B-f1a2b3 | OrderServiceImpl | getOrderById | 28 | if | F | order が null → null を返す | |
| B-c4d5e6-0 | B-c4d5e6 | OrderServiceImpl | placeOrder | 38 | enhanced-for | 0回 | getItems() が空リスト | |
| B-c4d5e6-N | B-c4d5e6 | OrderServiceImpl | placeOrder | 38 | enhanced-for | 1回以上 | getItems() が非空 | |
| B-7f8a9b-T | B-7f8a9b | OrderServiceImpl | placeOrder | 39 | if | T（在庫不足） | checkStock が false → throw | |
| B-7f8a9b-F | B-7f8a9b | OrderServiceImpl | placeOrder | 39 | if | F（在庫あり） | checkStock が true → 継続 | |
```

> 「担当 TC-ID」列はテストケース設計時（Step B）に記入する。  
> 「要確認」列は再生成時に自動記入される（`新規` / `⚠ B-xxx との順序逆転` / `祖先変更 (旧: ...)` / 空欄）。

### テストケース表（Step B の出力）

```
TC-ID    | 対象 B-ID       | テスト名                                | 前提条件             | 入力                   | 期待結果
---------|-----------------|----------------------------------------|----------------------|------------------------|------------------
TC-OS-01 | B-05-0          | 空アイテムで注文 → 正常終了             | items = []           | placeOrder(order)      | 例外なし、insert 0回
TC-OS-02 | B-05-N, B-05a-F | 在庫あり1アイテムで注文成功             | stock=5, required=1  | placeOrder(order)      | insertOrder 1回呼ばれる
TC-OS-03 | B-05-N, B-05a-T | 在庫不足で RuntimeException            | stock=0, required=1  | placeOrder(order)      | RuntimeException
TC-OS-04 | B-05-N, B-05a-T | 2アイテム目で在庫不足                   | item1=OK, item2=NG   | placeOrder(order)      | RuntimeException、item1のinsertは呼ばれない
```

### カバレッジ確認表（Step B の出力）

```markdown
| B-ID（アウトカム） | 担当 TC-ID | カバー済み |
|---|---|---|
| B-3fa2b1-0 | TC-01 | ✓ |
| B-3fa2b1-N | TC-02, TC-03 | ✓ |
...
```

未割当: **0 件** → C1 カバレッジ達成

---

## 5. 実例: OrderServiceImpl.placeOrder()

sample-app の最も複雑なメソッドを例として、Step A → Step B の全流れを示す。

### 5.1 ソースコード（対象部分）

```java
// OrderServiceImpl.java lines 37-49
@Transactional
public void placeOrder(Order order) {
    for (OrderItem item : order.getItems()) {          // B-L1（enhanced-for）
        if (!productService.checkStock(               // B-L1a（if、ループ内）
                item.getProductId(), item.getQuantity())) {
            throw new RuntimeException(
                "在庫不足: productId=" + item.getProductId());
        }
    }
    orderDao.insertOrder(order);
    for (OrderItem item : order.getItems()) {          // B-L2（enhanced-for、2回目）
        item.setOrderId(order.getId());
        orderDao.insertOrderItem(item);
        productService.decreaseStock(
            item.getProductId(), item.getQuantity());
    }
}
```

### 5.2 分岐インベントリ（Step A の出力）

**分岐点一覧**

| B-ID | クラス | メソッド | 行 | 種別 | 条件式 | アウトカム数 | 祖先チェーン | 要確認 |
|---|---|---|---|---|---|---|---|---|
| B-3fa2b1 | OrderServiceImpl | placeOrder | 38 | enhanced-for | item : order.getItems() | 2 | - | |
| B-cc9d4e | OrderServiceImpl | placeOrder | 39 | if | !checkStock(id, qty) | 2 | B-3fa2b1 | |
| B-8b7c6f | OrderServiceImpl | placeOrder | 44 | enhanced-for | item : order.getItems() | 2 | - | |

**アウトカム詳細**

| アウトカム ID | B-ID | メソッド | 行 | ラベル | 説明 | 担当 TC-ID |
|---|---|---|---|---|---|---|
| B-3fa2b1-0 | B-3fa2b1 | placeOrder | 38 | 0回 | getItems() が空リスト → ループスキップ | |
| B-3fa2b1-N | B-3fa2b1 | placeOrder | 38 | 1回以上 | getItems() が非空 → ループ本体実行 | |
| B-cc9d4e-T | B-cc9d4e | placeOrder | 39 | T（在庫不足） | checkStock が false → throw | |
| B-cc9d4e-F | B-cc9d4e | placeOrder | 39 | F（在庫あり） | checkStock が true → 継続 | |
| B-8b7c6f-0 | B-8b7c6f | placeOrder | 44 | 0回 | B-3fa2b1-0 と同一入力で到達 → insert 0回 | |
| B-8b7c6f-N | B-8b7c6f | placeOrder | 44 | 1回以上 | B-3fa2b1-N, B-cc9d4e-F を全通過 → insert 実行 | |

**総アウトカム数: 6**（B-3fa2b1: 2 + B-cc9d4e: 2 + B-8b7c6f: 2）

### 5.3 テストケース（Step B の出力）

| TC-ID | カバーする B-ID | テスト名 | モック設定 | 期待結果 |
|---|---|---|---|---|
| TC-01 | B-3fa2b1-0, B-8b7c6f-0 | アイテム空で注文 → 正常終了 | getItems() = [] | insertOrder 呼ばれない ※ |
| TC-02 | B-3fa2b1-N, B-cc9d4e-F, B-8b7c6f-N | 1アイテム在庫あり → 正常 | stock=5, qty=1 | insertOrder 1回、insertItem 1回、decreaseStock 1回 |
| TC-03 | B-3fa2b1-N, B-cc9d4e-T | 1アイテム在庫不足 → 例外 | stock=0, qty=1 | RuntimeException、insertOrder 呼ばれない |
| TC-04 | B-3fa2b1-N, B-cc9d4e-F→T | 2アイテム目で在庫不足 | item1=OK, item2=NG | RuntimeException、item1のcheckStock=true, item2=false |
| TC-05 | B-3fa2b1-N, B-cc9d4e-F（全F）, B-8b7c6f-N | 複数アイテム全在庫あり | stock充分 × 2 | insertOrder 1回、insertItem 2回、decreaseStock 2回 |

> ※ TC-01: アイテムが空なので for ループが 0 回 → insertOrder も呼ばれない。  
>   これは仕様として正しいか別途要確認（空注文を許容するか）。

### 5.4 カバレッジ確認表

| B-ID（アウトカム） | 担当 TC-ID | カバー済み |
|---|---|---|
| B-3fa2b1-0 | TC-01 | ✓ |
| B-3fa2b1-N | TC-02, TC-03, TC-04, TC-05 | ✓ |
| B-cc9d4e-T | TC-03, TC-04 | ✓ |
| B-cc9d4e-F | TC-02, TC-04, TC-05 | ✓ |
| B-8b7c6f-0 | TC-01 | ✓ |
| B-8b7c6f-N | TC-02, TC-05 | ✓ |

未割当: **0 件** → C1 カバレッジ達成

### 5.5 JUnit 5 + Mockito スケルトン（参考）

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceImplTest {

    @Mock OrderDao orderDao;
    @Mock ProductService productService;
    @InjectMocks OrderServiceImpl orderService;

    // TC-01: B-3fa2b1-0, B-8b7c6f-0
    @Test
    void placeOrder_emptyItems_noInsertCalled() {
        Order order = new Order();
        order.setItems(Collections.emptyList());

        orderService.placeOrder(order);

        verify(orderDao, never()).insertOrder(any());
    }

    // TC-02: B-3fa2b1-N, B-cc9d4e-F, B-8b7c6f-N
    @Test
    void placeOrder_singleItemInStock_insertsSuccessfully() {
        OrderItem item = new OrderItem();
        item.setProductId(1); item.setQuantity(1); item.setUnitPrice(100);
        Order order = new Order();
        order.setItems(List.of(item));

        when(productService.checkStock(1, 1)).thenReturn(true);

        orderService.placeOrder(order);

        verify(orderDao).insertOrder(order);
        verify(orderDao).insertOrderItem(item);
        verify(productService).decreaseStock(1, 1);
    }

    // TC-03: B-3fa2b1-N, B-cc9d4e-T
    @Test
    void placeOrder_stockInsufficient_throwsRuntimeException() {
        OrderItem item = new OrderItem();
        item.setProductId(1); item.setQuantity(5);
        Order order = new Order();
        order.setItems(List.of(item));

        when(productService.checkStock(1, 5)).thenReturn(false);

        assertThrows(RuntimeException.class, () -> orderService.placeOrder(order));
        verify(orderDao, never()).insertOrder(any());
    }

    // TC-04: B-3fa2b1-N, B-cc9d4e-F→T（2アイテム目で在庫不足）
    @Test
    void placeOrder_secondItemOutOfStock_throwsAndNoInsert() {
        OrderItem item1 = new OrderItem(); item1.setProductId(1); item1.setQuantity(1);
        OrderItem item2 = new OrderItem(); item2.setProductId(2); item2.setQuantity(99);
        Order order = new Order();
        order.setItems(List.of(item1, item2));

        when(productService.checkStock(1, 1)).thenReturn(true);
        when(productService.checkStock(2, 99)).thenReturn(false);

        assertThrows(RuntimeException.class, () -> orderService.placeOrder(order));
        verify(orderDao, never()).insertOrder(any());
    }
}
```

---

## 6. カバレッジ確認チェックリスト

テストケース作成完了後（Step B 後）、以下を確認する。

### 分岐タイプ別チェック

```
□ if 文              全アウトカム（T/F）に TC-ID が割り当てられているか
□ else if / else     各分岐（含む else）に TC-ID があるか
□ switch             全 case + default に TC-ID があるか
□ for / while        0 回ケース と 1 回以上ケース の両方があるか
□ do-while           1 回で終了ケース と 複数回ケース の両方があるか
□ enhanced-for（Java） 空コレクションケース があるか
□ for-of（JS）        空イテラブルケース があるか
□ for-in（JS）        キーなしオブジェクトケース があるか
□ try-catch          正常系 と 例外発生系 の両方があるか
□ &&                 短絡評価（左辺=false）のケース があるか
□ ||                 短絡評価（左辺=true）のケース があるか
□ 三項演算子（JS）   T/F 両方のケース があるか
```

### カバレッジ確認表チェック

```
□ カバレッジ確認表の「未割当」行が 0 件か
□ JaCoCo レポートで黄ダイアモンド（部分カバー）が 0 件か（Java のみ）
□ JaCoCo レポートで赤ダイアモンド（未カバー）が 0 件か（Java のみ）
```

### 設計品質チェック

```
□ 1つのテストケースが「T と F 両方」を担っていないか
  （テストケースは1つの観点を検証するべき）
□ モック設定と期待結果が矛盾していないか
□ 境界値（stock=required, required=0 など）がカバーされているか
□ 空注文・null パラメータなど境界的な入力が考慮されているか
```

---

## 付録: 分岐タイプ別テストケース導出ルール

### A.1 if 文（単純）

```java
if (user == null) {      // 分岐アウトカム T
    return null;
}
return user;             // 分岐アウトカム F
```

| アウトカム | テストケースで用意するもの |
|---|---|
| T (null) | DAO が null を返すようにモック |
| F (非null) | DAO が User オブジェクトを返すようにモック |

### A.2 if-else if-else（複数分岐）

```java
if (status.equals("PENDING")) {
    // ...
} else if (status.equals("COMPLETED")) {
    // ...
} else {
    // ...
}
```

| アウトカム | テストケース |
|---|---|
| PENDING | status = "PENDING" |
| COMPLETED | status = "COMPLETED" |
| else | status = "CANCELLED"（未定義の値） |

> 上位条件が T の場合、下位条件は評価されないため各 case を独立してテストすること。

### A.3 switch 文

```java
switch (role) {
    case "admin": doAdmin(); break;
    case "user":  doUser();  break;
    default:      throw new IllegalArgumentException();
}
```

| アウトカム | テストケース |
|---|---|
| "admin" | role = "admin" |
| "user" | role = "user" |
| default | role = "guest"（定義外の値） |

fall-through がある場合は通過するすべての case を 1 ケースで確認可能だが、意図した fall-through であることをコメントで明示する。

### A.4 ループ（for / while）

```java
for (OrderItem item : order.getItems()) {  // ← ここで2分岐
    if (!checkStock(...)) {                // ← ここでさらに2分岐（ループ内）
        throw new RuntimeException();
    }
}
```

| アウトカム | テストケース |
|---|---|
| 0回（空リスト） | `order.getItems()` が空リストを返す |
| 1回・ループ内T | 1アイテム、在庫不足 → 例外 |
| 1回・ループ内F | 1アイテム、在庫あり → 正常 |
| 複数回・途中でT | 2アイテム目で在庫不足 → 例外 |
| 複数回・全F | 2アイテムとも在庫あり → 正常 |

ループ内の分岐はイテレーション回数との組み合わせで考える。

> **JavaScript の注意点**:  
> Java の `enhanced-for` に相当するものが JS では2種類に分かれる。  
> - `for...of`（`for-of`）: 配列・イテラブルの各要素 → アウトカムは「空イテラブル / 非空」の2択  
> - `for...in`（`for-in`）: オブジェクトのキー列挙 → アウトカムは「キーなし / キーあり」の2択

### A.5 try-catch

```java
try {
    orderService.placeOrder(order);
    return ResponseEntity.ok(...);
} catch (RuntimeException e) {
    return ResponseEntity.badRequest()...;
}
```

| アウトカム | テストケース |
|---|---|
| 正常（catch 未通過） | `placeOrder()` が正常完了するようにモック |
| RuntimeException 発生 | `placeOrder()` が `RuntimeException` をスローするようにモック |

複数の例外型がある場合、各 catch ブロックを発火させるケースを独立して用意する。

### A.6 三項演算子（JavaScript のみ）

```javascript
const label = count > 0 ? "あり" : "なし";
//            ↑ ternary（T/F 2アウトカム）
```

| アウトカム | テストケース |
|---|---|
| T | `count > 0` が真となる入力（例: count = 1） |
| F | `count > 0` が偽となる入力（例: count = 0） |

Java の三項演算子は初版対象外（JaCoCo は計測するが、サンプルアプリには存在しないため）。

### A.7 複合条件（&&）の詳細導出

```java
// ProductServiceImpl.checkStock() line 52
return product != null && product.getStock() >= requiredQuantity;
//     ↑ B-02               ↑ B-03
```

| パス | B-02（product != null） | B-03（stock >= required） | 戻り値 | テストケース |
|---|---|---|---|---|
| A | false（短絡） | 評価されない | false | `productDao.findById()` が null を返す |
| B | true | true | true | stock=5, required=5（境界=等値） |
| C | true | false | false | stock=3, required=5 |

最低限 A と（B または C）の 2 ケースで C1 を達成できるが、B・C を両方用意することで境界値も網羅できる。

### A.8 MyBatis XML タグ（DAO 層・層1）

```xml
<!-- 例: 動的 WHERE 句 -->
<if test="categoryId != null">
    AND category_id = #{categoryId}
</if>
```

| タグ | アウトカム | テストケースで用意するもの |
|---|---|---|
| `<if test="cond">` T | SQL 句が追加される | cond が真となるパラメータを渡す |
| `<if test="cond">` F | SQL 句がスキップされる | cond が偽（null 等）のパラメータを渡す |
| `<choose><when><otherwise>` | 各 when + otherwise それぞれ | 各 when に合致する値、どれにも合致しない値を渡す |
| `<foreach>` 0 件 | コレクション展開されない | 空コレクションを渡す |
| `<foreach>` 1 件以上 | コレクション展開される | 非空コレクションを渡す |

> **Service 層との違い**: パラメータ（Java メソッドの引数）で SQL の生成を制御する。DB の状態は変えない。

### A.9 SQL ロジック分岐（DAO 層・層2）

```sql
-- 例: WHERE ヒット/ミス
SELECT * FROM users WHERE id = #{id}

-- 例: UPDATE 影響件数
UPDATE products SET stock = stock + #{quantity} WHERE id = #{id}
```

| SQL 要素 | 分岐の種類 | アウトカム | テストデータの制御 |
|---|---|---|---|
| `SELECT … WHERE id = #{id}` | WHERE ヒット/ミス | ヒットあり → エンティティ返却 | 該当 ID を事前 INSERT |
| 同上 | WHERE ヒット/ミス | ヒットなし → null | INSERT しない |
| `SELECT *`（`List<T>` 返却） | SELECT 件数 | 0 件 → 空リスト | テーブル空 |
| 同上 | SELECT 件数 | 1 件以上 → リスト | 件数分 INSERT |
| `UPDATE … WHERE id = #{id}` | 更新件数 | 更新あり → 戻り値 1 | 該当 ID を事前 INSERT |
| 同上 | 更新件数 | 更新なし → 戻り値 0 | 対象 ID なし |
| `DELETE … WHERE id = #{id}` | 削除件数 | 削除あり → 戻り値 1 | 該当 ID を事前 INSERT |
| 同上 | 削除件数 | 削除なし → 戻り値 0 | 対象 ID なし |
| `INSERT` + UNIQUE 制約 | 制約違反の有無 | 成功 → 戻り値 1 | 重複なし |
| 同上 | 制約違反の有無 | 失敗 → 例外 | 同値を事前 INSERT |
| `SET col = col + #{qty}` | 値の符号 | 正値 → 増加 | qty > 0 |
| 同上 | 値の符号 | 負値 → 減少 | qty < 0 |

> **層1 との違い**: パラメータは固定のまま **テストデータ（INSERT するデータ）** で DB 状態を変えて分岐を制御する。
