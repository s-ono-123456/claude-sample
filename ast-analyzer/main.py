#!/usr/bin/env python3
"""
AST解析ツール Phase 1 + 2 + 3
  Phase 1: Java (Controller / Service / DAO) + MyBatis XML → Neo4j
  Phase 2: JSP (Screen / Button) + URL照合 + View照合 → Neo4j
  Phase 3: JS (JsFunction / AjaxCall) + リンク解決 → Neo4j
"""
import argparse
import logging
from pathlib import Path
from typing import List

import yaml

from parsers.java_controller_parser import parse_controller
from parsers.java_service_parser import parse_service
from parsers.java_dao_parser import parse_dao
from parsers.mybatis_xml_parser import parse_mapper
from parsers.jsp_parser import parse_jsp
from parsers.js_parser import parse_js
from graph.neo4j_client import Neo4jClient
from linker.method_call_linker import link_all
from linker.url_linker import link_buttons_to_controllers
from linker.view_linker import link_views_to_screens
from linker.js_linker import (
    link_buttons_to_js_functions,
    link_js_function_calls,
    link_ajax_to_controllers,
    link_hrefs_to_controllers,
)
from model.ir import ControllerInfo, ButtonType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def load_config(path: str) -> dict:
    config_file = Path(path).resolve()
    base_dir = config_file.parent
    with open(config_file, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for key in ("source_root", "mapper_root", "jsp_root", "js_root"):
        if cfg.get(key):
            p = Path(cfg[key])
            if not p.is_absolute():
                cfg[key] = str(base_dir / p)
    return cfg


def scan_files(root: str, pattern: str) -> List[Path]:
    return list(Path(root).rglob(pattern))


# ──────────────────────────────────────────────────────────────────────
# Phase 1
# ──────────────────────────────────────────────────────────────────────
def run_phase1(cfg: dict):
    source_root = cfg["source_root"]
    mapper_root = cfg.get("mapper_root", source_root)

    log.info("=== Phase 1: Java解析 ===")
    java_files = scan_files(source_root, "*.java")
    log.info("Javaファイル: %d 件", len(java_files))

    controllers, services, daos = [], [], []
    for f in java_files:
        path = str(f)
        ctrl = parse_controller(path)
        if ctrl:
            controllers.append(ctrl)
            log.info("[Controller] %-40s  %d methods", ctrl.class_name, len(ctrl.methods))
            continue
        svc = parse_service(path)
        if svc:
            services.append(svc)
            log.info("[Service]    %-40s  %d methods", svc.class_name, len(svc.methods))
            continue
        dao = parse_dao(path)
        if dao:
            daos.append(dao)
            log.info("[Dao]        %-40s  %d methods", dao.class_name, len(dao.methods))

    xml_files = scan_files(mapper_root, "*.xml")
    log.info("XMLファイル: %d 件", len(xml_files))
    mappers = []
    for f in xml_files:
        m = parse_mapper(str(f))
        if m:
            mappers.append(m)
            log.info("[Mapper]     %-40s  %d statements", m.namespace.split(".")[-1], len(m.statements))

    return controllers, services, daos, mappers


# ──────────────────────────────────────────────────────────────────────
# Phase 2
# ──────────────────────────────────────────────────────────────────────
def run_phase2(cfg: dict, controllers: List[ControllerInfo]):
    jsp_root = cfg.get("jsp_root", "")
    if not jsp_root:
        log.info("jsp_root が未設定のため Phase 2 をスキップします")
        return [], [], [], []

    view_prefix = cfg.get("view_prefix", "/WEB-INF/views/")
    view_suffix = cfg.get("view_suffix", ".jsp")
    context_path = cfg.get("context_path", "")

    log.info("=== Phase 2: JSP解析 ===")
    jsp_files = scan_files(jsp_root, "*.jsp")
    log.info("JSPファイル: %d 件", len(jsp_files))

    screens = []
    for f in jsp_files:
        screen = parse_jsp(str(f), jsp_root, view_prefix, view_suffix)
        if screen:
            screens.append(screen)
            log.info("[Screen]     %-40s  %d buttons", screen.view_name, len(screen.buttons))

    # URL照合: Button.targetUrl → ControllerMethod.url
    btn_ctrl_pairs = link_buttons_to_controllers(screens, controllers, context_path)
    log.info("URL照合: Button→Controller %d 件", len(btn_ctrl_pairs))

    # View照合: ControllerMethod.return_view → Screen
    returns_view, redirects_to = link_views_to_screens(
        controllers, screens, view_prefix, view_suffix
    )
    log.info("View照合: RETURNS_VIEW %d 件 / REDIRECTS_TO %d 件", len(returns_view), len(redirects_to))

    return screens, btn_ctrl_pairs, returns_view, redirects_to


# ──────────────────────────────────────────────────────────────────────
# Phase 3
# ──────────────────────────────────────────────────────────────────────
def run_phase3(cfg: dict, screens: list, controllers: list):
    js_root = cfg.get("js_root") or cfg.get("jsp_root", "")
    if not js_root:
        log.info("js_root が未設定のため Phase 3 をスキップします")
        return [], [], [], [], []

    context_path = cfg.get("context_path", "")

    log.info("=== Phase 3: JS解析 ===")
    js_file_paths = scan_files(js_root, "*.js")
    log.info("JSファイル: %d 件", len(js_file_paths))

    js_files = []
    for f in js_file_paths:
        js_info = parse_js(str(f))
        if js_info:
            js_files.append(js_info)
            ajax_count = sum(len(fn.ajax_calls) for fn in js_info.functions)
            log.info(
                "[JsFile] %-40s %d fn / %d ajax",
                Path(f).name, len(js_info.functions), ajax_count,
            )

    btn_js_pairs = link_buttons_to_js_functions(screens, js_files)
    log.info("Button→JsFunction: %d 件", len(btn_js_pairs))

    js_js_pairs = link_js_function_calls(js_files)
    log.info("JsFunction→JsFunction (CALLS): %d 件", len(js_js_pairs))

    ajax_ctrl_pairs = link_ajax_to_controllers(js_files, controllers, context_path)
    log.info("AjaxCall→ControllerMethod: %d 件", len(ajax_ctrl_pairs))

    href_ctrl_pairs = link_hrefs_to_controllers(js_files, controllers, context_path)
    log.info("LocationHref→ControllerMethod: %d 件", len(href_ctrl_pairs))

    return js_files, btn_js_pairs, js_js_pairs, ajax_ctrl_pairs, href_ctrl_pairs


# ──────────────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────────────
def main(config_path: str, dry_run: bool, phase: int):
    cfg = load_config(config_path)

    controllers, services, daos, mappers = run_phase1(cfg)

    screens, btn_ctrl_pairs, returns_view, redirects_to = [], [], [], []
    if phase >= 2:
        screens, btn_ctrl_pairs, returns_view, redirects_to = run_phase2(cfg, controllers)

    js_files, btn_js_pairs, js_js_pairs, ajax_ctrl_pairs, href_ctrl_pairs = [], [], [], [], []
    if phase >= 3:
        js_files, btn_js_pairs, js_js_pairs, ajax_ctrl_pairs, href_ctrl_pairs = \
            run_phase3(cfg, screens, controllers)

    log.info("")
    log.info("=== 解析結果サマリー ===")
    log.info("  Controller : %d", len(controllers))
    log.info("  Service    : %d", len(services))
    log.info("  DAO        : %d", len(daos))
    log.info("  Mapper     : %d", len(mappers))
    if phase >= 2:
        log.info("  Screen     : %d", len(screens))
        log.info("  URL照合    : %d", len(btn_ctrl_pairs))
        log.info("  View照合   : %d", len(returns_view) + len(redirects_to))
    if phase >= 3:
        log.info("  JsFile     : %d", len(js_files))
        log.info("  Btn→JS     : %d", len(btn_js_pairs))
        log.info("  JS→JS      : %d", len(js_js_pairs))
        log.info("  Ajax→Ctrl  : %d", len(ajax_ctrl_pairs))
        log.info("  Href→Ctrl  : %d", len(href_ctrl_pairs))

    if dry_run:
        log.info("--dry-run モード: Neo4jへの書き込みをスキップします")
        return

    neo4j_cfg = cfg["neo4j"]
    log.info("")
    log.info("=== Neo4jに接続中: %s ===", neo4j_cfg["uri"])

    with Neo4jClient(
        uri=neo4j_cfg["uri"],
        user=neo4j_cfg["user"],
        password=neo4j_cfg["password"],
    ) as neo4j:
        neo4j.create_constraints()

        # ── Phase 1: ノード & エッジ ──
        log.info("Phase 1: ノードを保存中...")
        for c in controllers:
            neo4j.save_controller(c)
        for s in services:
            neo4j.save_service(s)
        for d in daos:
            neo4j.save_dao(d)
        for m in mappers:
            neo4j.save_mapper(m)

        log.info("Phase 1: エッジを生成中 (Controller→Service→DAO)...")
        link_all(controllers, services, daos, neo4j)

        if phase < 2:
            log.info("=== 完了 ===")
            return

        # ── Phase 2: ノード & エッジ ──
        log.info("Phase 2: Screen/Buttonノードを保存中...")
        for screen in screens:
            neo4j.save_screen(screen)

        log.info("Phase 2: URLエッジを生成中 (Button→ControllerMethod)...")
        for btn, screen, cm, ctrl_class in btn_ctrl_pairs:
            if btn.button_type == ButtonType.SUBMIT:
                neo4j.link_button_submits_to(btn, ctrl_class, cm)
            else:
                neo4j.link_button_navigates_to(btn, ctrl_class, cm)

        log.info("Phase 2: Viewエッジを生成中 (ControllerMethod→Screen)...")
        for ctrl_class, cm, screen in returns_view:
            neo4j.link_controller_returns_view(ctrl_class, cm, screen)
        for ctrl_class, cm, screen in redirects_to:
            neo4j.link_controller_redirects_to(ctrl_class, cm, screen)

        # TRANSITIONS_TO: Screen→Controller→Screen の連鎖を直接エッジとして追加
        log.info("Phase 2: TRANSITIONS_TOエッジを生成中...")
        _build_screen_transitions(neo4j, btn_ctrl_pairs, returns_view, redirects_to)

        if phase < 3:
            log.info("=== 完了 ===")
            return

        # ── Phase 3: ノード & エッジ ──
        log.info("Phase 3: JsFile/JsFunction/AjaxCallノードを保存中...")
        for js_file in js_files:
            neo4j.save_js_file(js_file)

        log.info("Phase 3: Button→JsFunctionエッジを生成中 (TRIGGERS_JS)...")
        for btn, screen, fn in btn_js_pairs:
            neo4j.link_button_triggers_js(btn.uid, fn.file_path, fn.name)

        log.info("Phase 3: JsFunction→JsFunctionエッジを生成中 (CALLS)...")
        for caller_fn, callee_fn in js_js_pairs:
            neo4j.link_js_calls_js(
                caller_fn.file_path, caller_fn.name,
                callee_fn.file_path, callee_fn.name,
            )

        log.info("Phase 3: AjaxCall→ControllerMethodエッジを生成中 (AJAX_CALLS)...")
        for fn, ajax, ctrl, cm in ajax_ctrl_pairs:
            neo4j.link_ajax_to_controller(
                fn.file_path, fn.name,
                ajax.url, ajax.http_method,
                ctrl.class_name, cm,
            )

        log.info("Phase 3: LocationHref→ControllerMethodエッジを生成中 (NAVIGATES_TO)...")
        for fn, href, ctrl, cm in href_ctrl_pairs:
            neo4j.link_js_navigates_to(fn.file_path, fn.name, ctrl.class_name, cm)

    log.info("=== 完了 ===")


def _build_screen_transitions(neo4j, btn_ctrl_pairs, returns_view, redirects_to):
    """
    Button→ControllerMethod→Screen のパスから Screen→Screen の TRANSITIONS_TO エッジを生成する。
    これにより画面遷移フローをグラフで直接辿れるようにする。
    """
    # ControllerMethod.id → 遷移先 Screen のマップを構築
    from graph.neo4j_client import _cm_id
    cm_to_screen: dict = {}
    for ctrl_class, cm, screen in returns_view:
        cm_to_screen[_cm_id(ctrl_class, cm.name, cm.url)] = screen
    for ctrl_class, cm, screen in redirects_to:
        cm_to_screen[_cm_id(ctrl_class, cm.name, cm.url)] = screen

    # 各 Button が属する Screen → 遷移先 Screen
    for btn, from_screen, cm, ctrl_class in btn_ctrl_pairs:
        mid = _cm_id(ctrl_class, cm.name, cm.url)
        to_screen = cm_to_screen.get(mid)
        if to_screen and from_screen.path != to_screen.path:
            neo4j.link_screen_transitions(
                from_screen.path,
                to_screen.path,
                trigger=btn.label,
            )


def cmd_summary(config_path: str):
    """Neo4j 上のグラフ統計と未解決 AjaxCall を表示する。"""
    cfg = load_config(config_path)
    neo4j_cfg = cfg["neo4j"]
    with Neo4jClient(
        uri=neo4j_cfg["uri"],
        user=neo4j_cfg["user"],
        password=neo4j_cfg["password"],
    ) as neo4j:
        log.info("=== グラフ統計 ===")
        for key, cnt in sorted(neo4j.summary().items()):
            log.info("  %-35s %d", key, cnt)

        unresolved = neo4j.unresolved_ajax_calls()
        if unresolved:
            log.info("")
            log.info("=== 未解決 AjaxCall (%d 件) ===", len(unresolved))
            for item in unresolved:
                log.info("  [%s] %s", item["method"], item["url"])
        else:
            log.info("未解決 AjaxCall: なし")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AST解析ツール")
    parser.add_argument("--config", default="config.yaml", help="設定ファイルパス")
    parser.add_argument("--dry-run", action="store_true", help="解析のみ (Neo4j書き込みなし)")
    parser.add_argument(
        "--phase", type=int, default=3, choices=[1, 2, 3],
        help="実行フェーズ: 1=Java/MyBatisのみ, 2=JSP含む, 3=JS含む (デフォルト: 3)"
    )
    parser.add_argument("--summary", action="store_true", help="Neo4jグラフ統計を表示して終了")
    args = parser.parse_args()

    if args.summary:
        cmd_summary(args.config)
    else:
        main(args.config, args.dry_run, args.phase)
