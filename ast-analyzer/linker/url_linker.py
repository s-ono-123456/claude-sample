"""
Button の targetUrl を ControllerMethod の URL に照合する。

Spring MVC のパスパラメータ {id} を正規表現に変換して部分一致ではなく完全一致で照合する。
コンテキストパスは設定値で除去する。
"""
import re
import logging
from typing import List, Tuple

from model.ir import ScreenInfo, ButtonInfo, ButtonType, ControllerInfo, ControllerMethodInfo

log = logging.getLogger(__name__)


def _normalize(url: str, context_path: str) -> str:
    """クエリパラメータ・フラグメント・コンテキストパスを除去して正規化する"""
    url = url.split("?")[0].split("#")[0]
    if context_path and url.startswith(context_path):
        url = url[len(context_path):]
    return url.rstrip("/") or "/"


def _make_pattern(url: str) -> re.Pattern:
    """Spring MVC の {pathVar} を [^/]+ に変換した正規表現を返す"""
    escaped = re.escape(url)
    escaped = re.sub(r"\\{[^}]+\\}", "[^/]+", escaped)
    return re.compile(f"^{escaped}$")


def link_buttons_to_controllers(
    screens: List[ScreenInfo],
    controllers: List[ControllerInfo],
    context_path: str = "",
) -> List[Tuple[ButtonInfo, ScreenInfo, ControllerMethodInfo, str]]:
    """
    各 Screen の Button の targetUrl を ControllerMethod に照合する。
    Returns: [(button, screen, controller_method, ctrl_class_name), ...]
    """
    # Controller 側を (ctrl_class, cm, normalized_url, pattern) に展開
    all_methods: List[Tuple[str, ControllerMethodInfo, str, re.Pattern]] = []
    for ctrl in controllers:
        for cm in ctrl.methods:
            norm = _normalize(cm.url, context_path)
            all_methods.append((ctrl.class_name, cm, norm, _make_pattern(norm)))

    results = []
    for screen in screens:
        for btn in screen.buttons:
            if not btn.target_url:
                continue
            btn_norm = _normalize(btn.target_url, context_path)
            btn_pattern = _make_pattern(btn_norm)

            for ctrl_class, cm, ctrl_norm, pattern in all_methods:
                # 双方向マッチ: Controllerパターン←ボタンURL / ボタンパターン←Controller URL
                if not (pattern.fullmatch(btn_norm) or btn_pattern.fullmatch(ctrl_norm)):
                    continue
                # HTTP メソッド照合 (ANY は全メソッドと一致)
                from model.ir import HttpMethod
                if cm.http_method not in (HttpMethod.ANY,):
                    expected_http = cm.http_method.value
                    actual_http = btn.http_method.upper()
                    if actual_http != expected_http:
                        continue
                results.append((btn, screen, cm, ctrl_class))
                log.debug(
                    "URL match: %s [%s] -> %s.%s",
                    btn_norm, btn.http_method, ctrl_class, cm.name,
                )
                break  # 最初に一致した Controller に紐付け

    return results
