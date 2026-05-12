"""
Phase 3: JS ↔ Controller / Button ↔ JsFunction のリンク解決
"""
import re
import logging
from typing import Dict, List, Set, Tuple

from model.ir import (
    AjaxCallInfo, ButtonInfo, ControllerInfo, ControllerMethodInfo,
    HttpMethod, JsFileInfo, JsFunctionInfo, ScreenInfo,
)

log = logging.getLogger(__name__)


def _normalize_url(url: str, context_path: str = "") -> str:
    url = url.split("?")[0].split("#")[0]
    if context_path and url.startswith(context_path):
        url = url[len(context_path):]
    return url.rstrip("/") or "/"


def _url_to_pattern(url: str) -> re.Pattern:
    """{var}/{id} などのパスパラメータをワイルドカードに変換した正規表現を返す。"""
    escaped = re.escape(url)
    escaped = re.sub(r"\\{[^}]+\\}", "[^/]+", escaped)
    return re.compile(f"^{escaped}$")


def _build_fn_index(js_files: List[JsFileInfo]) -> Dict[str, JsFunctionInfo]:
    """全 JsFunction を名前でインデックス化する (同名は最初のものを優先)。"""
    index: Dict[str, JsFunctionInfo] = {}
    for js_file in js_files:
        for fn in js_file.functions:
            if fn.name not in index:
                index[fn.name] = fn
    return index


def link_buttons_to_js_functions(
    screens: List[ScreenInfo],
    js_files: List[JsFileInfo],
) -> List[Tuple[ButtonInfo, ScreenInfo, JsFunctionInfo]]:
    """
    Button.onclick_fn → JsFunction のリンク。
    Returns: [(button, screen, js_function), ...]
    """
    fn_by_name = _build_fn_index(js_files)

    results: List[Tuple[ButtonInfo, ScreenInfo, JsFunctionInfo]] = []
    for screen in screens:
        for btn in screen.buttons:
            if not btn.onclick_fn:
                continue
            fn = fn_by_name.get(btn.onclick_fn)
            if fn:
                results.append((btn, screen, fn))
                log.debug("Button→JS: [%s] -> %s()", btn.onclick_fn, fn.name)

    return results


def link_js_function_calls(
    js_files: List[JsFileInfo],
) -> List[Tuple[JsFunctionInfo, JsFunctionInfo]]:
    """
    JsFunctionInfo.fn_calls を解決して JsFunction → CALLS → JsFunction のリストを返す。
    Returns: [(caller_fn, callee_fn), ...]
    """
    fn_by_name = _build_fn_index(js_files)

    results: List[Tuple[JsFunctionInfo, JsFunctionInfo]] = []
    seen: Set[Tuple[str, str, str, str]] = set()

    for js_file in js_files:
        for caller_fn in js_file.functions:
            for callee_name in caller_fn.fn_calls:
                callee_fn = fn_by_name.get(callee_name)
                if callee_fn is None:
                    continue
                key = (caller_fn.name, caller_fn.file_path, callee_fn.name, callee_fn.file_path)
                if key in seen:
                    continue
                seen.add(key)
                results.append((caller_fn, callee_fn))
                log.debug("JS→JS: %s -> %s", caller_fn.name, callee_fn.name)

    return results


def link_ajax_to_controllers(
    js_files: List[JsFileInfo],
    controllers: List[ControllerInfo],
    context_path: str = "",
) -> List[Tuple[JsFunctionInfo, AjaxCallInfo, ControllerInfo, ControllerMethodInfo]]:
    """
    JsFunction の AjaxCall.url を ControllerMethod.url に照合する。
    Returns: [(js_function, ajax_call, ctrl, ctrl_method), ...]
    """
    # Controller 側のパターンを事前構築
    all_methods: List[Tuple[ControllerInfo, ControllerMethodInfo, str, re.Pattern]] = []
    for ctrl in controllers:
        for cm in ctrl.methods:
            norm = _normalize_url(cm.url, context_path)
            all_methods.append((ctrl, cm, norm, _url_to_pattern(norm)))

    results = []
    for js_file in js_files:
        for fn in js_file.functions:
            for ajax in fn.ajax_calls:
                ajax_norm = _normalize_url(ajax.url, context_path)
                # {var} も [^/]+ として照合
                ajax_pattern = _url_to_pattern(ajax_norm)

                for ctrl, cm, ctrl_norm, ctrl_pattern in all_methods:
                    # 双方向マッチ: AjaxCall側 or Controller側のパターンでどちらでも一致
                    if not (ctrl_pattern.fullmatch(ajax_norm) or ajax_pattern.fullmatch(ctrl_norm)):
                        continue
                    # HTTP メソッド照合 (ANY は全メソッドと一致)
                    if cm.http_method != HttpMethod.ANY:
                        if ajax.http_method.upper() != cm.http_method.value.upper():
                            continue
                    results.append((fn, ajax, ctrl, cm))
                    log.debug(
                        "Ajax→Ctrl: %s [%s] -> %s.%s",
                        ajax.url, ajax.http_method, ctrl.class_name, cm.name,
                    )
                    break

    return results


def link_hrefs_to_controllers(
    js_files: List[JsFileInfo],
    controllers: List[ControllerInfo],
    context_path: str = "",
) -> List[Tuple[JsFunctionInfo, str, any, ControllerInfo, ControllerMethodInfo]]:
    """
    window.location.href = url を ControllerMethod.url に照合する。
    Returns: [(js_function, href_url, condition, ctrl, ctrl_method), ...]
    """
    all_methods: List[Tuple[ControllerInfo, ControllerMethodInfo, str, re.Pattern]] = []
    for ctrl in controllers:
        for cm in ctrl.methods:
            norm = _normalize_url(cm.url, context_path)
            all_methods.append((ctrl, cm, norm, _url_to_pattern(norm)))

    results = []
    for js_file in js_files:
        for fn in js_file.functions:
            for href, condition in fn.location_hrefs:
                href_norm = _normalize_url(href, context_path)
                href_pattern = _url_to_pattern(href_norm)

                for ctrl, cm, ctrl_norm, ctrl_pattern in all_methods:
                    if not (ctrl_pattern.fullmatch(href_norm) or href_pattern.fullmatch(ctrl_norm)):
                        continue
                    results.append((fn, href, condition, ctrl, cm))
                    log.debug("Href→Ctrl: %s [%s] -> %s.%s", href, condition, ctrl.class_name, cm.name)
                    break

    return results
