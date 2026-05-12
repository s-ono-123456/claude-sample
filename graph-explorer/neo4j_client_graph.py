import yaml
from neo4j import GraphDatabase


def load_neo4j_config(config_path: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["neo4j"]


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self._driver.close()

    def get_all_screens(self) -> dict[str, str]:
        """viewName -> title の辞書を返す。title が空の場合は viewName を代用。"""
        with self._driver.session() as session:
            result = session.run(
                "MATCH (s:Screen) RETURN s.viewName AS vn, s.title AS title ORDER BY s.title"
            )
            return {
                r["vn"]: r["title"] or r["vn"]
                for r in result
                if r["vn"]
            }

    def get_all_transitions(self) -> list:
        """全 TRANSITIONS_TO エッジを辞書のリストで返す。"""
        with self._driver.session() as session:
            result = session.run(
                "MATCH (s1:Screen)-[r:TRANSITIONS_TO]->(s2:Screen) "
                "RETURN "
                "  coalesce(s1.title, s1.viewName) AS from_screen, "
                "  s1.viewName AS from_view, "
                "  coalesce(s2.title, s2.viewName) AS to_screen, "
                "  s2.viewName AS to_view, "
                "  r.trigger AS trigger, "
                "  r.condition AS condition "
                "ORDER BY from_screen, to_screen"
            )
            return [dict(r) for r in result]

    def get_paths_between(self, from_view: str, to_view: str, max_hops: int = 5) -> list:
        """2画面間の全 TRANSITIONS_TO パスを返す。"""
        with self._driver.session() as session:
            result = session.run(
                f"MATCH path = (s1:Screen {{viewName: $from_view}})"
                f"-[:TRANSITIONS_TO*1..{max_hops}]->(s2:Screen {{viewName: $to_view}}) "
                "RETURN path",
                from_view=from_view,
                to_view=to_view,
            )
            return [r["path"] for r in result]

    def get_screen_transitions(self, name: str, hops: int) -> list:
        with self._driver.session() as session:
            result = session.run(
                f"MATCH path = (s:Screen {{viewName: $name}})"
                f"-[:TRANSITIONS_TO*1..{hops}]->(e:Screen) RETURN path",
                name=name,
            )
            return [r["path"] for r in result]

    def get_call_chain(self, name: str) -> list:
        paths = []
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH path = (s:Screen {viewName: $name})-[:CONTAINS]->(b:Button)
                  -[:SUBMITS_TO]->(cm:ControllerMethod)
                  -[:CALLS]->(sm:ServiceMethod)
                  -[:CALLS]->(dm:DaoMethod)
                  -[:EXECUTES]->(sql:SqlStatement)
                  -[:READS|WRITES]->(t:Table)
                RETURN path
                """,
                name=name,
            )
            paths.extend(r["path"] for r in result)

            result = session.run(
                """
                MATCH path = (s:Screen {viewName: $name})-[:CONTAINS]->(b:Button)
                  -[:TRIGGERS_JS]->(jf:JsFunction)
                  -[:AJAX_CALLS]->(cm:ControllerMethod)
                  -[:CALLS]->(sm:ServiceMethod)
                  -[:CALLS]->(dm:DaoMethod)
                  -[:EXECUTES]->(sql:SqlStatement)
                  -[:READS|WRITES]->(t:Table)
                RETURN path
                """,
                name=name,
            )
            paths.extend(r["path"] for r in result)
        return paths
