# extract_metadata.py 実装方針

## 概要

JSP ファイルの DOM パース・JS 静的解析・Neo4j クエリを組み合わせ、
`metadata/screens/*.yaml` と `metadata/screens_index.yaml` を生成するスクリプト。

---

## ファイル配置

```
playwright-gen/collect/
  extract_metadata.py         # メインスクリプト（本ファイルの対象）
  transitions_query.cypher    # Neo4j クエリ（遷移情報取得用）
  screens_master.yaml         # URL の正となる手動管理ファイル（後述）
```

---

## CLI インタフェース

```powershell
# 全画面生成
uv run python playwright-gen/collect/extract_metadata.py --config ast-analyzer/config.yaml

# 特定画面のみ再生成
uv run python playwright-gen/collect/extract_metadata.py --config ast-analyzer/config.yaml --screen login

# dry-run（ファイル書き込みなし、stdout 確認）
uv run python playwright-gen/collect/extract_metadata.py --config ast-analyzer/config.yaml --dry-run
```

### argparse 定義

| 引数 | 必須 | 説明 |
|---|---|---|
| `--config` | ○ | `ast-analyzer/config.yaml` のパス |
| `--screen` | - | 単一画面 id を指定（省略時は全画面） |
| `--dry-run` | - | ファイル書き込みをスキップし stdout に出力 |

---

## 処理フロー（6ステップ）

### ① 対象 JSP ファイルの列挙

1. `config.yaml` から `view_dir`（例: `ast-analyzer/sample-app/src/main/webapp/WEB-INF/views/`）を読み込む
2. `screens_master.yaml`（手動管理）を読み込み、画面 id・title・url・jsp_path の対応表を構築する
   - `screens_master.yaml` が存在しない場合は JSP パスから id を推測して自動生成する（初回のみ）
3. `--screen` 指定がある場合は対象をその画面のみに絞る

**`screens_master.yaml` の形式（手動管理）:**

```yaml
screens:
  - id: login
    title: ログイン
    url: /user/login
    jsp: user/login.jsp
  - id: product_list
    title: 商品一覧
    url: /product/list
    jsp: product/list.jsp
  # ...
```

> URL は `@RequestMapping` ではなく設計書を正とするため、このファイルを手動で管理する。

---

### ② JSP の DOM パース（BeautifulSoup）

各 JSP ファイルを BeautifulSoup で読み込み、以下の情報を抽出する。

#### forms[] の抽出

```python
for form in soup.find_all('form'):
    form_id    = form.get('id')           # <form id="loginForm">
    action     = form.get('action', '')   # <form action="/user/login">
    method     = form.get('method', 'get').lower()
    inputs     = extract_inputs(form)     # form 内の input/select/textarea
    buttons    = extract_buttons(form)    # form 内の submit ボタン
```

#### inputs[] の抽出ルール

| タグ | 抽出項目 |
|---|---|
| `<input>` | id, name, type, required（属性の有無）, value（hidden のみ）|
| `<select>` | id, name, options[]（value + label）, required |
| `<textarea>` | id, name, required |

- `label` は `<label for="id">` のテキスト、または隣接テキストノードから取得する
- `required` 属性が存在する場合は `required: true`（値に関わらず）

#### buttons[] の抽出ルール

- `button[type=submit]` または `input[type=submit]` を対象とする
- `data-confirm` 属性 または `onclick="confirm('...')"` を検出した場合は `confirm_dialog` に設定する
- `id` がない場合は `class` を代替セレクタとして使用する

#### standalone_inputs[] の抽出

- `soup.find_all('input')` から `form` 内のものを除外する
- `id` 属性を持つもののみを対象とする（JS の `getElementById` で参照される前提）

#### nav_links[] の抽出

- `soup.find_all('a', href=True)` を列挙する
- `http://` / `https://` 始まりの外部リンクは除外する
- href を `screens_master.yaml` の `url` と前方一致で照合し `transition_to` を解決する

#### assertions の抽出

```python
title_text = soup.find('title').get_text(strip=True)   # → on_load[type=title]
h1_text    = soup.find('h1').get_text(strip=True)       # → on_load[type=h1]
url_pattern = screen_meta['url']                        # → on_load[type=url]（screens_master から転記）
```

---

### ③ JS 解析（正規表現）

対象は JSP 内の `<script>` タグ、および `<script src="...">` で読み込む外部 `.js` ファイル。

#### js_actions[] の抽出

```python
# onclick="foo()" → js_fn: foo
RE_ONCLICK = re.compile(r'onclick=["\'](\w+)\(')

# JS 関数ボディの reads_inputs 抽出
RE_GET_ELEMENT = re.compile(r'document\.getElementById\(["\'](\w+)["\']\)')

# window.location.href の遷移先抽出（静的解決可能な場合のみ）
RE_LOCATION = re.compile(r'window\.location\.href\s*=\s*["\']([^"\']+)["\']')
```

- `RE_GET_ELEMENT` でマッチした id を `reads_inputs` に追加する
- `RE_LOCATION` でマッチした URL は `screens_master.yaml` と照合し `transition_to` を解決する
- 変数代入（`window.location.href = url`）の場合は静的解析不可のため `transition_to: null`、`unresolved: true` を付与する

---

### ④ Neo4j クエリ（遷移情報補完）

`unresolved: true` の `transition_to` を Neo4j の `TRANSITIONS_TO` エッジで補完する。

**`transitions_query.cypher` の内容:**

```cypher
MATCH (b:Button)-[:TRANSITIONS_TO]->(s:Screen)
RETURN b.id AS source_id, b.selector AS source_selector, s.id AS target_screen

UNION

MATCH (j:JsFunction)-[:TRANSITIONS_TO]->(s:Screen)
RETURN j.name AS source_id, null AS source_selector, s.id AS target_screen
```

- ドライバは `ast-analyzer/graph/neo4j_client.py` の接続設定を流用する（`config.yaml` の `neo4j` セクション）
- クエリ結果を `{ source_id → target_screen }` の dict に変換し、`unresolved` フラグ付きエントリを上書きする
- Neo4j でも解決できない場合は `transition_to: null` のまま出力する（手動補完対象）

---

### ⑤ Java ソース解析（バリデーション突き合わせ）

#### バリデーション突き合わせの流れ

```
form.action + form.method
  → Neo4j: MATCH (c:ControllerMethod {url: action, method: method}) RETURN c.modelAttribute
  → モデルクラス名（例: com.example.sampleapp.model.User）を取得
  → Java ファイルを直接読み込み（config.yaml の src_dir から検索）
  → フィールドのアノテーションを正規表現でパース
```

**Bean Validation アノテーション → screens.yaml のマッピング:**

| アノテーション | screens.yaml への反映 |
|---|---|
| `@NotNull` / `@NotEmpty` / `@NotBlank` | `required: true`、`required_sources` に `java` を追加 |
| `@Size(min=N, max=M)` | `minlength: N`、`maxlength: M` |
| `@Min(N)` | `min: N` |
| `@Max(N)` | `max: N` |
| `@Email` | `format: email` |
| `@Pattern(regexp=...)` | `pattern: ...` |

**Java アノテーション抽出の正規表現:**

```python
RE_ANNOTATION = re.compile(
    r'@(NotNull|NotEmpty|NotBlank|Size|Min|Max|Email|Pattern)'
    r'(?:\(([^)]*)\))?'
)
RE_FIELD = re.compile(
    r'(?:private|protected|public)\s+\S+\s+(\w+)\s*;'
)
```

- フィールドの直前に出現するアノテーションのブロックを抽出して突き合わせる
- JSP の `input[name]` と Java フィールド名が一致するものを対象とする
- 差異がある場合は `validation_discrepancies` に記録する

---

### ⑥ screens/*.yaml への出力

```python
import yaml

# 画面ごとに個別ファイルへ書き込み
output_path = Path(f"playwright-gen/metadata/screens/{screen_id}.yaml")
if not dry_run:
    output_path.write_text(yaml.dump(screen_data, allow_unicode=True, sort_keys=False))
else:
    print(yaml.dump(screen_data, allow_unicode=True, sort_keys=False))
```

- `screens_index.yaml` も更新する（新規画面が追加された場合のみ差分マージ）
- 既存ファイルは**無条件上書き**（手動補完済みフィールドは上書きされることに注意）

> **手動補完済みフィールドの保護**: `url`、`preconditions`、`conditional_elements` は
> 上書きで失われる可能性がある。これらは `screens_master.yaml` に集約して管理し、
> スクリプトが毎回そちらから転記する設計とすることで保護する。

---

## モジュール構成

```python
extract_metadata.py
  main()
    load_config()           # config.yaml 読み込み
    load_screens_master()   # screens_master.yaml 読み込み（URL・手動管理情報）
    connect_neo4j()         # Neo4j ドライバ初期化
    for screen in targets:
      parse_jsp()           # ② JSP DOM パース
      parse_js()            # ③ JS 解析
      resolve_transitions() # ④ Neo4j 補完
      check_validation()    # ⑤ Java アノテーション突き合わせ
      write_yaml()          # ⑥ ファイル出力
    update_screens_index()  # screens_index.yaml 更新
```

---

## 依存ライブラリ

| ライブラリ | 用途 | 取得元 |
|---|---|---|
| `beautifulsoup4` | JSP DOM パース | `pyproject.toml` に追加 |
| `lxml` | BeautifulSoup のパーサ（HTML5 相当） | 同上 |
| `pyyaml` | YAML 読み書き | 同上（既存依存） |
| `neo4j` | Neo4j ドライバ | 同上（ast-analyzer と共有） |

`ast-analyzer/graph/neo4j_client.py` の接続クラスをそのまま流用する。

---

## エラーハンドリング方針

| 状況 | 対処 |
|---|---|
| JSP ファイルが見つからない | 警告ログを出力し当該画面をスキップ |
| `<title>` / `<h1>` タグが存在しない | `null` で出力し警告を付与 |
| Neo4j 接続失敗 | 遷移補完をスキップし `unresolved: true` のまま続行 |
| Java ファイルが見つからない | バリデーション突き合わせをスキップし `bound_class: null` で出力 |

---

## 実装の優先順位

フェーズ分けして段階的に実装する。

| フェーズ | 実装内容 | 備考 |
|---|---|---|
| Phase 1 | ②③（JSP DOM パース + JS 正規表現） | Neo4j なしで動作確認可能 |
| Phase 2 | ④（Neo4j 遷移補完） | Phase 1 の出力に差分追加 |
| Phase 3 | ⑤（Java バリデーション突き合わせ） | 複雑度が高いため最後 |
