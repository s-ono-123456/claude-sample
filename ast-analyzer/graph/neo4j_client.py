import logging
from typing import List

from neo4j import GraphDatabase

from model.ir import (
    ControllerInfo, ControllerMethodInfo,
    ServiceInfo, DaoInfo, MapperInfo, SqlType,
    ScreenInfo, ButtonInfo, ButtonType,
    JsFileInfo, JsFunctionInfo, AjaxCallInfo,
)

log = logging.getLogger(__name__)


def _cm_id(class_name: str, method_name: str, url: str) -> str:
    return f"{class_name}#{method_name}#{url}"


def _sm_id(class_name: str, method_name: str) -> str:
    return f"{class_name}#{method_name}"


def _dm_id(class_name: str, method_name: str) -> str:
    return f"{class_name}#{method_name}"


def _sql_id(namespace: str, sql_id: str) -> str:
    return f"{namespace}#{sql_id}"


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _run(self, query: str, **params):
        with self.driver.session() as session:
            return session.run(query, **params)

    def _run_unwind(self, query: str, items: list, **params):
        if not items:
            return
        with self.driver.session() as session:
            return session.run(query, items=items, **params)

    # ------------------------------------------------------------------
    # スキーマ初期化
    # ------------------------------------------------------------------
    def clear_all(self):
        """全ノード・リレーションシップを削除する。"""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        log.info("全データを削除しました")

    def create_constraints(self):
        stmts = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Screen)           REQUIRE n.path IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Button)           REQUIRE n.uid IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Controller)       REQUIRE n.className IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:ControllerMethod) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Service)          REQUIRE n.className IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:ServiceMethod)    REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Dao)              REQUIRE n.className IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:DaoMethod)        REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:SqlStatement)     REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Table)            REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:JsFile)           REQUIRE n.path IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:JsFunction)       REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:AjaxCall)         REQUIRE n.id IS UNIQUE",
        ]
        for s in stmts:
            self._run(s)
        log.info("制約を作成しました")

    # ------------------------------------------------------------------
    # ノード保存 (Phase 1)
    # ------------------------------------------------------------------
    def save_controllers(self, ctrls: List[ControllerInfo]):
        if not ctrls:
            return
        ctrl_items = [
            {"className": c.class_name, "filePath": c.file_path, "baseUrl": c.base_url}
            for c in ctrls
        ]
        method_items = [
            {
                "id": _cm_id(c.class_name, m.name, m.url),
                "name": m.name,
                "url": m.url,
                "httpMethod": m.http_method.value,
                "returnView": m.return_view,
                "redirectTo": m.redirect_to,
                "className": c.class_name,
            }
            for c in ctrls
            for m in c.methods
        ]
        self._run_unwind(
            "UNWIND $items AS c "
            "MERGE (ctrl:Controller {className: c.className}) "
            "SET ctrl.filePath = c.filePath, ctrl.baseUrl = c.baseUrl",
            ctrl_items,
        )
        if method_items:
            self._run_unwind(
                "UNWIND $items AS m "
                "MERGE (cm:ControllerMethod {id: m.id}) "
                "SET cm.name = m.name, cm.url = m.url, cm.httpMethod = m.httpMethod, "
                "    cm.returnView = m.returnView, cm.redirectTo = m.redirectTo, cm.className = m.className",
                method_items,
            )
            self._run_unwind(
                "UNWIND $items AS m "
                "MATCH (ctrl:Controller {className: m.className}) "
                "MATCH (cm:ControllerMethod {id: m.id}) "
                "MERGE (ctrl)-[:HAS_METHOD]->(cm)",
                method_items,
            )

    def save_services(self, svcs: List[ServiceInfo]):
        if not svcs:
            return
        svc_items = [
            {"className": s.class_name, "filePath": s.file_path}
            for s in svcs
        ]
        method_items = [
            {
                "id": _sm_id(s.class_name, m.name),
                "name": m.name,
                "signature": m.signature,
                "className": s.class_name,
            }
            for s in svcs
            for m in s.methods
        ]
        self._run_unwind(
            "UNWIND $items AS s "
            "MERGE (svc:Service {className: s.className}) "
            "SET svc.filePath = s.filePath",
            svc_items,
        )
        if method_items:
            self._run_unwind(
                "UNWIND $items AS m "
                "MERGE (sm:ServiceMethod {id: m.id}) "
                "SET sm.name = m.name, sm.signature = m.signature, sm.className = m.className",
                method_items,
            )
            self._run_unwind(
                "UNWIND $items AS m "
                "MATCH (svc:Service {className: m.className}) "
                "MATCH (sm:ServiceMethod {id: m.id}) "
                "MERGE (svc)-[:HAS_METHOD]->(sm)",
                method_items,
            )

    def save_daos(self, daos: List[DaoInfo]):
        if not daos:
            return
        dao_items = [
            {"className": d.class_name, "filePath": d.file_path, "fqn": d.fqn}
            for d in daos
        ]
        method_items = [
            {
                "id": _dm_id(d.class_name, m.name),
                "name": m.name,
                "signature": m.signature,
                "className": d.class_name,
            }
            for d in daos
            for m in d.methods
        ]
        self._run_unwind(
            "UNWIND $items AS d "
            "MERGE (dao:Dao {className: d.className}) "
            "SET dao.filePath = d.filePath, dao.fqn = d.fqn",
            dao_items,
        )
        if method_items:
            self._run_unwind(
                "UNWIND $items AS m "
                "MERGE (dm:DaoMethod {id: m.id}) "
                "SET dm.name = m.name, dm.signature = m.signature, dm.className = m.className",
                method_items,
            )
            self._run_unwind(
                "UNWIND $items AS m "
                "MATCH (dao:Dao {className: m.className}) "
                "MATCH (dm:DaoMethod {id: m.id}) "
                "MERGE (dao)-[:HAS_METHOD]->(dm)",
                method_items,
            )

    def save_mappers(self, mappers: List[MapperInfo]):
        if not mappers:
            return
        stmt_items = []
        reads = []
        writes = []
        all_tables = set()

        for mapper in mappers:
            simple_name = mapper.namespace.split(".")[-1]
            for stmt in mapper.statements:
                sid = _sql_id(mapper.namespace, stmt.sql_id)
                stmt_items.append({
                    "id": sid,
                    "sqlId": stmt.sql_id,
                    "sqlType": stmt.sql_type.value,
                    "rawSql": stmt.raw_sql,
                    "namespace": mapper.namespace,
                    "dmId": _dm_id(simple_name, stmt.sql_id),
                })
                for table in stmt.tables:
                    all_tables.add(table)
                    entry = {"sqlId": sid, "table": table}
                    if stmt.sql_type == SqlType.SELECT:
                        reads.append(entry)
                    else:
                        writes.append(entry)

        self._run_unwind(
            "UNWIND $items AS s "
            "MERGE (sql:SqlStatement {id: s.id}) "
            "SET sql.sqlId = s.sqlId, sql.sqlType = s.sqlType, "
            "    sql.rawSql = s.rawSql, sql.namespace = s.namespace",
            stmt_items,
        )
        self._run_unwind(
            "UNWIND $items AS s "
            "MATCH (dm:DaoMethod {id: s.dmId}) "
            "MATCH (sql:SqlStatement {id: s.id}) "
            "MERGE (dm)-[:EXECUTES]->(sql)",
            stmt_items,
        )
        table_items = [{"name": t} for t in all_tables]
        self._run_unwind(
            "UNWIND $items AS t MERGE (tbl:Table {name: t.name})",
            table_items,
        )
        self._run_unwind(
            "UNWIND $items AS r "
            "MATCH (sql:SqlStatement {id: r.sqlId}) "
            "MATCH (t:Table {name: r.table}) "
            "MERGE (sql)-[:READS]->(t)",
            reads,
        )
        self._run_unwind(
            "UNWIND $items AS w "
            "MATCH (sql:SqlStatement {id: w.sqlId}) "
            "MATCH (t:Table {name: w.table}) "
            "MERGE (sql)-[:WRITES]->(t)",
            writes,
        )

    # ------------------------------------------------------------------
    # ノード保存 (Phase 2: Screen / Button)
    # ------------------------------------------------------------------
    def save_screens(self, screens: List[ScreenInfo]):
        if not screens:
            return
        screen_items = [
            {"path": s.path, "viewName": s.view_name, "title": s.title}
            for s in screens
        ]
        button_items = [
            {
                "uid": btn.uid,
                "label": btn.label,
                "buttonType": btn.button_type.value,
                "targetUrl": btn.target_url,
                "httpMethod": btn.http_method,
                "onclickFn": btn.onclick_fn,
                "screenPath": s.path,
            }
            for s in screens
            for btn in s.buttons
        ]
        self._run_unwind(
            "UNWIND $items AS s "
            "MERGE (sc:Screen {path: s.path}) "
            "SET sc.viewName = s.viewName, sc.title = s.title",
            screen_items,
        )
        if button_items:
            self._run_unwind(
                "UNWIND $items AS b "
                "MERGE (btn:Button {uid: b.uid}) "
                "SET btn.label = b.label, btn.buttonType = b.buttonType, "
                "    btn.targetUrl = b.targetUrl, btn.httpMethod = b.httpMethod, btn.onclickFn = b.onclickFn",
                button_items,
            )
            self._run_unwind(
                "UNWIND $items AS b "
                "MATCH (sc:Screen {path: b.screenPath}) "
                "MATCH (btn:Button {uid: b.uid}) "
                "MERGE (sc)-[:CONTAINS]->(btn)",
                button_items,
            )

    # ------------------------------------------------------------------
    # エッジ生成 (Phase 2)
    # ------------------------------------------------------------------
    def link_buttons_submits_to(self, pairs: list):
        """[(btn, ctrl_class, cm), ...] → Button -[:SUBMITS_TO]-> ControllerMethod"""
        items = [
            {"uid": btn.uid, "cmId": _cm_id(ctrl_class, cm.name, cm.url)}
            for btn, ctrl_class, cm in pairs
        ]
        self._run_unwind(
            "UNWIND $items AS p "
            "MATCH (b:Button {uid: p.uid}) "
            "MATCH (cm:ControllerMethod {id: p.cmId}) "
            "MERGE (b)-[:SUBMITS_TO]->(cm)",
            items,
        )

    def link_buttons_navigates_to(self, pairs: list):
        """[(btn, ctrl_class, cm), ...] → Button -[:NAVIGATES_TO]-> ControllerMethod"""
        items = [
            {"uid": btn.uid, "cmId": _cm_id(ctrl_class, cm.name, cm.url)}
            for btn, ctrl_class, cm in pairs
        ]
        self._run_unwind(
            "UNWIND $items AS p "
            "MATCH (b:Button {uid: p.uid}) "
            "MATCH (cm:ControllerMethod {id: p.cmId}) "
            "MERGE (b)-[:NAVIGATES_TO]->(cm)",
            items,
        )

    def link_controllers_returns_view(self, pairs: list):
        """[(ctrl_class, cm, screen, condition), ...] → ControllerMethod -[:RETURNS_VIEW]-> Screen"""
        items = [
            {"cmId": _cm_id(ctrl_class, cm.name, cm.url), "path": screen.path}
            for ctrl_class, cm, screen, *_ in pairs
        ]
        self._run_unwind(
            "UNWIND $items AS p "
            "MATCH (cm:ControllerMethod {id: p.cmId}) "
            "MATCH (s:Screen {path: p.path}) "
            "MERGE (cm)-[:RETURNS_VIEW]->(s)",
            items,
        )

    def link_controllers_redirects_to(self, pairs: list):
        """[(ctrl_class, cm, screen, condition), ...] → ControllerMethod -[:REDIRECTS_TO]-> Screen"""
        items = [
            {"cmId": _cm_id(ctrl_class, cm.name, cm.url), "path": screen.path}
            for ctrl_class, cm, screen, *_ in pairs
        ]
        self._run_unwind(
            "UNWIND $items AS p "
            "MATCH (cm:ControllerMethod {id: p.cmId}) "
            "MATCH (s:Screen {path: p.path}) "
            "MERGE (cm)-[:REDIRECTS_TO]->(s)",
            items,
        )

    def link_screens_transitions(self, pairs: list):
        """[(from_path, to_path, trigger, condition), ...] → Screen -[:TRANSITIONS_TO]-> Screen"""
        to_paths = list({to_path for _, to_path, _, _ in pairs})
        self._run_unwind(
            "UNWIND $items AS p MERGE (s:Screen {path: p})",
            to_paths,
        )
        items = [
            {"fromPath": from_path, "toPath": to_path, "trigger": trigger, "condition": condition}
            for from_path, to_path, trigger, condition in pairs
        ]
        # condition は null の場合があるため MERGE キーに含めず SET で設定する
        self._run_unwind(
            "UNWIND $items AS p "
            "MATCH (s1:Screen {path: p.fromPath}) "
            "MATCH (s2:Screen {path: p.toPath}) "
            "MERGE (s1)-[r:TRANSITIONS_TO {trigger: p.trigger}]->(s2) "
            "SET r.condition = p.condition",
            items,
        )

    # ------------------------------------------------------------------
    # ノード保存 (Phase 3: JsFile / JsFunction / AjaxCall)
    # ------------------------------------------------------------------
    def save_js_files(self, js_files: List[JsFileInfo]):
        if not js_files:
            return
        file_items = [{"path": jf.path} for jf in js_files]
        fn_items = []
        ajax_items = []

        for jf in js_files:
            for fn in jf.functions:
                fn_id = f"{jf.path}#{fn.name}"
                fn_items.append({
                    "id": fn_id,
                    "name": fn.name,
                    "filePath": jf.path,
                    "line": fn.line,
                })
                for ajax in fn.ajax_calls:
                    ajax_id = f"{fn_id}#{ajax.url}#{ajax.http_method}"
                    ajax_items.append({
                        "id": ajax_id,
                        "url": ajax.url,
                        "method": ajax.http_method,
                        "unresolved": ajax.unresolved,
                        "fnId": fn_id,
                    })

        self._run_unwind(
            "UNWIND $items AS f MERGE (jf:JsFile {path: f.path})",
            file_items,
        )
        if fn_items:
            self._run_unwind(
                "UNWIND $items AS f "
                "MERGE (jf:JsFunction {id: f.id}) "
                "SET jf.name = f.name, jf.filePath = f.filePath, jf.line = f.line",
                fn_items,
            )
            self._run_unwind(
                "UNWIND $items AS f "
                "MATCH (file:JsFile {path: f.filePath}) "
                "MATCH (jf:JsFunction {id: f.id}) "
                "MERGE (file)-[:CONTAINS]->(jf)",
                fn_items,
            )
        if ajax_items:
            self._run_unwind(
                "UNWIND $items AS a "
                "MERGE (ac:AjaxCall {id: a.id}) "
                "SET ac.url = a.url, ac.method = a.method, ac.unresolved = a.unresolved",
                ajax_items,
            )
            self._run_unwind(
                "UNWIND $items AS a "
                "MATCH (jf:JsFunction {id: a.fnId}) "
                "MATCH (ac:AjaxCall {id: a.id}) "
                "MERGE (jf)-[:MAKES_AJAX]->(ac)",
                ajax_items,
            )

    # ------------------------------------------------------------------
    # エッジ生成 (Phase 1)
    # ------------------------------------------------------------------
    def link_controllers_to_services(self, pairs: list):
        """[(cmId, smId), ...] → ControllerMethod -[:CALLS]-> ServiceMethod"""
        self._run_unwind(
            "UNWIND $items AS p "
            "MATCH (cm:ControllerMethod {id: p.cmId}) "
            "MATCH (sm:ServiceMethod {id: p.smId}) "
            "MERGE (cm)-[:CALLS]->(sm)",
            pairs,
        )

    def link_services_to_daos(self, pairs: list):
        """[(smId, dmId), ...] → ServiceMethod -[:CALLS]-> DaoMethod"""
        self._run_unwind(
            "UNWIND $items AS p "
            "MATCH (sm:ServiceMethod {id: p.smId}) "
            "MATCH (dm:DaoMethod {id: p.dmId}) "
            "MERGE (sm)-[:CALLS]->(dm)",
            pairs,
        )

    # ------------------------------------------------------------------
    # エッジ生成 (Phase 3)
    # ------------------------------------------------------------------
    def link_buttons_triggers_js(self, pairs: list):
        """[(btn, screen, fn), ...] → Button -[:TRIGGERS_JS]-> JsFunction"""
        items = [
            {"uid": btn.uid, "fnId": f"{fn.file_path}#{fn.name}"}
            for btn, _screen, fn in pairs
        ]
        self._run_unwind(
            "UNWIND $items AS p "
            "MATCH (b:Button {uid: p.uid}) "
            "MATCH (jf:JsFunction {id: p.fnId}) "
            "MERGE (b)-[:TRIGGERS_JS]->(jf)",
            items,
        )

    def link_js_calls_js_batch(self, pairs: list):
        """[(caller_fn, callee_fn), ...] → JsFunction -[:CALLS]-> JsFunction"""
        items = [
            {
                "callerId": f"{caller.file_path}#{caller.name}",
                "calleeId": f"{callee.file_path}#{callee.name}",
            }
            for caller, callee in pairs
        ]
        self._run_unwind(
            "UNWIND $items AS p "
            "MATCH (caller:JsFunction {id: p.callerId}) "
            "MATCH (callee:JsFunction {id: p.calleeId}) "
            "MERGE (caller)-[:CALLS]->(callee)",
            items,
        )

    def link_ajax_to_controllers(self, pairs: list):
        """[(fn, ajax, ctrl, cm), ...] → AjaxCall -[:RESOLVES_TO]-> ControllerMethod + JsFunction -[:AJAX_CALLS]-> ControllerMethod"""
        resolves_items = []
        ajax_calls_items = []
        for fn, ajax, ctrl, cm in pairs:
            fn_id = f"{fn.file_path}#{fn.name}"
            ajax_id = f"{fn_id}#{ajax.url}#{ajax.http_method}"
            cm_id = _cm_id(ctrl.class_name, cm.name, cm.url)
            resolves_items.append({"ajaxId": ajax_id, "cmId": cm_id})
            ajax_calls_items.append({"fnId": fn_id, "cmId": cm_id})

        self._run_unwind(
            "UNWIND $items AS p "
            "MATCH (a:AjaxCall {id: p.ajaxId}) "
            "MATCH (cm:ControllerMethod {id: p.cmId}) "
            "MERGE (a)-[:RESOLVES_TO]->(cm)",
            resolves_items,
        )
        self._run_unwind(
            "UNWIND $items AS p "
            "MATCH (jf:JsFunction {id: p.fnId}) "
            "MATCH (cm:ControllerMethod {id: p.cmId}) "
            "MERGE (jf)-[:AJAX_CALLS]->(cm)",
            ajax_calls_items,
        )

    def link_js_navigates_to_batch(self, pairs: list):
        """[(fn, href, ctrl, cm), ...] → JsFunction -[:NAVIGATES_TO]-> ControllerMethod"""
        items = [
            {
                "fnId": f"{fn.file_path}#{fn.name}",
                "cmId": _cm_id(ctrl.class_name, cm.name, cm.url),
            }
            for fn, _href, ctrl, cm in pairs
        ]
        self._run_unwind(
            "UNWIND $items AS p "
            "MATCH (jf:JsFunction {id: p.fnId}) "
            "MATCH (cm:ControllerMethod {id: p.cmId}) "
            "MERGE (jf)-[:NAVIGATES_TO]->(cm)",
            items,
        )

    # ------------------------------------------------------------------
    # 診断クエリ
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        result = {}
        with self.driver.session() as session:
            for record in session.run(
                "MATCH (n) RETURN labels(n)[0] AS lbl, count(n) AS cnt"
            ):
                result[f"node:{record['lbl']}"] = record["cnt"]
            for record in session.run(
                "MATCH ()-[r]->() RETURN type(r) AS lbl, count(r) AS cnt"
            ):
                result[f"edge:{record['lbl']}"] = record["cnt"]
        return result

    def unresolved_ajax_calls(self) -> list:
        with self.driver.session() as session:
            return [
                {"url": r["url"], "method": r["method"]}
                for r in session.run(
                    "MATCH (a:AjaxCall) WHERE NOT (a)-[:RESOLVES_TO]->() "
                    "RETURN a.url AS url, a.method AS method ORDER BY a.url"
                )
            ]
