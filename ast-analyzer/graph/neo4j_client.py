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

    # ------------------------------------------------------------------
    # スキーマ初期化
    # ------------------------------------------------------------------
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
            # Phase 3
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:JsFile)           REQUIRE n.path IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:JsFunction)       REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:AjaxCall)         REQUIRE n.id IS UNIQUE",
        ]
        for s in stmts:
            self._run(s)
        log.info("制約を作成しました")

    # ------------------------------------------------------------------
    # ノード保存 (Phase 2: Screen / Button)
    # ------------------------------------------------------------------
    def save_screen(self, screen: ScreenInfo):
        self._run(
            "MERGE (s:Screen {path: $path}) "
            "SET s.viewName = $vn, s.title = $title",
            path=screen.path, vn=screen.view_name, title=screen.title,
        )
        for btn in screen.buttons:
            self._run(
                "MERGE (b:Button {uid: $uid}) "
                "SET b.label = $label, b.buttonType = $bt, "
                "    b.targetUrl = $url, b.httpMethod = $hm, b.onclickFn = $fn",
                uid=btn.uid, label=btn.label, bt=btn.button_type.value,
                url=btn.target_url, hm=btn.http_method, fn=btn.onclick_fn,
            )
            self._run(
                "MATCH (s:Screen {path: $path}) "
                "MATCH (b:Button {uid: $uid}) "
                "MERGE (s)-[:CONTAINS]->(b)",
                path=screen.path, uid=btn.uid,
            )

    # ------------------------------------------------------------------
    # エッジ生成 (Phase 2)
    # ------------------------------------------------------------------
    def link_button_submits_to(self, btn: ButtonInfo, ctrl_class: str, cm: ControllerMethodInfo):
        """フォームsubmitボタン → SUBMITS_TO → ControllerMethod"""
        self._run(
            "MATCH (b:Button {uid: $uid}) "
            "MATCH (cm:ControllerMethod {id: $cmId}) "
            "MERGE (b)-[:SUBMITS_TO]->(cm)",
            uid=btn.uid,
            cmId=_cm_id(ctrl_class, cm.name, cm.url),
        )

    def link_button_navigates_to(self, btn: ButtonInfo, ctrl_class: str, cm: ControllerMethodInfo):
        """リンクボタン → NAVIGATES_TO → ControllerMethod"""
        self._run(
            "MATCH (b:Button {uid: $uid}) "
            "MATCH (cm:ControllerMethod {id: $cmId}) "
            "MERGE (b)-[:NAVIGATES_TO]->(cm)",
            uid=btn.uid,
            cmId=_cm_id(ctrl_class, cm.name, cm.url),
        )

    def link_button_triggers_js(self, btn: ButtonInfo):
        """onclickボタン → TRIGGERS_JS → JsFunction (Phase 3で使用)"""
        # JSFunctionノードは Phase 3 で作成するため、ここではButtonのプロパティとして保持済み
        pass

    def link_controller_returns_view(
        self, ctrl_class: str, cm: ControllerMethodInfo, screen: ScreenInfo
    ):
        """ControllerMethod → RETURNS_VIEW → Screen"""
        self._run(
            "MATCH (cm:ControllerMethod {id: $cmId}) "
            "MATCH (s:Screen {path: $path}) "
            "MERGE (cm)-[:RETURNS_VIEW]->(s)",
            cmId=_cm_id(ctrl_class, cm.name, cm.url),
            path=screen.path,
        )

    def link_controller_redirects_to(
        self, ctrl_class: str, cm: ControllerMethodInfo, screen: ScreenInfo
    ):
        """ControllerMethod → REDIRECTS_TO → Screen (return "redirect:/path")"""
        self._run(
            "MATCH (cm:ControllerMethod {id: $cmId}) "
            "MATCH (s:Screen {path: $path}) "
            "MERGE (cm)-[:REDIRECTS_TO]->(s)",
            cmId=_cm_id(ctrl_class, cm.name, cm.url),
            path=screen.path,
        )

    def link_screen_transitions(self, from_path: str, to_path: str, trigger: str = ""):
        """Screen → TRANSITIONS_TO → Screen (画面遷移の直接エッジ)"""
        self._run("MERGE (s:Screen {path: $path})", path=to_path)
        self._run(
            "MATCH (s1:Screen {path: $fromPath}) "
            "MATCH (s2:Screen {path: $toPath}) "
            "MERGE (s1)-[:TRANSITIONS_TO {trigger: $trigger}]->(s2)",
            fromPath=from_path, toPath=to_path, trigger=trigger,
        )

    # ------------------------------------------------------------------
    # ノード保存 (Phase 1)
    # ------------------------------------------------------------------
    def save_controller(self, ctrl: ControllerInfo):
        self._run(
            "MERGE (c:Controller {className: $cn}) "
            "SET c.filePath = $fp, c.baseUrl = $bu",
            cn=ctrl.class_name, fp=ctrl.file_path, bu=ctrl.base_url,
        )
        for m in ctrl.methods:
            mid = _cm_id(ctrl.class_name, m.name, m.url)
            self._run(
                "MERGE (cm:ControllerMethod {id: $id}) "
                "SET cm.name = $name, cm.url = $url, cm.httpMethod = $hm, "
                "    cm.returnView = $rv, cm.redirectTo = $rt, cm.className = $cn",
                id=mid, name=m.name, url=m.url, hm=m.http_method.value,
                rv=m.return_view, rt=m.redirect_to, cn=ctrl.class_name,
            )
            self._run(
                "MATCH (c:Controller {className: $cn}) "
                "MATCH (cm:ControllerMethod {id: $id}) "
                "MERGE (c)-[:HAS_METHOD]->(cm)",
                cn=ctrl.class_name, id=mid,
            )

    def save_service(self, svc: ServiceInfo):
        self._run(
            "MERGE (s:Service {className: $cn}) SET s.filePath = $fp",
            cn=svc.class_name, fp=svc.file_path,
        )
        for m in svc.methods:
            mid = _sm_id(svc.class_name, m.name)
            self._run(
                "MERGE (sm:ServiceMethod {id: $id}) "
                "SET sm.name = $name, sm.signature = $sig, sm.className = $cn",
                id=mid, name=m.name, sig=m.signature, cn=svc.class_name,
            )
            self._run(
                "MATCH (s:Service {className: $cn}) "
                "MATCH (sm:ServiceMethod {id: $id}) "
                "MERGE (s)-[:HAS_METHOD]->(sm)",
                cn=svc.class_name, id=mid,
            )

    def save_dao(self, dao: DaoInfo):
        self._run(
            "MERGE (d:Dao {className: $cn}) SET d.filePath = $fp, d.fqn = $fqn",
            cn=dao.class_name, fp=dao.file_path, fqn=dao.fqn,
        )
        for m in dao.methods:
            mid = _dm_id(dao.class_name, m.name)
            self._run(
                "MERGE (dm:DaoMethod {id: $id}) "
                "SET dm.name = $name, dm.signature = $sig, dm.className = $cn",
                id=mid, name=m.name, sig=m.signature, cn=dao.class_name,
            )
            self._run(
                "MATCH (d:Dao {className: $cn}) "
                "MATCH (dm:DaoMethod {id: $id}) "
                "MERGE (d)-[:HAS_METHOD]->(dm)",
                cn=dao.class_name, id=mid,
            )

    def save_mapper(self, mapper: MapperInfo):
        # namespace の末尾 simple name でDaoMethodと照合
        simple_name = mapper.namespace.split(".")[-1]

        for stmt in mapper.statements:
            sid = _sql_id(mapper.namespace, stmt.sql_id)
            self._run(
                "MERGE (sql:SqlStatement {id: $id}) "
                "SET sql.sqlId = $sqlId, sql.sqlType = $type, "
                "    sql.rawSql = $raw, sql.namespace = $ns",
                id=sid, sqlId=stmt.sql_id, type=stmt.sql_type.value,
                raw=stmt.raw_sql, ns=mapper.namespace,
            )
            # DaoMethod → SqlStatement
            dm_id = _dm_id(simple_name, stmt.sql_id)
            self._run(
                "MATCH (dm:DaoMethod {id: $dmId}) "
                "MATCH (sql:SqlStatement {id: $sqlId}) "
                "MERGE (dm)-[:EXECUTES]->(sql)",
                dmId=dm_id, sqlId=sid,
            )
            # SqlStatement → Table
            for table in stmt.tables:
                self._run("MERGE (t:Table {name: $name})", name=table)
                rel = "READS" if stmt.sql_type == SqlType.SELECT else "WRITES"
                self._run(
                    f"MATCH (sql:SqlStatement {{id: $sid}}) "
                    f"MATCH (t:Table {{name: $tn}}) "
                    f"MERGE (sql)-[:{rel}]->(t)",
                    sid=sid, tn=table,
                )

    # ------------------------------------------------------------------
    # エッジ生成
    # ------------------------------------------------------------------
    def link_controller_to_service(
        self,
        ctrl_class: str,
        cm: ControllerMethodInfo,
        svc_class: str,
        sm_name: str,
    ):
        self._run(
            "MATCH (cm:ControllerMethod {id: $cmId}) "
            "MATCH (sm:ServiceMethod {id: $smId}) "
            "MERGE (cm)-[:CALLS]->(sm)",
            cmId=_cm_id(ctrl_class, cm.name, cm.url),
            smId=_sm_id(svc_class, sm_name),
        )

    def link_service_to_dao(
        self,
        svc_class: str,
        sm_name: str,
        dao_class: str,
        dm_name: str,
    ):
        self._run(
            "MATCH (sm:ServiceMethod {id: $smId}) "
            "MATCH (dm:DaoMethod {id: $dmId}) "
            "MERGE (sm)-[:CALLS]->(dm)",
            smId=_sm_id(svc_class, sm_name),
            dmId=_dm_id(dao_class, dm_name),
        )

    # ------------------------------------------------------------------
    # Phase 3: JsFile / JsFunction / AjaxCall
    # ------------------------------------------------------------------

    def save_js_file(self, js_file: JsFileInfo):
        """JsFile と JsFunction ノード・AjaxCall ノードを保存する。"""
        self._run("MERGE (f:JsFile {path: $path})", path=js_file.path)

        for fn in js_file.functions:
            fn_id = f"{js_file.path}#{fn.name}"
            self._run(
                "MERGE (jf:JsFunction {id: $id}) "
                "SET jf.name = $name, jf.filePath = $fp, jf.line = $line",
                id=fn_id, name=fn.name, fp=js_file.path, line=fn.line,
            )
            self._run(
                "MATCH (f:JsFile {path: $path}) "
                "MATCH (jf:JsFunction {id: $id}) "
                "MERGE (f)-[:CONTAINS]->(jf)",
                path=js_file.path, id=fn_id,
            )
            for ajax in fn.ajax_calls:
                ajax_id = f"{fn_id}#{ajax.url}#{ajax.http_method}"
                self._run(
                    "MERGE (a:AjaxCall {id: $id}) "
                    "SET a.url = $url, a.method = $method, a.unresolved = $unresolved",
                    id=ajax_id, url=ajax.url,
                    method=ajax.http_method, unresolved=ajax.unresolved,
                )
                self._run(
                    "MATCH (jf:JsFunction {id: $fnId}) "
                    "MATCH (a:AjaxCall {id: $ajaxId}) "
                    "MERGE (jf)-[:MAKES_AJAX]->(a)",
                    fnId=fn_id, ajaxId=ajax_id,
                )

    def link_button_triggers_js(self, btn_uid: str, fn_file_path: str, fn_name: str):
        """Button → TRIGGERS_JS → JsFunction"""
        fn_id = f"{fn_file_path}#{fn_name}"
        self._run(
            "MATCH (b:Button {uid: $uid}) "
            "MATCH (jf:JsFunction {id: $fnId}) "
            "MERGE (b)-[:TRIGGERS_JS]->(jf)",
            uid=btn_uid, fnId=fn_id,
        )

    def link_js_calls_js(
        self, caller_file: str, caller_name: str, callee_file: str, callee_name: str
    ):
        """JsFunction → CALLS → JsFunction"""
        caller_id = f"{caller_file}#{caller_name}"
        callee_id = f"{callee_file}#{callee_name}"
        self._run(
            "MATCH (caller:JsFunction {id: $callerId}) "
            "MATCH (callee:JsFunction {id: $calleeId}) "
            "MERGE (caller)-[:CALLS]->(callee)",
            callerId=caller_id, calleeId=callee_id,
        )

    def link_ajax_to_controller(
        self,
        fn_file: str,
        fn_name: str,
        ajax_url: str,
        ajax_method: str,
        ctrl_class: str,
        cm: ControllerMethodInfo,
    ):
        """AjaxCall → RESOLVES_TO → ControllerMethod、JsFunction → AJAX_CALLS → ControllerMethod"""
        fn_id = f"{fn_file}#{fn_name}"
        ajax_id = f"{fn_id}#{ajax_url}#{ajax_method}"
        cm_id = _cm_id(ctrl_class, cm.name, cm.url)

        self._run(
            "MATCH (a:AjaxCall {id: $ajaxId}) "
            "MATCH (cm:ControllerMethod {id: $cmId}) "
            "MERGE (a)-[:RESOLVES_TO]->(cm)",
            ajaxId=ajax_id, cmId=cm_id,
        )
        self._run(
            "MATCH (jf:JsFunction {id: $fnId}) "
            "MATCH (cm:ControllerMethod {id: $cmId}) "
            "MERGE (jf)-[:AJAX_CALLS]->(cm)",
            fnId=fn_id, cmId=cm_id,
        )

    def link_js_navigates_to(
        self, fn_file: str, fn_name: str, ctrl_class: str, cm: ControllerMethodInfo
    ):
        """JsFunction → NAVIGATES_TO → ControllerMethod (window.location.href)"""
        fn_id = f"{fn_file}#{fn_name}"
        self._run(
            "MATCH (jf:JsFunction {id: $fnId}) "
            "MATCH (cm:ControllerMethod {id: $cmId}) "
            "MERGE (jf)-[:NAVIGATES_TO]->(cm)",
            fnId=fn_id, cmId=_cm_id(ctrl_class, cm.name, cm.url),
        )

    # ------------------------------------------------------------------
    # 診断クエリ
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """グラフの全ノード・エッジ数を返す。"""
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
        """RESOLVES_TO を持たない AjaxCall 一覧を返す。"""
        with self.driver.session() as session:
            return [
                {"url": r["url"], "method": r["method"]}
                for r in session.run(
                    "MATCH (a:AjaxCall) WHERE NOT (a)-[:RESOLVES_TO]->() "
                    "RETURN a.url AS url, a.method AS method ORDER BY a.url"
                )
            ]
