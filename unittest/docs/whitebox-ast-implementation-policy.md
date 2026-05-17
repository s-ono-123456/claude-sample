# AST 分岐抽出ツール 実装方針（tree-sitter 版）

`ast-analyzer/` とは独立した別サブプロジェクトとして Python + tree-sitter で
Java / JavaScript 分岐インベントリ抽出ツールを構築する方針をまとめる。

---

## 1. 配置とプロジェクト構成

```
C:\claude\
├── ast-analyzer/              ← 既存（Neo4j グラフ構築）
├── unittest/                  ← ユニットテスト支援ツール群
│   ├── branch-extractor/      ← 本ツール（AST 分岐抽出）
│   │   ├── branch_extractor.py   ← 分岐抽出ロジック本体（Java/JS）
│   │   ├── branch_extract.py     ← CLI エントリポイント
│   │   ├── dao/
│   │   │   ├── xml_extractor.py  ← 層1: MyBatis XML タグ解析
│   │   │   └── sql_extractor.py  ← 層2: SQL 本体のロジック分岐解析
│   │   └── README.md
│   ├── excel-extractor/       ← 同一ツール群（Excel 設計書抽出）
│   └── docs/                  ← ツール群共通の設計書
└── pyproject.toml             ← 共有環境に tree-sitter を追加
```

`ast-analyzer/` のコードには一切依存しない。

---

## 2. セットアップ

### 依存追加

```toml
# pyproject.toml に追記
dependencies = [
    ...
    "tree-sitter>=0.23",
    "tree-sitter-java>=0.23",
    "tree-sitter-javascript>=0.23",
    "sqlglot>=23",              # DAO 層: SQL 本体のロジック分岐解析用
]
```

```powershell
uv sync
```

### 初期化コード（branch_extractor.py 先頭）

Java / JS 用。tree-sitter パーサーを初期化する。

```python
from pathlib import Path
from tree_sitter import Language, Parser, Node
import tree_sitter_java as tsjava
import tree_sitter_javascript as tsjs

JAVA_LANGUAGE = Language(tsjava.language())
JS_LANGUAGE   = Language(tsjs.language())

java_parser = Parser(JAVA_LANGUAGE)
js_parser   = Parser(JS_LANGUAGE)

def get_parser(file_path: str) -> tuple[Parser, str]:
    ext = Path(file_path).suffix.lower()
    if ext == '.java':
        return java_parser, 'java'
    elif ext in ('.js', '.mjs', '.cjs'):
        return js_parser, 'javascript'
    raise ValueError(f"Unsupported extension: {ext}")
```

### 初期化コード（branch_extract.py — XML の場合の分岐）

`.xml` の場合は tree-sitter を使わず `dao/` モジュールへ委譲する。
`xml.etree.ElementTree` と `sqlglot` は Python 標準 / 外部ライブラリであり、パーサーオブジェクトの事前初期化は不要。
CLIエントリポイントで拡張子を確認し、処理フローを切り替える。

```python
from pathlib import Path

def main(args):
    ext = Path(args.file).suffix.lower()

    if ext == '.xml':
        # DAO 層フロー: xml_extractor → sql_extractor
        from dao.xml_extractor import extract_branches_from_xml
        results = extract_branches_from_xml(args.file, dao_java=args.dao)
    else:
        # Java / JS フロー: tree-sitter
        from branch_extractor import extract_branches
        results = extract_branches(args.file, method=args.method)

    render_markdown(results, args.output)
```

---

## 3. 主要ノード型と分岐タイプのマッピング

### Java

| tree-sitter ノード型 | branch_type | アウトカム数 | 備考 |
|---|---|---|---|
| `if_statement`（単純条件） | `if` | 2 | T / F |
| `if_statement`（`&&` 条件） | `if(&&)` | N+1 | 短絡パスに分解 |
| `if_statement`（`\|\|` 条件） | `if(\|\|)` | N+1 | 短絡パスに分解 |
| `for_statement` | `for` | 2 | 0回 / 1回以上 |
| `enhanced_for_statement` | `enhanced-for` | 2 | 空コレクション / 非空 |
| `while_statement` | `while` | 2 | 0回 / 1回以上 |
| `do_statement` | `do-while` | 2 | 1回で終了 / 複数回 |
| `switch_statement` | `switch` | case 数 | case ごと（default 含む） |
| `try_statement` | `try-catch` | catch 数 + 1 | 正常 + catch ごと |

### JavaScript

| tree-sitter ノード型 | branch_type | アウトカム数 | 備考 |
|---|---|---|---|
| `if_statement` | `if` | 2 | T / F |
| `if_statement`（`&&` 条件） | `if(&&)` | N+1 | 短絡パスに分解 |
| `if_statement`（`\|\|` 条件） | `if(\|\|)` | N+1 | 短絡パスに分解 |
| `for_statement` | `for` | 2 | 0回 / 1回以上 |
| `for_in_statement` | `for-in` | 2 | キーなし / キーあり |
| `for_of_statement` | `for-of` | 2 | 空イテラブル / 非空 |
| `while_statement` | `while` | 2 | 0回 / 1回以上 |
| `do_statement` | `do-while` | 2 | 1回で終了 / 複数回 |
| `switch_statement` | `switch` | case 数 | case ごと（default 含む） |
| `try_statement` | `try-catch` | catch 数 + 1 | JS は単一 catch のみ → 常に 2 |
| `ternary_expression` | `ternary` | 2 | T / F（JS では多用されるため対象に含める） |

> Java との主な差分: `enhanced_for_statement` → `for_of_statement` / `for_in_statement` に分割。`ternary_expression` を追加。

### MyBatis XML（DAO 層）

tree-sitter は使用せず、`xml.etree.ElementTree` で XML をパースする。

| XML タグ | branch_type | アウトカム数 | 備考 |
|---|---|---|---|
| `<if test="cond">` | `mybatis-if` | 2 | T: SQL 句追加 / F: スキップ |
| `<choose><when test="..."><otherwise>` | `mybatis-choose` | when 数 + 1 | 各 when + otherwise |
| `<foreach collection="...">` | `mybatis-foreach` | 2 | 0 件 / 1 件以上 |

SQL 本体のロジック分岐（層2）は `sqlglot` でさらに解析する:

| SQL 要素 | branch_type | アウトカム数 | 備考 |
|---|---|---|---|
| `SELECT … WHERE` + 単一返却 | `sql-where-single` | 2 | ヒットあり(エンティティ) / なし(null) |
| `SELECT … WHERE` + `List<T>` 返却 | `sql-where-list` | 2 | 0 件 / 1 件以上 |
| `UPDATE … WHERE` | `sql-update` | 2 | 更新あり(戻り1) / なし(戻り0) |
| `DELETE … WHERE` | `sql-delete` | 2 | 削除あり(戻り1) / なし(戻り0) |
| `INSERT` + UNIQUE 制約 | `sql-insert` | 2 | 成功 / 制約違反（手動補完） |
| `CASE WHEN` | `sql-case` | WHEN 数 + 1 | 各 WHEN + ELSE |
| `LEFT JOIN` | `sql-left-join` | 2 | 結合先あり(非NULL) / 結合先なし(NULL) |

単一/`List<T>` 返却の判別は DAO インターフェース（.java）の戻り型を参照する。

```python
BRANCH_NODE_TYPES_JS = {
    'if_statement', 'for_statement', 'for_in_statement', 'for_of_statement',
    'while_statement', 'do_statement', 'switch_statement',
    'try_statement', 'ternary_expression',
}
```

---

### `&&`/`||` の検出方法

条件ノードが `binary_expression` かつ operator が `&&`/`||` かどうかを調べる。

```python
BRANCH_NODE_TYPES = {
    'if_statement', 'for_statement', 'enhanced_for_statement',
    'while_statement', 'do_statement', 'switch_statement', 'try_statement',
}

def get_condition_node(node: Node) -> Node | None:
    """if / while / do の条件ノードを返す"""
    return node.child_by_field_name('condition')

def detect_bool_op(cond: Node) -> str | None:
    """条件が && または || を持つか判定。inner は最外側の operator を返す"""
    if cond is None:
        return None
    # parenthesized_expression の場合、内側の式を取得
    inner = cond.named_children[0] if cond.type == 'parenthesized_expression' else cond
    if inner.type == 'binary_expression':
        op = inner.child_by_field_name('operator')
        if op and op.type in ('&&', '||'):
            return op.type
    return None
```

---

## 4. 実装アプローチ: ツリー再帰ウォーク

クエリ言語よりも **再帰ウォーク** を採用する。理由：

- メソッドのスコープを自然に追跡できる（スタック変数として保持）
- ネストした分岐の親子関係を追跡しやすい
- tree-sitter のクエリ言語の学習コストを省ける

```
walk(node, context, language)
  context = { class_name, method_name, branch_stack }

  【Java】
  node.type が 'class_declaration'  → context.class_name を更新
  node.type が 'method_declaration' → context.method_name を更新、branch_stack をリセット
  node.type が BRANCH_NODE_TYPES   → BranchInfo を生成し branch_stack に push
                                     再帰後に branch_stack から pop
  その他                            → 子ノードを再帰

  【JavaScript】
  node.type が 'class_declaration'    → context.class_name を更新
  node.type が 'function_declaration' → context.method_name を更新（トップレベル関数）
                                        branch_stack をリセット
  node.type が 'method_definition'    → context.method_name を更新（クラスメソッド）
                                        branch_stack をリセット
  node.type が 'arrow_function'
           / 'function'（式）         → context.method_name = '<anonymous>@{line}'
                                        ※ 親 variable_declarator の name を参照して
                                          命名可能（const foo = () => の場合 'foo'）
  node.type が BRANCH_NODE_TYPES_JS  → BranchInfo を生成し branch_stack に push
                                        再帰後に branch_stack から pop
  その他                              → 子ノードを再帰
```

`branch_stack` の全要素が現在の祖先チェーン → `ancestor_chain` を自然に解決できる（例: `B-aaa > B-bbb`）。

### MyBatis XML の実装アプローチ

tree-sitter の再帰ウォークは使わず、`xml.etree.ElementTree` のツリー走査を2段階で行う。

**段階1: 動的 SQL タグの走査（層1）**

```
parse_xml(file_path, dao_java)
  context = { namespace, sql_id, branch_stack }

  ET.parse(file_path) で XML ツリーを構築

  <mapper namespace="..."> → context.namespace を取得

  各 SQL タグ（<select> / <update> / <delete> / <insert>）を列挙:
    context.sql_id = タグの id 属性
    branch_stack をリセット
    SQL タグの子要素を再帰走査:
      タグ名が 'if'       → BranchInfo(mybatis-if) を生成、branch_stack に push
                            子要素を再帰後に pop
      タグ名が 'choose'   → BranchInfo(mybatis-choose) を生成
                            子の <when> / <otherwise> ごとにアウトカムを生成
      タグ名が 'foreach'  → BranchInfo(mybatis-foreach) を生成、branch_stack に push
                            子要素を再帰後に pop
      その他              → 子要素を再帰
```

`branch_stack` は Java/JS と同様に機能し、`<foreach>` 内の `<if>` などネスト構造の祖先チェーンを自然に追跡できる。

**段階2: SQL 本体のロジック分岐（層2）**

```
  SQL タグのテキストを結合して SQL 文字列を構築
  （動的タグのテキストは #{placeholder} を除いてそのまま連結）

  sqlglot.parse_one(sql_text, dialect="mysql") で SQL AST を生成

  sql_id に対応する DAO メソッドの戻り型を dao_java から取得:
    → List<T> なら sql-where-list（0件/1件以上）
    → T       なら sql-where-single（ヒットあり/なし）

  SQL AST を走査して sql-* の BranchInfo を生成
```

---

## 5. 処理フロー

### Java / JS フロー

```
extract_branches(file_path: str, method: str) → list[BranchInfo]

  1. Path.read_bytes() でソースを読み込み
     tree-sitter は bytes を要求する

  2. get_parser(file_path) で言語を判定し適切なパーサーを取得
     → .java        → java_parser, language='java'
     → .js / .mjs / .cjs → js_parser, language='javascript'

  3. parser.parse(source_bytes) で CST を生成
     → パースエラーがあっても部分木として継続（tree-sitter はエラー耐性が高い）
     → node.has_error で構文エラーの有無を確認

  4. tree.root_node からツリー再帰ウォークを開始

  5. スコープ追跡（言語別）
     Java: 'class_declaration' → class_name、'method_declaration' → method_name
     JS:   'class_declaration' → class_name
           'function_declaration' / 'method_definition' → method_name
           'arrow_function' / 'function'（式） → method_name = '<anonymous>@{line}'

  6. BRANCH_NODE_TYPES（Java）または BRANCH_NODE_TYPES_JS（JS）を検出したら BranchInfo を生成
     - branch_id: 後述の採番規則（条件式ハッシュベース）参照
     - line: node.start_point[0] + 1
     - condition: 後述の各ノード型別の取得方法で取得
     - ancestor_chain: branch_stack の全要素を `>` 区切りで結合（例: `B-aaa > B-bbb`）。トップレベルは `-`

  7. 全ノード処理後に BranchInfo リストを返す
```

### XML フロー（DAO 層）

Java / JS フローとは独立した別関数。tree-sitter は使わない。

```
extract_branches_from_xml(file_path: str, sql_id: str, dao_java: str) → list[BranchInfo]

  【層1: 動的 SQL タグの走査】

  1. ET.parse(file_path) で XML ツリーを構築

  2. <mapper namespace="..."> から namespace を取得

  3. 各 SQL タグ（<select> / <update> / <delete> / <insert>）を列挙:
     sql_id = タグの id 属性、branch_stack をリセット

  4. SQL タグの子要素を再帰走査して動的タグを検出:
     → <if>      → BranchInfo(mybatis-if) を生成、branch_stack に push → 再帰後 pop
     → <choose>  → BranchInfo(mybatis-choose) を生成、<when>/<otherwise> のアウトカムを列挙
     → <foreach> → BranchInfo(mybatis-foreach) を生成、branch_stack に push → 再帰後 pop
     → その他    → 子要素を再帰

  【層2: SQL 本体のロジック分岐】

  5. SQL タグのテキストを結合して SQL 文字列を構築
     （動的タグのテキストは #{placeholder} を除いてそのまま連結）

  6. dao_java の対応メソッドの戻り型を取得
     → List<T> → sql-where-list（0件 / 1件以上）
     → T       → sql-where-single（ヒットあり / なし）

  7. sqlglot.parse_one(sql_text, dialect="mysql") で SQL AST を生成

  8. SQL AST を走査して sql-* の BranchInfo を生成

  9. 全 SQL タグ処理後に BranchInfo リストを返す
```

---

## 5-B. B-ID 採番規則

### 基本方式

`B-{6桁16進数}` 形式。以下のキー文字列の MD5 ダイジェスト先頭 6 文字を使用する。

```
キー = "{class_name}::{method_name}::{branch_type}::{condition_str}::{n}"
```

DAO 層（MyBatis XML）では `class_name` / `method_name` の代わりに `namespace` / `sql_id` を使用する:

```
キー = "{namespace}::{sql_id}::{branch_type}::{condition_str}::{n}"
```

- `namespace`: XML の `<mapper namespace="...">` 属性値（例: `com.example.dao.UserDao`）
- `sql_id`: `<select id="...">`  等の id 属性値（例: `findByCategory`）

- `n` は同一ファイル内で `(class_name, method_name, branch_type, condition_str)` の
  4 要素が完全一致する分岐が何番目か（0 始まり）
- `n=0` の場合でも必ずキーに含める（すべての ID を同じアルゴリズムで算出するため）

### 重複への対処

`if (isPresent)` のような汎用条件式が同一メソッド内に複数ある場合、`n` の値が変わるため
ハッシュが衝突しない。

```python
import hashlib
from collections import defaultdict

def make_branch_id(class_name: str, method_name: str, branch_type: str,
                   condition_str: str, counter: dict) -> str:
    key_base = f"{class_name}::{method_name}::{branch_type}::{condition_str}"
    n = counter[key_base]
    counter[key_base] += 1
    digest = hashlib.md5(f"{key_base}::{n}".encode()).hexdigest()
    return f"B-{digest[:6]}"

# 呼び出し側
counter = defaultdict(int)
branch_id = make_branch_id(class_name, method_name, branch_type, cond_str, counter)
```

### 安定性

- ソースの前後に行を追加・削除しても条件式が変わらない限り ID は不変
- 同一メソッド内で前に位置する同条件の分岐を追加・削除した場合のみ後続の `n` がずれる
- Markdown の git diff が「分岐の追加・変更・削除」を正確に反映する

### シフト検出チェック

同一条件式の前挿入による `n` のずれ（= B-ID のシフト）は、条件式だけでは検出できない。
再生成時に**旧 Markdown と新 Markdown の B-ID 並び順を比較**し、
同一メソッド内で異なる condition_str を持つ B-ID ペアの前後関係が逆転していれば警告する。

```
例:
  旧: B-3f7a2c(isPresent) → B-cc44ee(for loop) → B-9c1e4a(isPresent)
  新: B-3f7a2c(isPresent) → B-9c1e4a(isPresent) → B-cc44ee(for loop) → B-NEW(isPresent)

  B-9c1e4a と B-cc44ee の順序が逆転 → シフト発生と判定
```

チェックロジック:

```python
def detect_shift(old_branches: list[BranchInfo], new_branches: list[BranchInfo]) -> list[str]:
    warnings = []
    methods = {b.method_name for b in old_branches}
    for method in methods:
        old_seq = [b for b in old_branches if b.method_name == method]
        new_seq = [b for b in new_branches if b.method_name == method]
        old_ids = [b.branch_id for b in old_seq]
        new_ids = [b.branch_id for b in new_seq]
        # 旧・新の両方に存在する ID のみ対象
        common = [bid for bid in old_ids if bid in set(new_ids)]
        old_order = [bid for bid in old_ids if bid in set(common)]
        new_order = [bid for bid in new_ids if bid in set(common)]
        # 異なる condition_str を持つペアの前後関係を比較
        for i, x in enumerate(old_order):
            for y in old_order[i+1:]:
                cond_x = next(b.condition for b in old_branches if b.branch_id == x)
                cond_y = next(b.condition for b in old_branches if b.branch_id == y)
                if cond_x == cond_y:
                    continue
                ni, nj = new_order.index(x), new_order.index(y)
                if ni > nj:  # 旧では x→y だったのに新では y→x
                    warnings.append(
                        f"WARN: {method} で {x} と {y} の順序が逆転。"
                        f"シフトの可能性あり。TC-ID 割り当てを確認してください。"
                    )
    return warnings
```

再生成時に旧 Markdown と比較し、差分情報を**出力 Markdown の分岐点一覧テーブルの `要確認` 列に直接記載**する（セクション 9 参照）。
TC-ID を記入する作業者が該当行を見た時点で気づけるようにするため。

`要確認` 列に記載する内容:

| 状態 | 記載内容 |
|---|---|
| 前回と変化なし | （空欄） |
| 今回新規追加 | `新規` |
| シフトの可能性あり | `⚠ B-xxx との順序逆転` |
| 祖先チェーンが変わった | `祖先変更 (旧: B-xxx > B-yyy)` |

前回存在したが今回消えた B-ID は行自体がなくなるため、テーブルとは別に
`## 削除された分岐` セクションを出力末尾に追記する。
TC-ID が割り当て済みだった場合は `[TC割当済]` を付記する。

**限界**: 同一メソッド内に異なる condition_str を持つ B-ID が存在しない場合（同条件の分岐のみのメソッド）は検出不可。

---

## 6. ノード型別の情報取得

### if_statement

```
tree-sitter フィールド:
  condition   → parenthesized_expression（さらに内側が実際の条件式）
  consequence → block（then 節）
  alternative → else_clause（else 節、optional）

condition_str の取得:
  cond_node = node.child_by_field_name('condition')
  cond_str  = cond_node.text.decode()
  # → "(user == null)" ※括弧込み。strip('()') で括弧を外す

&&/|| の判定:
  cond_node の内側 named_children[0] が binary_expression かどうかを確認
```

### enhanced_for_statement（拡張 for）

```
tree-sitter フィールド:
  type  → 変数の型
  name  → ループ変数名（identifier）
  value → イテラブル式
  body  → ブロック

condition_str の取得:
  var_name  = node.child_by_field_name('name').text.decode()
  iterable  = node.child_by_field_name('value').text.decode()
  cond_str  = f"{var_name} : {iterable}"
```

### for_statement（通常 for）

```
tree-sitter フィールド:
  init      → 初期化式
  condition → 継続条件式
  update    → 更新式
  body      → ブロック

condition_str の取得:
  cond_node = node.child_by_field_name('condition')
  cond_str  = cond_node.text.decode() if cond_node else "(条件なし)"
```

### switch_statement

```
tree-sitter フィールド:
  condition → parenthesized_expression
  body      → switch_block

case の列挙:
  switch_block の children から switch_block_statement_group を取得
  各グループの先頭 switch_label から case 値を取得
  label.children に 'case' キーワードがあれば case 値あり、なければ default
```

### try_statement

```
tree-sitter フィールド:
  body          → block
  catch_clause  → 複数可（named_children から type=='catch_clause' でフィルタ）
  finally_clause → optional

catch の例外型取得:
  catch_clause → catch_formal_parameter → type → text.decode()
  複数型（multi-catch）: type_list の各 type をパイプ区切り
```

---

## 6-B. JavaScript ノード型別の情報取得

### for_in_statement（JS）

```
tree-sitter フィールド:
  left  → 変数宣言または識別子（キー変数）
  right → 走査対象オブジェクト
  body  → statement_block

condition_str の取得:
  key_str  = node.child_by_field_name('left').text.decode()
  obj_str  = node.child_by_field_name('right').text.decode()
  cond_str = f"{key_str} in {obj_str}"
  # → "key in obj" ※ for...in はオブジェクトのキーを列挙
```

### for_of_statement（JS）

```
tree-sitter フィールド:
  left  → 変数宣言または識別子（値変数）
  right → イテラブル式
  body  → statement_block

condition_str の取得:
  var_str  = node.child_by_field_name('left').text.decode()
  iter_str = node.child_by_field_name('right').text.decode()
  cond_str = f"{var_str} of {iter_str}"
  # → "item of items" ※ Java の enhanced_for に相当
```

### try_statement（JS 差分）

```
Java との差分:
  Java は catch_clause が複数（multi-catch）存在しうるが、
  JS は catch ブロックが最大 1 つ（型指定なし）。
  → アウトカムは常に「正常 + catch」の 2 固定。

  例外変数名の取得:
    catch_clause 直下の identifier または object_pattern を参照する
    （Java の catch_formal_parameter に相当するノードは存在しない）

  condition_str の取得:
    catch_clause 内の identifier.text.decode() を使用
    例: "catch (e)" → condition_str = "catch (e)"
```

### ternary_expression（JS 新規）

```
tree-sitter フィールド:
  condition   → 条件式
  consequence → 真の場合の式
  alternative → 偽の場合の式

condition_str の取得:
  cond_node = node.child_by_field_name('condition')
  cond_str  = cond_node.text.decode()
  branch_type = 'ternary'

生成するアウトカム:
  B-xxx-T  condition 真 → consequence を評価
  B-xxx-F  condition 偽 → alternative を評価
```

> **注意**: ternary は式（expression）なので、メソッド本体以外（デフォルト引数等）にも出現しうる。
> 初版では検出した行のメソッドスコープに属するものとして記録する。

---

## 6-C. MyBatis XML 要素別の情報取得

`xml.etree.ElementTree` で XML をパースし、以下の要素を取得する。

### `<if>` タグ

```
属性:
  test → 条件式文字列

condition_str の取得:
  elem.get('test')
  # → "categoryId != null"

生成するアウトカム:
  B-xxx-T  test が真 → この if ブロックの SQL が追加される
  B-xxx-F  test が偽 → この if ブロックがスキップされる
```

### `<choose>` / `<when>` / `<otherwise>` タグ

```
<choose> 直下の <when> 要素と <otherwise> 要素を列挙する。

各 <when> の condition_str:
  elem.get('test')

<otherwise> の condition_str:
  "otherwise"（固定文字列）

生成するアウトカム:
  B-xxx-0  最初の when 条件が真
  B-xxx-1  2番目の when 条件が真（最初は偽）
  ...
  B-xxx-N  otherwise（全 when が偽）
```

### `<foreach>` タグ

```
属性:
  collection → コレクション式
  item       → ループ変数名

condition_str の取得:
  f"{elem.get('item')} in {elem.get('collection')}"

生成するアウトカム:
  B-xxx-0  コレクションが空 → 展開されない
  B-xxx-N  コレクションが非空 → 展開される
```

### SQL 本体（層2）の情報取得

`<select>`, `<update>`, `<delete>`, `<insert>` タグのテキストを `sqlglot.parse_one()` に渡す。

```python
import sqlglot

ast = sqlglot.parse_one(sql_text, dialect="mysql")

# WHERE 句の有無
has_where = ast.find(sqlglot.expressions.Where) is not None

# SQL 種別
sql_kind = type(ast).__name__  # "Select" / "Update" / "Delete" / "Insert"

# CASE WHEN の数
case_nodes = list(ast.find_all(sqlglot.expressions.Case))
```

DAO インターフェース（.java）を `--dao` オプションで渡すと戻り型を参照できる:

```python
# 戻り型が List<T> かどうかで SELECT のアウトカムを決定
# → java ファイルをパースしてメソッドの戻り型を抽出
```

---

## 7. 複合条件（`&&` / `||`）の分解

`&&` を例に、`binary_expression` を再帰的に平坦化する。

```
入力: node（binary_expression, operator='&&'）

_flatten_and(node):
  left  = node.child_by_field_name('left')
  right = node.child_by_field_name('right')
  result = []
  if left.type == 'binary_expression' and left operator == '&&':
      result += _flatten_and(left)
  else:
      result.append(left.text.decode())
  result.append(right.text.decode())
  return result

A && B && C → ["A", "B", "C"]

生成するアウトカム:
  B-xxx-F1  A = false → 全体 false（短絡）
  B-xxx-F2  A = true, B = false → 全体 false（短絡）
  B-xxx-F3  A = true, B = true, C = false → 全体 false
  B-xxx-T   全て true → 全体 true
```

`||` は T/F が逆になる同様の処理。

---

## 8. CLI インターフェース

```
uv run python unittest/branch-extractor/branch_extract.py <file> --method <name> [options]

引数:
  file                解析対象の単一ファイル（.java / .js / .mjs / .cjs / .xml）

必須オプション:
  --method / -m       解析対象を1メソッドに限定する（必須・省略不可）
                      .java / .js の場合 → メソッド名（例: placeOrder）
                      .xml の場合        → SQL の id 属性値（例: findByCategory）

任意オプション:
  --output / -o       出力先 .md ファイル（省略時: 標準出力）
  --dao <path>        DAO インターフェースの .java ファイルパス（.xml 解析時は必須）
                      SELECT の単一/リスト返却を判別してアウトカムを確定するために使用する

制約（違反時はエラー終了）:
  - --method は常に必須
  - <file> が .xml の場合、--dao は必須
  - <file> が .xml 以外（.java / .js）の場合、--dao は使用不可
  - --dao に指定するファイルは .java でなければならない
  Error: --method is required
  Error: --dao is required when <file> is a .xml mapper file
  Error: --dao is only valid when <file> is a .xml mapper file
  Error: --dao must point to a .java file
```

使用例：

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
  --dao ast-analyzer/sample-app/src/main/java/.../OrderDao.java `
  --output unittest/docs/branch-inventory-order-dao.md
```

---

## 9. Markdown 出力フォーマット

```markdown
# 分岐インベントリ: <対象パス>

**分岐点数**: N　**総アウトカム数**: M

## 分岐点一覧

| B-ID | クラス | メソッド | 行 | 種別 | 条件式 | アウトカム数 | 祖先チェーン | 要確認 |
|---|---|---|---|---|---|---|---|---|
| B-a1b2c3 | OrderServiceImpl | placeOrder | 25 | if | order == null | 2 | - | 新規 |
| B-3f7a2c | OrderServiceImpl | placeOrder | 38 | enhanced-for | item : order.getItems() | 2 | - | |
| B-9c1e4a | OrderServiceImpl | placeOrder | 39 | if | !productService.checkStock(...) | 2 | B-3f7a2c | ⚠ B-cc44ee との順序逆転 |
| B-cc44ee | OrderServiceImpl | placeOrder | 45 | for | i = 0; i < items.size(); i++ | 2 | B-3f7a2c | |
| B-f08b31 | OrderServiceImpl | placeOrder | 60 | if | items.isEmpty() | 2 | B-3f7a2c > B-cc44ee | 祖先変更 (旧: B-3f7a2c) |

## アウトカム詳細

| アウトカム ID | B-ID | クラス | メソッド | 行 | 種別 | ラベル | 説明 | 担当 TC-ID |
|---|---|---|---|---|---|---|---|---|
| B-3f7a2c-0 | B-3f7a2c | OrderServiceImpl | placeOrder | 38 | enhanced-for | 0回 | getItems() が空 → ループスキップ | |
| B-3f7a2c-N | B-3f7a2c | OrderServiceImpl | placeOrder | 38 | enhanced-for | 1回以上 | getItems() が非空 → ループ実行 | |

> 「担当 TC-ID」列はテストケース設計時に記入する  
> 「要確認」列は再生成時に自動記入される。空欄 = 前回生成時から変更なし

```markdown
## 削除された分岐

以下の分岐は前回生成時に存在したが今回のソースに見つからない。

| B-ID | クラス | メソッド | 条件式 | 備考 |
|---|---|---|---|---|
| B-d3a9f1 | OrderServiceImpl | cancelOrder | status == CANCELED | [TC割当済] |
| B-7e2c80 | OrderServiceImpl | cancelOrder | items.isEmpty() | |
```

**B-ID の採番規則**: セクション 5-B 参照。条件式が変わらない限り ID は不変のため、
ソースの前後にコードを追加・削除しても Markdown の差分が分岐そのものの変化を直接反映する。

---

## 10. 既知の制限事項

### Java

| 制限 | 内容 |
|---|---|
| Lambda / Stream | `list.stream().filter(x -> x > 0)` 内部の条件式は branch_extractor では対象外（メソッド本体として解析されない） |
| `&&` と `\|\|` の混合 | `(A && B) \|\| C` のような混合は最外側の `\|\|` として分類。内側の `&&` は初版では別途分解しない |
| 三項演算子 `? :` | `ternary_expression` を初版では対象外とする（JaCoCo は計測するが、サンプルアプリには存在しない） |
| 匿名クラス | 匿名クラス内のメソッドは外側のメソッド名に含まれて記録される（初版許容） |

### JavaScript

| 制限 | 内容 |
|---|---|
| 匿名コールバック | `arr.forEach(function() {...})` 内部の分岐は `<anonymous>@{line}` で記録（メソッド名なし） |
| 変数代入 arrow function | `const fn = () => {...}` は変数名を method_name に使う（オプション実装。初版では `<anonymous>@{line}`） |
| 動的プロパティアクセス | `obj[key]` 等の動的条件は condition_str にそのまま出力（分解しない） |
| `&&`/`\|\|` の混合 | Java 同様、最外側の演算子で分類。内側は初版では分解しない |
| `?.`（Optional Chaining） | `a?.b` の分岐として検出しない（初版許容） |
| Generator / async | `yield` / `await` が絡む制御フローは分岐として扱わない |

### MyBatis XML（DAO 層）

| 制限 | 内容 |
|---|---|
| UNIQUE 制約違反 | DDL を読まないと制約の有無が不明 → 手動でアウトカムに追記 |
| `SET col = col + #{qty}` の符号分岐 | 値の意味論 → 構造解析では検出不可 → 手動で境界値ケースとして追記 |
