"""
Controller の return "viewName" / return "redirect:/path" を Screen に照合する。

ViewResolver の prefix/suffix を考慮して view 名を正規化し、
ScreenInfo.view_name と比較する。
"""
import logging
from typing import List, Tuple

from model.ir import ScreenInfo, ControllerInfo, ControllerMethodInfo

log = logging.getLogger(__name__)


def _normalize_view_name(raw: str, view_prefix: str, view_suffix: str) -> str:
    """
    Controller が返す view 名を ScreenInfo.view_name の形式に正規化する。
    例: "WEB-INF/views/search" → "search"  (prefix=WEB-INF/views/)
    """
    name = raw.strip()
    prefix_clean = view_prefix.strip("/")
    if prefix_clean and name.startswith(prefix_clean):
        name = name[len(prefix_clean):].lstrip("/")
    suffix_clean = view_suffix.lstrip(".")
    if name.endswith("." + suffix_clean):
        name = name[: -(len(suffix_clean) + 1)]
    return name.lstrip("/")


def link_views_to_screens(
    controllers: List[ControllerInfo],
    screens: List[ScreenInfo],
    view_prefix: str = "/WEB-INF/views/",
    view_suffix: str = ".jsp",
) -> Tuple[
    List[Tuple[str, ControllerMethodInfo, ScreenInfo]],   # RETURNS_VIEW
    List[Tuple[str, ControllerMethodInfo, ScreenInfo]],   # REDIRECTS_TO
]:
    """
    Controller メソッドの return 値を Screen に照合する。
    Returns:
        returns_view: [(ctrl_class, cm, screen), ...]   return "viewName"
        redirects_to: [(ctrl_class, cm, screen), ...]   return "redirect:/path"
    """
    # view_name → ScreenInfo のマップ (正規化済み)
    screen_by_view: dict[str, ScreenInfo] = {s.view_name: s for s in screens}
    # path → ScreenInfo のマップ (サーバーリダイレクト用)
    screen_by_path: dict[str, ScreenInfo] = {s.path: s for s in screens}

    returns_view: List[Tuple[str, ControllerMethodInfo, ScreenInfo]] = []
    redirects_to: List[Tuple[str, ControllerMethodInfo, ScreenInfo]] = []

    for ctrl in controllers:
        for cm in ctrl.methods:
            # ── RETURNS_VIEW ──
            if cm.return_view:
                norm = _normalize_view_name(cm.return_view, view_prefix, view_suffix)
                screen = screen_by_view.get(norm)
                if screen:
                    returns_view.append((ctrl.class_name, cm, screen))
                    log.debug("RETURNS_VIEW: %s.%s -> %s", ctrl.class_name, cm.name, norm)
                else:
                    log.debug("view未解決: %s.%s -> %s", ctrl.class_name, cm.name, norm)

            # ── REDIRECTS_TO ──
            if cm.redirect_to:
                # redirect 先が他の ControllerMethod の URL と一致する場合は
                # 対応する Screen を間接的に探す
                target = cm.redirect_to.rstrip("/") or "/"
                # まず path 直接一致を試みる
                screen = screen_by_path.get(target)
                if not screen:
                    # view_name として照合
                    norm = _normalize_view_name(target, view_prefix, view_suffix)
                    screen = screen_by_view.get(norm)
                if screen:
                    redirects_to.append((ctrl.class_name, cm, screen))
                    log.debug("REDIRECTS_TO: %s.%s -> %s", ctrl.class_name, cm.name, target)

    return returns_view, redirects_to
