# generate_pom.py 実装方針

## 概要

`metadata/screens/*.yaml` を読み込み、Jinja2 テンプレートを使って
`pom/*.ts`（TypeScript Page Object Model）を自動生成するスクリプト。
`extract_metadata.py` の直後に実行することを前提とする。

---

## ファイル配置

```
playwright-gen/collect/
  generate_pom.py             # メインスクリプト（本ファイルの対象）
  templates/
    page.ts.j2                # Jinja2 テンプレート（POM クラス）
    base_page.ts.j2           # BasePage テンプレート（初回のみ生成）

playwright-gen/pom/
  BasePage.ts                 # 手動編集可（初回生成後は上書きしない）
  LoginPage.ts                # 自動生成（毎回上書き）
  ProductListPage.ts          # 自動生成（毎回上書き）
  # ...
```

---

## CLI インタフェース

```powershell
# screens/*.yaml から pom/*.ts を全画面生成
uv run python playwright-gen/collect/generate_pom.py --config ast-analyzer/config.yaml

# 特定画面のみ再生成
uv run python playwright-gen/collect/generate_pom.py --config ast-analyzer/config.yaml --screen login

# dry-run（stdout で確認、ファイル書き込みなし）
uv run python playwright-gen/collect/generate_pom.py --config ast-analyzer/config.yaml --dry-run
```

### argparse 定義

| 引数 | 必須 | 説明 |
|---|---|---|
| `--config` | ○ | `ast-analyzer/config.yaml` のパス（出力先の基準パスに使用） |
| `--screen` | - | 単一画面 id を指定（省略時は全画面） |
| `--dry-run` | - | ファイル書き込みをスキップし stdout に出力 |

---

## 処理フロー（9ステップ）

### ① screens_index.yaml の読み込み

```python
screens_index = yaml.safe_load(
    Path("playwright-gen/metadata/screens_index.yaml").read_text(encoding="utf-8")
)
# skip_pom: true のエントリを除外
targets = [s for s in screens_index["screens"] if not s.get("skip_pom")]
```

---

### ② screens/{id}.yaml の読み込み

```python
for screen_meta in targets:
    screen = yaml.safe_load(
        Path(f"playwright-gen/metadata/screens/{screen_meta['id']}.yaml")
        .read_text(encoding="utf-8")
    )
```

---

### ③ Locator フィールドの列挙（constructor 用）

以下の優先順位で全 Locator を収集し、重複を排除する。

```python
locators = []

# forms[].inputs[]
for form in screen.get("forms", []):
    for inp in form.get("inputs", []):
        if inp.get("type") == "hidden":
            continue  # hidden は Locator 不要
        locators.append(Locator(
            name=f"{inp['id']}Input",
            selector=resolve_selector(inp),
        ))
    for btn in form.get("buttons", []):
        locators.append(Locator(
            name=resolve_locator_name(btn),
            selector=resolve_selector(btn),
        ))

# standalone_inputs[]
for inp in screen.get("standalone_inputs", []):
    locators.append(Locator(
        name=f"{inp['id']}Input",
        selector=resolve_selector(inp),
    ))

# js_actions[]
for action in screen.get("js_actions", []):
    locators.append(Locator(
        name=resolve_locator_name(action),
        selector=resolve_selector(action),
    ))
```

---

### ④ セレクタ文字列の解決

```python
def resolve_selector(element: dict) -> str:
    if element.get("id"):
        return f"#{element['id']}"
    if element.get("class"):
        return f".{element['class']}"
    if element.get("name"):
        return f'[name="{element["name"]}"]'
    if element.get("selector"):
        return element["selector"]
    raise ValueError(f"セレクタを解決できません: {element}")
```

---

### ⑤ goto() メソッドの生成

URL のパスパラメータ（`{id}` 等）を検出して引数付きメソッドを生成する。

```python
import re

RE_PATH_PARAM = re.compile(r'\{(\w+)\}')

def build_goto(url: str) -> GoToMethod:
    params = RE_PATH_PARAM.findall(url)
    # /product/detail/{id} → `${id}` に変換
    js_url = RE_PATH_PARAM.sub(lambda m: f'${{{m.group(1)}}}', url)
    args = [GoToArg(name=p, ts_type="number") for p in params]
    return GoToMethod(args=args, js_url=js_url)
```

---

### ⑥ waitForLoad() メソッドの生成

`assertions.on_load` を TypeScript の expect 文に変換する。

```python
def to_expect_stmt(assertion: dict) -> str:
    t = assertion["type"]
    value = assertion.get("value", "")
    if t == "url":
        pattern = value.replace("/", "\\/")
        return f"await expect(this.page).toHaveURL(/{pattern}/);"
    if t == "title":
        stripped = value.rstrip()
        if stripped.endswith('-'):
            # "商品詳細 -" のような動的タイトルの前方一致パターンは正規表現に変換
            escaped = re.escape(stripped)
            return f"await expect(this.page).toHaveTitle(/^{escaped}/);"
        return f"await expect(this.page).toHaveTitle('{value}');"
    if t == "h1":
        return f"await expect(this.page.locator('h1')).toHaveText('{value}');"
    raise ValueError(f"未対応の assertion type: {t}")
```

---

### ⑦ フォームアクションメソッドの生成

フォームごとに `forms[].inputs[]`（hidden 除く）を引数として `fill → click` を生成する。

```python
def build_form_method(form: dict, screen_inputs: dict) -> FormMethod:
    inputs = [i for i in form.get("inputs", []) if i.get("type") != "hidden"]
    buttons = form.get("buttons", [])

    # メソッド名: submit ボタンの label をキャメルケース化
    method_name = to_camel_case(buttons[0]["label"]) if buttons else "submit"

    # 引数の型推論
    args = [MethodArg(name=i["id"], ts_type=infer_ts_type(i)) for i in inputs]

    # confirm_dialog がある場合はダイアログ処理を先頭に挿入
    has_confirm = any(b.get("confirm_dialog") for b in buttons)

    return FormMethod(name=method_name, args=args, inputs=inputs, buttons=buttons, has_confirm=has_confirm)

def infer_ts_type(input_def: dict) -> str:
    type_map = {
        "text": "string", "password": "string", "email": "string",
        "textarea": "string", "number": "number", "select": "string",
    }
    return type_map.get(input_def.get("type", "text"), "string")
```

---

### ⑧ JS アクションメソッドの生成

`reads_inputs[]` を `standalone_inputs` の `type` 属性から型推論して引数化する。

```python
def build_js_method(action: dict, standalone_inputs: list) -> JsMethod:
    # reads_inputs の id から standalone_inputs の型情報を引く
    input_map = {i["id"]: i for i in standalone_inputs}
    args = [
        MethodArg(name=inp_id, ts_type=infer_ts_type(input_map[inp_id]))
        for inp_id in action.get("reads_inputs", [])
        if inp_id in input_map
    ]
    # action_id: クリック対象ボタンの Locator 名
    try:
        action_id = resolve_locator_name(action)
    except ValueError:
        # js_fn は既にキャメルケースのためそのまま使用
        action_id = action["js_fn"] + "Btn"
    return JsMethod(
        name=action["js_fn"],
        args=args,
        reads_inputs=[inp_id for inp_id in action.get("reads_inputs", []) if inp_id in input_map],
        action_id=action_id,
    )
```

---

### ⑨ Jinja2 テンプレートへの変数渡しと .ts ファイル出力

```python
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader("playwright-gen/collect/templates"))
# カスタムフィルタを登録
env.filters["pascal_case"] = to_pascal_case
env.filters["camel_case"]  = to_camel_case

template = env.get_template("page.ts.j2")
content = template.render(
    screen=screen,
    locators=locators,
    goto=goto_method,
    on_load_stmts=on_load_stmts,
    form_methods=form_methods,
    js_methods=js_methods,
)

output_path = Path(f"playwright-gen/pom/{to_pascal_case(screen['id'])}Page.ts")
if not dry_run:
    output_path.write_text(content, encoding="utf-8")
else:
    print(content)
```

- 出力ファイル名: `pom/{PascalCase(id)}Page.ts`
- 既存ファイルは**無条件上書き**（手動編集は継承クラスで対応）
- `BasePage.ts` は初回のみ生成し、以降は上書きしない

---

## Jinja2 テンプレート（page.ts.j2）

```jinja2
{# collect/templates/page.ts.j2 #}
import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

export class {{ screen.id | pascal_case }}Page extends BasePage {
{% for loc in locators %}
  readonly {{ loc.name }}: Locator;
{% endfor %}

  constructor(page: Page) {
    super(page);
{% for loc in locators %}
    this.{{ loc.name }} = page.locator('{{ loc.selector }}');
{% endfor %}
  }

  async goto({{ goto.args | join(', ', attribute='ts_sig') }}) {
    await this.page.goto(`{{ goto.js_url }}`);
  }

  async waitForLoad() {
{% for stmt in on_load_stmts %}
    {{ stmt }}
{% endfor %}
  }

{% for method in form_methods %}
  async {{ method.name }}({{ method.args | join(', ', attribute='ts_sig') }}) {
{% if method.has_confirm %}
    this.page.on('dialog', dialog => dialog.accept());
{% endif %}
{% for inp in method.inputs %}
{% if inp.type == 'select' %}
    await this.{{ inp.id }}Input.selectOption(String({{ inp.id }}));
{% else %}
    await this.{{ inp.id }}Input.fill(String({{ inp.id }}));
{% endif %}
{% endfor %}
{% for btn in method.buttons %}
    await this.{{ btn | locator_name }}.click();
{% endfor %}
  }

{% endfor %}
{% for method in js_methods %}
  async {{ method.name }}({{ method.args | join(', ', attribute='ts_sig') }}) {
{% for inp_id in method.reads_inputs %}
    await this.{{ inp_id }}Input.fill(String({{ inp_id }}));
{% endfor %}
    await this.{{ method.action_id }}.click();
  }

{% endfor %}
}
```

---

## BasePage テンプレート（base_page.ts.j2）

```typescript
// pom/BasePage.ts  ← 初回のみ生成（以降は手動管理可）
import { Page } from '@playwright/test';

export abstract class BasePage {
  protected readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  abstract goto(...args: unknown[]): Promise<void>;
  abstract waitForLoad(): Promise<void>;
}
```

---

## ユーティリティ関数

```python
import re

def to_pascal_case(s: str) -> str:
    """snake_case または kebab-case → PascalCase"""
    return ''.join(word.capitalize() for word in re.split(r'[_\-]', s))

def to_camel_case(s: str) -> str:
    """snake_case / 日本語ラベル → camelCase"""
    # 日本語ラベルの場合はそのまま返す（テンプレート側で使わない前提）
    words = re.split(r'[_\-\s]', s)
    return words[0].lower() + ''.join(w.capitalize() for w in words[1:])

def resolve_locator_name(element: dict) -> str:
    """ボタン・JS アクションの Locator 名を解決する"""
    if element.get("id"):
        return element["id"]              # id あり → そのまま（例: loginBtn）
    if element.get("class"):
        # btn-danger → dangerBtn
        cls = element["class"].replace("btn-", "")
        return to_camel_case(cls) + "Btn"
    if element.get("selector"):
        # ".btn-danger" → "dangerBtn"
        sel = element["selector"].lstrip(".")
        cls = sel.split(".")[0].replace("btn-", "")
        return to_camel_case(cls) + "Btn"
    if element.get("label"):
        return to_camel_case(element["label"]) + "Btn"
    if element.get("js_fn"):
        # js_fn は既にキャメルケース（addToCartWithQuantity → addToCartWithQuantityBtn）
        return element["js_fn"] + "Btn"
    raise ValueError(f"Locator 名を解決できません: {element}")
```

---

## js_actions のセレクタ前提条件

`generate_pom.py` は `screens/*.yaml` の `js_actions` にボタン識別子（`id` または `selector`）が
付与済みであることを前提とする。この付与は `extract_metadata.py` の `collect_onclick_map()` が行う。

`extract_metadata.py` では、JS ファイルを複数 JSP で共有している場合に関数が誤検知される問題を
次のロジックで解消している：

```python
# parse_js_for_screen 内
onclick_map = collect_onclick_map(soup)   # JSP の onclick ボタン → {fn_name: {id or selector}}
js_actions = [a for a in js_actions if a.get('js_fn') in onclick_map]  # 誤検知を除外
for action in js_actions:
    action.update(onclick_map[action['js_fn']])   # id/selector を付与
```

識別子が解決できない場合（JSP にボタンが存在しない等）、`generate_pom.py` は
`selector: "FIXME"` でロケータを生成し警告ログを出力して続行する。

---

## モジュール構成

```python
generate_pom.py
  main()
    load_screens_index()       # ① screens_index.yaml 読み込み
    for screen_meta in targets:
      screen = load_screen_yaml()      # ② 個別 screens/{id}.yaml 読み込み
      locators = build_locators()      # ③④ Locator 列挙 + セレクタ解決
      goto = build_goto()              # ⑤ goto() 生成
      on_load_stmts = build_on_load()  # ⑥ waitForLoad() 生成
      form_methods = build_form_methods()  # ⑦ フォームメソッド生成
      js_methods = build_js_methods()      # ⑧ JS アクションメソッド生成
      render_and_write()               # ⑨ テンプレート展開 + 出力
    ensure_base_page()         # BasePage.ts が存在しない場合のみ生成
```

---

## 依存ライブラリ

| ライブラリ | 用途 | 取得元 |
|---|---|---|
| `pyyaml` | YAML 読み込み | 既存依存 |
| `jinja2` | テンプレート展開 | `pyproject.toml` に追加 |

---

## エラーハンドリング方針

| 状況 | 対処 |
|---|---|
| `screens/{id}.yaml` が存在しない | エラーログを出力して当該画面をスキップ |
| セレクタを解決できない要素がある | `ValueError` をキャッチし警告ログを出力（`selector: "FIXME"` で出力して続行） |
| テンプレートファイルが存在しない | 即時エラー終了（前提条件エラー） |

---

## メソッド命名規則まとめ

| 対象 | 命名規則 | 例 |
|---|---|---|
| input 系 Locator | `{id}Input` | `usernameInput` |
| ボタン系 Locator（id あり） | `{id}` | `loginBtn` |
| ボタン系 Locator（class のみ） | `{camelCase(class 除く btn-)}Btn` | `dangerBtn` |
| フォーム submit メソッド | `{camelCase(button.label)}` | `login()`, `search()` |
| JS アクション メソッド | `{js_fn}` そのまま | `addToCartWithQuantity()` |

---

## 実装の優先順位

| フェーズ | 実装内容 | 備考 |
|---|---|---|
| Phase 1 | `BasePage.ts` の手書き + ③④⑤⑥⑦ | フォームのみの画面（login / register）で動作確認 |
| Phase 2 | ⑧ JS アクションメソッド生成 | standalone_inputs を持つ商品詳細画面で検証 |
| Phase 3 | Jinja2 テンプレート化（⑨） | Phase 1/2 はハードコード出力でもよい |
