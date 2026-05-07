"""
Phase 3: JavaScript ファイルを解析して JsFunction / AjaxCall 情報を抽出する。

対応パターン:
  - 関数定義: function name() {} および var/let/const name = function() {}
  - AjaxCall: $.ajax, $.get/post, fetch, axios.*, ajaxGet/ajaxPost (カスタムラッパー)
  - ナビゲーション: window.location.href = '...'
  - 関数間呼び出し: functionA() 内で functionB() を呼ぶ
"""
import re
import logging
from pathlib import Path
from typing import List, Optional, Set, Tuple

from model.ir import AjaxCallInfo, JsFileInfo, JsFunctionInfo

log = logging.getLogger(__name__)

# コンテキストパス変数名 (URL抽出時にスキップ)
_CONTEXT_VARS: frozenset = frozenset({"contextPath", "ctx", "basePath", "rootPath"})

# JavaScript 予約語・組み込み名 (関数呼び出し記録から除外)
_SKIP_NAMES: frozenset = frozenset({
    "if", "for", "while", "do", "switch", "case", "return", "typeof",
    "instanceof", "new", "delete", "void", "throw", "try", "catch", "finally",
    "class", "extends", "super", "import", "export", "let", "var", "const",
    "function", "this", "arguments",
    "parseInt", "parseFloat", "isNaN", "isFinite",
    "String", "Number", "Boolean", "Array", "Object", "JSON", "Math",
    "Date", "RegExp", "Error", "TypeError", "RangeError", "SyntaxError",
    "Promise", "Map", "Set", "WeakMap", "WeakSet", "Symbol", "Proxy",
    "encodeURIComponent", "decodeURIComponent", "encodeURI", "decodeURI",
    "setTimeout", "setInterval", "clearTimeout", "clearInterval",
    "alert", "confirm", "prompt", "fetch", "eval", "Function",
    "document", "window", "navigator", "location", "history", "console",
    "XMLHttpRequest",
})

# ── 関数定義パターン ──────────────────────────────────────────────────────────
_RE_FN_DECL = re.compile(
    r"\bfunction\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\([^)]*\)\s*\{"
)
_RE_FN_EXPR = re.compile(
    r"\b(?:var|let|const)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*"
    r"function(?:\s+[a-zA-Z_$][a-zA-Z0-9_$]*)?\s*\([^)]*\)\s*\{"
)

# ── AjaxCall パターン ─────────────────────────────────────────────────────────
_RE_CUSTOM_AJAX = re.compile(
    r"\bajax(Get|Post|Put|Delete|Patch)\s*\(", re.IGNORECASE
)
_RE_JQUERY_SHORT = re.compile(
    r"\$\.(get|post|put|delete|patch)\s*\(", re.IGNORECASE
)
_RE_JQUERY_AJAX = re.compile(r"\$\.ajax\s*\(")
_RE_FETCH = re.compile(r"\bfetch\s*\(")
_RE_AXIOS = re.compile(r"\baxios\.(get|post|put|delete|patch)\s*\(", re.IGNORECASE)

# ── 画面遷移パターン ──────────────────────────────────────────────────────────
_RE_LOCATION_HREF = re.compile(r"\bwindow\.location(?:\.href)?\s*=\s*([^\n;]+)")
_RE_LOCATION_REPLACE = re.compile(r"\bwindow\.location\.replace\s*\(\s*([^)]+)")

# ── 関数呼び出し検出 ──────────────────────────────────────────────────────────
_RE_ANY_CALL = re.compile(r"\b([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(")


# ─────────────────────────────────────────────────────────────────────────────
# ユーティリティ
# ─────────────────────────────────────────────────────────────────────────────

def _match_braces(source: str, open_pos: int) -> int:
    """open_pos の '{' に対応する '}' の位置を返す。なければ -1。"""
    depth = 0
    i = open_pos
    n = len(source)

    while i < n:
        c = source[i]
        if c == "/" and i + 1 < n:
            if source[i + 1] == "/":
                nl = source.find("\n", i)
                i = nl + 1 if nl != -1 else n
                continue
            if source[i + 1] == "*":
                end = source.find("*/", i + 2)
                i = (end + 2) if end != -1 else n
                continue
        if c in ('"', "'", "`"):
            quote = c
            i += 1
            while i < n:
                ch = source[i]
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                if ch == quote:
                    i += 1
                    break
                i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _first_arg(text: str, start: int) -> str:
    """text[start] から始まる引数リストの第1引数文字列を返す (start は '(' の次の位置)。"""
    i = start
    n = len(text)
    depth = 0
    buf: List[str] = []
    in_str = False
    str_char = ""

    while i < n:
        c = text[i]
        if in_str:
            buf.append(c)
            if c == "\\" and i + 1 < n:
                buf.append(text[i + 1])
                i += 2
                continue
            if c == str_char:
                in_str = False
        else:
            if c in ('"', "'", "`"):
                in_str = True
                str_char = c
                buf.append(c)
            elif c in ("(", "[", "{"):
                depth += 1
                buf.append(c)
            elif c in (")", "]", "}"):
                if depth == 0:
                    break
                depth -= 1
                buf.append(c)
            elif c == "," and depth == 0:
                break
            else:
                buf.append(c)
        i += 1

    return "".join(buf).strip()


def _extract_url(expr: str) -> Tuple[str, bool]:
    """URL式から (正規化URL, unresolved) を返す。"""
    expr = expr.strip().rstrip(";").strip()

    # シンプルな文字列リテラル
    m = re.match(r'^[\'"]([^\'"]+)[\'"]$', expr)
    if m:
        return m.group(1), False

    # テンプレートリテラル
    m = re.match(r"^`([^`]+)`$", expr)
    if m:
        url = re.sub(r"\$\{[^}]+\}", "{var}", m.group(1))
        return url, True

    # 単純な識別子 (変数名)
    if re.match(r"^[a-zA-Z_$][a-zA-Z0-9_$]*$", expr):
        return expr, True

    # 文字列連結 (contextPath + '/path' + variable + ...)
    parts = re.split(r"\s*\+\s*", expr)
    url_parts: List[str] = []
    unresolved = False

    for part in parts:
        part = part.strip()
        if not part or part in _CONTEXT_VARS:
            continue
        # 条件式・関数呼び出しを含む部分は {var} 扱い
        if "?" in part or "(" in part:
            url_parts.append("{var}")
            unresolved = True
            continue
        m2 = re.match(r'^[\'"]([^\'"]*)[\'"]$', part)
        if m2:
            url_parts.append(m2.group(1))
        elif re.match(r"^\d+$", part):
            url_parts.append(part)
        else:
            url_parts.append("{var}")
            unresolved = True

    if url_parts:
        return "".join(url_parts), unresolved

    return expr[:60], True  # フォールバック


def _strip_strings_and_comments(source: str) -> str:
    """文字列・コメントをスペースに置換する (改行は保持)。"""
    result: List[str] = []
    i = 0
    n = len(source)

    while i < n:
        c = source[i]
        if c == "/" and i + 1 < n:
            if source[i + 1] == "/":
                nl = source.find("\n", i)
                end = nl if nl != -1 else n
                result.append(" " * (end - i))
                i = end
                continue
            if source[i + 1] == "*":
                end = source.find("*/", i + 2)
                end = (end + 2) if end != -1 else n
                chunk = source[i:end]
                result.append(re.sub(r"[^\n]", " ", chunk))
                i = end
                continue
        if c in ('"', "'", "`"):
            quote = c
            j = i + 1
            while j < n:
                ch = source[j]
                if ch == "\\" and j + 1 < n:
                    j += 2
                    continue
                if ch == quote:
                    j += 1
                    break
                j += 1
            chunk = source[i:j]
            result.append(re.sub(r"[^\n]", " ", chunk))
            i = j
            continue
        result.append(c)
        i += 1

    return "".join(result)


# ─────────────────────────────────────────────────────────────────────────────
# 抽出ロジック
# ─────────────────────────────────────────────────────────────────────────────

def _extract_ajax_calls(body: str) -> List[AjaxCallInfo]:
    """関数ボディから AjaxCallInfo リストを抽出する。"""
    calls: List[AjaxCallInfo] = []

    # カスタムラッパー: ajaxGet/ajaxPost(url, ...)
    for m in _RE_CUSTOM_AJAX.finditer(body):
        verb = m.group(1).upper()
        url_expr = _first_arg(body, m.end())
        url, unresolved = _extract_url(url_expr)
        line = body[: m.start()].count("\n") + 1
        calls.append(AjaxCallInfo(url=url, http_method=verb, unresolved=unresolved, line=line))

    # jQuery 短縮形: $.get/$.post(url, ...)
    for m in _RE_JQUERY_SHORT.finditer(body):
        verb = m.group(1).upper()
        url_expr = _first_arg(body, m.end())
        url, unresolved = _extract_url(url_expr)
        line = body[: m.start()].count("\n") + 1
        calls.append(AjaxCallInfo(url=url, http_method=verb, unresolved=unresolved, line=line))

    # $.ajax({url: '...', type: '...'})
    for m in _RE_JQUERY_AJAX.finditer(body):
        obj_start = body.find("{", m.end())
        if obj_start == -1:
            continue
        obj_end = _match_braces(body, obj_start)
        if obj_end == -1:
            continue
        obj_str = body[obj_start + 1: obj_end]

        url_m = re.search(r"\burl\s*:\s*([^\n,}]+)", obj_str)
        type_m = re.search(r"\b(?:type|method)\s*:\s*['\"]([A-Za-z]+)['\"]", obj_str)
        if url_m:
            url, unresolved = _extract_url(url_m.group(1).strip())
            verb = type_m.group(1).upper() if type_m else "GET"
            line = body[: m.start()].count("\n") + 1
            calls.append(AjaxCallInfo(url=url, http_method=verb, unresolved=unresolved, line=line))

    # fetch(url, {method: '...'})
    for m in _RE_FETCH.finditer(body):
        url_expr = _first_arg(body, m.end())
        url, unresolved = _extract_url(url_expr)
        rest_start = m.end() + len(url_expr)
        method_m = re.search(
            r"method\s*:\s*['\"]([A-Za-z]+)['\"]",
            body[rest_start: rest_start + 300],
        )
        verb = method_m.group(1).upper() if method_m else "GET"
        line = body[: m.start()].count("\n") + 1
        calls.append(AjaxCallInfo(url=url, http_method=verb, unresolved=unresolved, line=line))

    # axios.get/post/etc(url, ...)
    for m in _RE_AXIOS.finditer(body):
        verb = m.group(1).upper()
        url_expr = _first_arg(body, m.end())
        url, unresolved = _extract_url(url_expr)
        line = body[: m.start()].count("\n") + 1
        calls.append(AjaxCallInfo(url=url, http_method=verb, unresolved=unresolved, line=line))

    return calls


def _extract_location_hrefs(body: str) -> List[str]:
    """window.location.href = ... から遷移先URLを抽出する。"""
    hrefs: List[str] = []
    for pattern in (_RE_LOCATION_HREF, _RE_LOCATION_REPLACE):
        for m in pattern.finditer(body):
            raw = m.group(1).rstrip(");").strip()
            url, _ = _extract_url(raw)
            hrefs.append(url)
    return hrefs


def _extract_fn_calls(body: str, own_name: str) -> List[str]:
    """ボディ内のbare function calls (メソッドコールでないもの) を返す。"""
    cleaned = _strip_strings_and_comments(body)
    calls: List[str] = []
    seen: Set[str] = set()

    for m in _RE_ANY_CALL.finditer(cleaned):
        name = m.group(1)
        if name in _SKIP_NAMES or name == own_name:
            continue
        # メソッドコール (.name(...)) を除外
        pos = m.start()
        before = cleaned[:pos].rstrip()
        if before.endswith("."):
            continue
        # function キーワードの後は定義なので除外
        if before.endswith("function"):
            continue
        if name not in seen:
            calls.append(name)
            seen.add(name)

    return calls


def _find_functions(source: str) -> List[Tuple[str, int, int, int]]:
    """
    (fn_name, brace_open, brace_close, line_num) のリストを返す。
    同一の { 位置は重複除外する。
    """
    results: List[Tuple[str, int, int, int]] = []
    seen_brace: Set[int] = set()

    for pattern in (_RE_FN_DECL, _RE_FN_EXPR):
        for m in pattern.finditer(source):
            fn_name = m.group(1)
            brace_open = source.rfind("{", m.start(), m.end())
            if brace_open == -1 or brace_open in seen_brace:
                continue
            brace_close = _match_braces(source, brace_open)
            if brace_close == -1:
                continue
            line_num = source[: m.start()].count("\n") + 1
            seen_brace.add(brace_open)
            results.append((fn_name, brace_open, brace_close, line_num))

    results.sort(key=lambda x: x[1])
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 公開インターフェース
# ─────────────────────────────────────────────────────────────────────────────

def parse_js(file_path: str) -> Optional[JsFileInfo]:
    """JSファイルを解析して JsFileInfo を返す。関数が見つからなければ None。"""
    source = Path(file_path).read_text(encoding="utf-8", errors="ignore")

    fn_spans = _find_functions(source)
    if not fn_spans:
        log.debug("[JsParser] 関数なし: %s", file_path)
        return None

    functions: List[JsFunctionInfo] = []
    for fn_name, brace_open, brace_close, line_num in fn_spans:
        body = source[brace_open: brace_close + 1]

        ajax_calls = _extract_ajax_calls(body)
        fn_calls = _extract_fn_calls(body, fn_name)
        location_hrefs = _extract_location_hrefs(body)

        functions.append(JsFunctionInfo(
            name=fn_name,
            file_path=file_path,
            ajax_calls=ajax_calls,
            fn_calls=fn_calls,
            location_hrefs=location_hrefs,
            line=line_num,
        ))
        log.debug(
            "[JsParser] %s.%s: ajax=%d fn_calls=%d hrefs=%d",
            Path(file_path).name, fn_name,
            len(ajax_calls), len(fn_calls), len(location_hrefs),
        )

    log.debug("[JsParser] %s: %d functions", Path(file_path).name, len(functions))
    return JsFileInfo(path=file_path, functions=functions)
