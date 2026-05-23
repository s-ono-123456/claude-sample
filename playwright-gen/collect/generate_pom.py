"""
metadata/screens/*.yaml を読み込み、Jinja2 テンプレートを使って
pom/*.ts (TypeScript Page Object Model) を自動生成するスクリプト。

Usage:
    uv run python playwright-gen/collect/generate_pom.py --config ast-analyzer/config.yaml
    uv run python playwright-gen/collect/generate_pom.py --config ast-analyzer/config.yaml --screen login
    uv run python playwright-gen/collect/generate_pom.py --config ast-analyzer/config.yaml --dry-run
"""

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

log = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
METADATA_DIR = SCRIPT_DIR.parent / 'metadata'
SCREENS_DIR = METADATA_DIR / 'screens'
POM_DIR = SCRIPT_DIR.parent / 'pom'
TEMPLATES_DIR = SCRIPT_DIR / 'templates'

RE_PATH_PARAM = re.compile(r'\{(\w+)\}')


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------

@dataclass
class Locator:
    name: str
    selector: str


@dataclass
class GoToArg:
    name: str
    ts_type: str

    @property
    def ts_sig(self) -> str:
        return f"{self.name}: {self.ts_type}"


@dataclass
class GoToMethod:
    args: list
    js_url: str


@dataclass
class MethodArg:
    name: str
    ts_type: str

    @property
    def ts_sig(self) -> str:
        return f"{self.name}: {self.ts_type}"


@dataclass
class FormMethod:
    name: str
    args: list
    inputs: list
    buttons: list
    has_confirm: bool


@dataclass
class JsMethod:
    name: str
    args: list
    reads_inputs: list
    action_id: str


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def to_pascal_case(s: str) -> str:
    return ''.join(word.capitalize() for word in re.split(r'[_\-]', s))


def to_camel_case(s: str) -> str:
    words = re.split(r'[_\-\s]', s)
    if not words:
        return s
    return words[0].lower() + ''.join(w.capitalize() for w in words[1:])


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


def resolve_locator_name(element: dict) -> str:
    if element.get("id"):
        return element["id"]
    if element.get("class"):
        cls = element["class"].replace("btn-", "")
        return to_camel_case(cls) + "Btn"
    if element.get("selector"):
        # ".btn-danger" → "dangerBtn"、".btn-primary.foo" → 先頭クラスのみ
        sel = element["selector"].lstrip(".")
        first_cls = sel.split(".")[0]
        cls = first_cls.replace("btn-", "")
        return to_camel_case(cls) + "Btn"
    if element.get("label"):
        return to_camel_case(element["label"]) + "Btn"
    if element.get("js_fn"):
        return element["js_fn"] + "Btn"
    raise ValueError(f"Locator 名を解決できません: {element}")


def infer_ts_type(input_def: dict) -> str:
    type_map = {
        "text": "string", "password": "string", "email": "string",
        "textarea": "string", "number": "number", "select": "string",
    }
    return type_map.get(input_def.get("type", "text"), "string")


def to_expect_stmt(assertion: dict) -> str:
    t = assertion["type"]
    value = assertion.get("value", "")
    if t == "url":
        # {id} 等のパスパラメータを「/以外の1文字以上」にマッチする正規表現に置換してからスラッシュをエスケープ
        pattern = RE_PATH_PARAM.sub('[^/]+', value).replace("/", "\\/")
        return f"await expect(this.page).toHaveURL(/{pattern}/);"
    if t == "title":
        stripped = value.rstrip()
        if stripped.endswith('-'):
            escaped = re.escape(stripped)
            return f"await expect(this.page).toHaveTitle(/^{escaped}/);"
        return f"await expect(this.page).toHaveTitle('{value}');"
    if t == "h1":
        return f"await expect(this.page.locator('h1')).toHaveText('{value}');"
    raise ValueError(f"未対応の assertion type: {t}")


# ---------------------------------------------------------------------------
# ビルダ関数
# ---------------------------------------------------------------------------

def build_locators(screen: dict) -> list[Locator]:
    locators = []
    seen_names: set[str] = set()

    def add(name: str, selector: str) -> None:
        if name not in seen_names:
            seen_names.add(name)
            locators.append(Locator(name=name, selector=selector))

    for form in screen.get("forms", []):
        for inp in form.get("inputs", []):
            if inp.get("type") == "hidden":
                continue
            try:
                sel = resolve_selector(inp)
                add(f"{inp['id']}Input", sel)
            except (ValueError, KeyError) as e:
                log.warning("input Locator をスキップ: %s", e)

        for btn in form.get("buttons", []):
            try:
                name = resolve_locator_name(btn)
                sel = resolve_selector(btn)
                add(name, sel)
            except ValueError as e:
                log.warning("button Locator をスキップ: %s — selector=FIXME で続行")
                name = btn.get("label", "unknown") + "Btn"
                add(name, "FIXME")

    for inp in screen.get("standalone_inputs", []):
        try:
            sel = resolve_selector(inp)
            add(f"{inp['id']}Input", sel)
        except (ValueError, KeyError) as e:
            log.warning("standalone_input Locator をスキップ: %s", e)

    for action in screen.get("js_actions", []):
        try:
            name = resolve_locator_name(action)
        except ValueError:
            continue
        try:
            sel = resolve_selector(action)
        except ValueError:
            log.warning("js_action '%s' のセレクタを解決できません — FIXME で続行", name)
            sel = "FIXME"
        add(name, sel)

    return locators


def build_goto(url: str) -> GoToMethod:
    params = RE_PATH_PARAM.findall(url)
    js_url = RE_PATH_PARAM.sub(lambda m: f'${{{m.group(1)}}}', url)
    args = [GoToArg(name=p, ts_type="number") for p in params]
    return GoToMethod(args=args, js_url=js_url)


def build_on_load(screen: dict) -> list[str]:
    stmts = []
    for assertion in screen.get("assertions", {}).get("on_load", []):
        try:
            stmts.append(to_expect_stmt(assertion))
        except ValueError as e:
            log.warning("assertion をスキップ: %s", e)
    return stmts


def build_form_methods(screen: dict) -> list[FormMethod]:
    methods = []
    for form in screen.get("forms", []):
        inputs = [i for i in form.get("inputs", []) if i.get("type") != "hidden"]
        buttons = form.get("buttons", [])

        if not inputs and not buttons:
            continue

        if buttons:
            method_name = to_camel_case(buttons[0].get("label", "submit"))
        else:
            method_name = "submit"

        args = []
        for i in inputs:
            if i.get("id"):
                args.append(MethodArg(name=i["id"], ts_type=infer_ts_type(i)))

        has_confirm = any(b.get("confirm_dialog") for b in buttons)

        methods.append(FormMethod(
            name=method_name,
            args=args,
            inputs=inputs,
            buttons=buttons,
            has_confirm=has_confirm,
        ))

    return methods


def build_js_methods(screen: dict) -> list[JsMethod]:
    methods = []
    standalone_inputs = screen.get("standalone_inputs", [])
    input_map = {i["id"]: i for i in standalone_inputs if i.get("id")}

    for action in screen.get("js_actions", []):
        js_fn = action.get("js_fn")
        if not js_fn:
            continue

        args = []
        valid_reads = []
        for inp_id in action.get("reads_inputs", []):
            if inp_id in input_map:
                args.append(MethodArg(name=inp_id, ts_type=infer_ts_type(input_map[inp_id])))
                valid_reads.append(inp_id)

        # action_id: Locator 名（クリック対象）
        try:
            action_id = resolve_locator_name(action)
        except ValueError:
            action_id = js_fn + "Btn"

        methods.append(JsMethod(
            name=js_fn,
            args=args,
            reads_inputs=valid_reads,
            action_id=action_id,
        ))

    return methods


# ---------------------------------------------------------------------------
# 出力
# ---------------------------------------------------------------------------

def render_and_write(
    env: Environment,
    screen: dict,
    locators: list,
    goto: GoToMethod,
    on_load_stmts: list,
    form_methods: list,
    js_methods: list,
    dry_run: bool,
) -> None:
    template = env.get_template("page.ts.j2")
    content = template.render(
        screen=screen,
        locators=locators,
        goto=goto,
        on_load_stmts=on_load_stmts,
        form_methods=form_methods,
        js_methods=js_methods,
    )

    class_name = to_pascal_case(screen["id"])
    output_path = POM_DIR / f"{class_name}Page.ts"

    if dry_run:
        print(f"// === {output_path} ===")
        print(content)
    else:
        POM_DIR.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        log.info("書き込み完了: %s", output_path)


def ensure_base_page(env: Environment, dry_run: bool) -> None:
    base_path = POM_DIR / "BasePage.ts"
    if base_path.exists():
        return

    template = env.get_template("base_page.ts.j2")
    content = template.render()

    if dry_run:
        print(f"// === {base_path} (初回生成) ===")
        print(content)
    else:
        POM_DIR.mkdir(parents=True, exist_ok=True)
        base_path.write_text(content, encoding="utf-8")
        log.info("BasePage.ts を生成しました: %s", base_path)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="screens/*.yaml から TypeScript POM を生成する")
    parser.add_argument("--config", required=True, help="ast-analyzer/config.yaml のパス（現在は未使用、将来の拡張用）")
    parser.add_argument("--screen", help="単一画面 id を指定（省略時は全画面）")
    parser.add_argument("--dry-run", action="store_true", help="ファイル書き込みをスキップし stdout に出力")
    args = parser.parse_args()

    # テンプレートエンジン初期化
    try:
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            keep_trailing_newline=True,
        )
    except Exception as e:
        log.error("テンプレートディレクトリが見つかりません: %s (%s)", TEMPLATES_DIR, e)
        sys.exit(1)

    # カスタムフィルタ登録
    env.filters["pascal_case"] = to_pascal_case
    env.filters["camel_case"] = to_camel_case
    env.filters["locator_name"] = resolve_locator_name

    # テンプレートファイルの存在確認
    for tmpl_name in ("page.ts.j2", "base_page.ts.j2"):
        try:
            env.get_template(tmpl_name)
        except TemplateNotFound:
            log.error("テンプレートファイルが見つかりません: %s", tmpl_name)
            sys.exit(1)

    # screens_index.yaml 読み込み
    index_path = METADATA_DIR / "screens_index.yaml"
    if not index_path.exists():
        log.error("screens_index.yaml が見つかりません: %s", index_path)
        sys.exit(1)

    screens_index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    targets = [s for s in screens_index.get("screens", []) if not s.get("skip_pom")]

    if args.screen:
        targets = [s for s in targets if s["id"] == args.screen]
        if not targets:
            log.error("画面が見つかりません: %s", args.screen)
            sys.exit(1)

    count = 0
    for screen_meta in targets:
        screen_id = screen_meta["id"]
        screen_path = SCREENS_DIR / f"{screen_id}.yaml"

        if not screen_path.exists():
            log.warning("screens/%s.yaml が見つかりません — スキップ", screen_id)
            continue

        screen = yaml.safe_load(screen_path.read_text(encoding="utf-8"))
        log.info("処理中: %s", screen_id)

        locators = build_locators(screen)
        goto = build_goto(screen.get("url", "/"))
        on_load_stmts = build_on_load(screen)
        form_methods = build_form_methods(screen)
        js_methods = build_js_methods(screen)

        render_and_write(
            env=env,
            screen=screen,
            locators=locators,
            goto=goto,
            on_load_stmts=on_load_stmts,
            form_methods=form_methods,
            js_methods=js_methods,
            dry_run=args.dry_run,
        )
        count += 1

    ensure_base_page(env, args.dry_run)

    log.info("完了: %d 画面", count)


if __name__ == "__main__":
    main()
