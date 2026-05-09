import re
import logging
from pathlib import Path
from typing import Optional, List, Tuple

from bs4 import BeautifulSoup

from model.ir import ScreenInfo, ButtonInfo, ButtonType

log = logging.getLogger(__name__)

_EXTERNAL_SCHEMES = ("http://", "https://", "//", "mailto:", "tel:", "ftp://")


def _preprocess_jsp(source: str) -> Tuple[str, List[str]]:
    """
    JSP固有構文をBeautifulSoupで解析できるHTMLに変換する。
    スクリプトレットは別途返し、後でsendRedirect等を抽出するために保持する。
    """
    scriptlets: List[str] = re.findall(r"<%(?![@=\-])(.*?)%>", source, re.DOTALL)

    html = source
    html = re.sub(r"<%--.*?--%>", "", html, flags=re.DOTALL)   # JSPコメント
    html = re.sub(r"<%@[^%]*%>", "", html)                      # ディレクティブ
    html = re.sub(r"<%=.*?%>", '""', html, flags=re.DOTALL)     # 式
    html = re.sub(r"<%.*?%>", "", html, flags=re.DOTALL)        # スクリプトレット

    # contextPath系EL式は除去 (ベースパスなのでURL照合に不要)
    html = re.sub(
        r"\$\{(?:pageContext\.request\.contextPath|contextPath|ctx|basePath|rootPath)\}",
        "",
        html,
    )
    # その他のEL式は {var} に変換 (パスパラメータとして照合できるように)
    html = re.sub(r"\$\{[^}]+\}", "{var}", html)

    # Spring form タグを標準 HTML form に変換
    html = re.sub(r"<form:form\b", "<form", html, flags=re.IGNORECASE)
    html = re.sub(r"</form:form\s*>", "</form>", html, flags=re.IGNORECASE)
    html = re.sub(r"<form:input\b", "<input", html, flags=re.IGNORECASE)
    html = re.sub(r"<form:button\b", "<button", html, flags=re.IGNORECASE)
    html = re.sub(r"<form:select\b", "<select", html, flags=re.IGNORECASE)

    return html, scriptlets


def _is_external(url: str) -> bool:
    return any(url.startswith(s) for s in _EXTERNAL_SCHEMES)


def _onclick_fn(onclick: str) -> Optional[str]:
    """onclick="fnName(args)" から関数名のみ取り出す"""
    m = re.match(r"\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(", onclick.strip())
    return m.group(1) if m else None


def _compute_view_name(file_path: str, jsp_root: str, view_prefix: str, view_suffix: str) -> str:
    """
    JSPファイルパスから ViewResolver が解決する view 名を計算する。
    例: /webapp/WEB-INF/views/user/search.jsp
        → jsp_root=/webapp, view_prefix=/WEB-INF/views/, view_suffix=.jsp
        → "user/search"
    """
    try:
        rel = Path(file_path).relative_to(jsp_root).with_suffix("").as_posix()
    except ValueError:
        return Path(file_path).stem

    prefix_clean = view_prefix.strip("/")
    if prefix_clean and rel.startswith(prefix_clean):
        rel = rel[len(prefix_clean):].lstrip("/")

    return rel


def parse_jsp(
    file_path: str,
    jsp_root: str,
    view_prefix: str = "/WEB-INF/views/",
    view_suffix: str = ".jsp",
) -> Optional[ScreenInfo]:
    """JSPファイルを解析して ScreenInfo を返す"""
    source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    html, scriptlets = _preprocess_jsp(source)
    soup = BeautifulSoup(html, "html.parser")

    view_name = _compute_view_name(file_path, jsp_root, view_prefix, view_suffix)

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else Path(file_path).stem

    buttons: List[ButtonInfo] = []
    btn_idx = 0
    processed_elem_ids = set()  # Python の id() で重複処理を防ぐ

    # ── フォーム内 submit ボタン ──────────────────────────────────────
    for form in soup.find_all("form"):
        action = (form.get("action") or "").strip()
        method = (form.get("method") or "GET").upper()

        for elem in form.find_all(["input", "button"]):
            eid = id(elem)
            if eid in processed_elem_ids:
                continue
            processed_elem_ids.add(eid)

            btn_type_attr = (elem.get("type") or "submit").lower()
            if btn_type_attr not in ("submit", "button", "image"):
                continue

            label = (
                elem.get("value")
                or elem.get_text(strip=True)
                or elem.get("name")
                or f"button{btn_idx}"
            )
            onclick = elem.get("onclick") or ""

            if btn_type_attr == "submit":
                buttons.append(ButtonInfo(
                    uid=f"{file_path}#btn{btn_idx}",
                    label=label,
                    button_type=ButtonType.SUBMIT,
                    target_url=action or None,
                    http_method=method,
                    onclick_fn=_onclick_fn(onclick) if onclick else None,
                ))
            else:
                fn = _onclick_fn(onclick)
                if fn:
                    buttons.append(ButtonInfo(
                        uid=f"{file_path}#btn{btn_idx}",
                        label=label,
                        button_type=ButtonType.JS_BUTTON,
                        onclick_fn=fn,
                    ))
                else:
                    continue  # onclick なしの type=button は対象外

            btn_idx += 1

    # ── <a href> リンク ──────────────────────────────────────────────
    for a_tag in soup.find_all("a"):
        href = (a_tag.get("href") or "").strip()
        if not href or href.startswith("#") or href.startswith("javascript:") or _is_external(href):
            continue
        raw_label = a_tag.get_text(strip=True)
        # EL式のみのラベルは href をフォールバックとして使う
        label = (raw_label if raw_label and raw_label != "{var}" else None) or href
        buttons.append(ButtonInfo(
            uid=f"{file_path}#btn{btn_idx}",
            label=label,
            button_type=ButtonType.LINK,
            target_url=href,
            http_method="GET",
        ))
        btn_idx += 1

    # ── フォーム外の onclick ボタン ───────────────────────────────────
    for elem in soup.find_all(["button", "input"]):
        eid = id(elem)
        if eid in processed_elem_ids:
            continue
        processed_elem_ids.add(eid)

        onclick = elem.get("onclick") or ""
        fn = _onclick_fn(onclick)
        if not fn:
            continue

        label = (
            elem.get("value")
            or elem.get_text(strip=True)
            or f"button{btn_idx}"
        )
        buttons.append(ButtonInfo(
            uid=f"{file_path}#btn{btn_idx}",
            label=label,
            button_type=ButtonType.JS_BUTTON,
            onclick_fn=fn,
        ))
        btn_idx += 1

    # ── サーバーサイド遷移 (sendRedirect / jsp:forward) ───────────────
    server_redirects: List[str] = []

    for fwd in soup.find_all(re.compile(r"^jsp:forward$", re.IGNORECASE)):
        page = fwd.get("page", "")
        if page:
            server_redirects.append(page)

    for scriptlet in scriptlets:
        for m in re.finditer(r'response\.sendRedirect\s*\(\s*"([^"]+)"', scriptlet):
            server_redirects.append(m.group(1))
        for m in re.finditer(r'getRequestDispatcher\s*\(\s*"([^"]+)"', scriptlet):
            server_redirects.append(m.group(1))

    log.debug("[JSP] %s: %d buttons, %d redirects", view_name, len(buttons), len(server_redirects))

    return ScreenInfo(
        path=file_path,
        view_name=view_name,
        title=title,
        buttons=buttons,
        server_redirects=server_redirects,
    )
