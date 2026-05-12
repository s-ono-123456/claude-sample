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
    List[Tuple[str, ControllerMethodInfo, ScreenInfo, any]],   # RETURNS_VIEW (condition追加)
    List[Tuple[str, ControllerMethodInfo, ScreenInfo, any]],   # REDIRECTS_TO (condition追加)
]:
    """
    Controller メソッドの return 値を Screen に照合する。
    conditional_returns を優先して使用し、条件情報を保持する。
    Returns:
        returns_view: [(ctrl_class, cm, screen, condition), ...]
        redirects_to: [(ctrl_class, cm, screen, condition), ...]
    """
    screen_by_view: dict[str, ScreenInfo] = {s.view_name: s for s in screens}
    screen_by_path: dict[str, ScreenInfo] = {s.path: s for s in screens}

    returns_view: list = []
    redirects_to: list = []

    for ctrl in controllers:
        for cm in ctrl.methods:
            if cm.conditional_returns:
                # conditional_returns を使い条件情報を保持
                for cr in cm.conditional_returns:
                    if cr.value.startswith("redirect:"):
                        target = cr.value[len("redirect:"):].rstrip("/") or "/"
                        screen = screen_by_path.get(target)
                        if not screen:
                            norm = _normalize_view_name(target, view_prefix, view_suffix)
                            screen = screen_by_view.get(norm)
                        if screen:
                            redirects_to.append((ctrl.class_name, cm, screen, cr.condition))
                            log.debug("REDIRECTS_TO: %s.%s -> %s [%s]", ctrl.class_name, cm.name, target, cr.condition)
                    else:
                        norm = _normalize_view_name(cr.value, view_prefix, view_suffix)
                        screen = screen_by_view.get(norm)
                        if screen:
                            returns_view.append((ctrl.class_name, cm, screen, cr.condition))
                            log.debug("RETURNS_VIEW: %s.%s -> %s [%s]", ctrl.class_name, cm.name, norm, cr.condition)
                        else:
                            log.debug("view未解決: %s.%s -> %s", ctrl.class_name, cm.name, cr.value)
            else:
                # フォールバック: 従来の return_view / redirect_to
                if cm.return_view:
                    norm = _normalize_view_name(cm.return_view, view_prefix, view_suffix)
                    screen = screen_by_view.get(norm)
                    if screen:
                        returns_view.append((ctrl.class_name, cm, screen, None))
                        log.debug("RETURNS_VIEW: %s.%s -> %s", ctrl.class_name, cm.name, norm)
                    else:
                        log.debug("view未解決: %s.%s -> %s", ctrl.class_name, cm.name, cm.return_view)
                if cm.redirect_to:
                    target = cm.redirect_to.rstrip("/") or "/"
                    screen = screen_by_path.get(target)
                    if not screen:
                        norm = _normalize_view_name(target, view_prefix, view_suffix)
                        screen = screen_by_view.get(norm)
                    if screen:
                        redirects_to.append((ctrl.class_name, cm, screen, None))
                        log.debug("REDIRECTS_TO: %s.%s -> %s", ctrl.class_name, cm.name, target)

    return returns_view, redirects_to
