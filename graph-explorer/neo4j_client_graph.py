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
