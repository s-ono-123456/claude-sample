#!/usr/bin/env python3
"""queries.cypher の全クエリをNeo4jに投げて結果を表示する"""
import sys
from neo4j import GraphDatabase
from neo4j.graph import Path, Node, Relationship
import yaml

def load_config(path="config.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

# ─── パス/ノード/リレーション の人が読める表現 ───────────────────────────────

def node_str(n: Node) -> str:
    label = next(iter(n.labels), "?")
    key_props = ["name", "className", "url", "viewName", "path", "sqlId", "id"]
    for k in key_props:
        if k in n:
            val = str(n[k])
            if len(val) > 40:
                val = val[-40:]  # パスは末尾を使う
            return f"({label}: {val})"
    return f"({label})"

def rel_str(r: Relationship) -> str:
    return f"-[:{r.type}]->"

def path_str(p: Path) -> str:
    parts = [node_str(p.start_node)]
    for rel in p.relationships:
        parts.append(f"-[:{rel.type}]->")
        parts.append(node_str(rel.end_node))
    return " ".join(parts)

def fmt_record(record):
    parts = []
    for key, val in record.items():
        if isinstance(val, Path):
            parts.append(f"{key}: {path_str(val)}")
        elif isinstance(val, Node):
            parts.append(f"{key}: {node_str(val)}")
        elif isinstance(val, list):
            inner = ", ".join(str(v) for v in val) if val else "(なし)"
            parts.append(f"{key}: [{inner}]")
        else:
            v = str(val) if val is not None else "(null)"
            if len(v) > 60:
                v = v[:60] + "…"
            parts.append(f"{key}: {v}")
    return "  " + " | ".join(parts)

# ─── クエリ定義 ──────────────────────────────────────────────────────────────

QUERIES = [
    (
        "Q1: フォーム経由の全呼び出し連鎖 (Screen→Button→Controller→Service→DAO→Table)",
        """
        MATCH path = (s:Screen)-[:CONTAINS]->(b:Button)
          -[:SUBMITS_TO]->(cm:ControllerMethod)
          -[:CALLS]->(sm:ServiceMethod)
          -[:CALLS]->(dm:DaoMethod)
          -[:EXECUTES]->(sql:SqlStatement)
          -[:READS|WRITES]->(t:Table)
        RETURN path LIMIT 5
        """,
    ),
    (
        "Q2: JS経由の全呼び出し連鎖 (Screen→Button→JsFunction→Controller→Service→DAO→Table)",
        """
        MATCH path = (s:Screen)-[:CONTAINS]->(b:Button)
          -[:TRIGGERS_JS]->(jf:JsFunction)
          -[:AJAX_CALLS]->(cm:ControllerMethod)
          -[:CALLS]->(sm:ServiceMethod)
          -[:CALLS]->(dm:DaoMethod)
          -[:EXECUTES]->(sql:SqlStatement)
          -[:READS|WRITES]->(t:Table)
        RETURN path LIMIT 5
        """,
    ),
    (
        "Q3: 画面遷移フロー (Screen → Screen 最大3ホップ)",
        """
        MATCH path = (s:Screen)-[:TRANSITIONS_TO*1..3]->(e:Screen)
        RETURN path LIMIT 8
        """,
    ),
    (
        "Q4: 特定テーブル(orders)を参照している画面を逆引き",
        """
        MATCH (t:Table)<-[:READS|WRITES]-(sql:SqlStatement)
          <-[:EXECUTES]-(dm:DaoMethod)
          <-[:CALLS]-(sm:ServiceMethod)
          <-[:CALLS]-(cm:ControllerMethod)
          <-[:SUBMITS_TO|AJAX_CALLS]-(b)
          <-[:CONTAINS]-(s:Screen)
        RETURN t.name AS tableName, s.viewName AS screen,
               cm.url AS endpoint, labels(b)[0] AS triggerType
        ORDER BY t.name, s.viewName
        """,
    ),
    (
        "Q5: Controllerごとのトリガー一覧 (フォーム/AJAX/リンク)",
        """
        MATCH (cm:ControllerMethod)
        OPTIONAL MATCH (b1:Button)-[:SUBMITS_TO]->(cm)
        OPTIONAL MATCH (b2:Button)-[:NAVIGATES_TO]->(cm)
        OPTIONAL MATCH (jf:JsFunction)-[:AJAX_CALLS]->(cm)
        WITH cm, collect(DISTINCT b1.label) AS submits,
             collect(DISTINCT b2.label) AS links,
             collect(DISTINCT jf.name) AS ajaxFns
        WHERE size(submits)+size(links)+size(ajaxFns) > 0
        RETURN cm.url AS url, cm.httpMethod AS method,
               submits, links, ajaxFns
        ORDER BY cm.url
        """,
    ),
    (
        "Q6: JS関数の呼び出しツリー (placeOrder から3ホップ)",
        """
        MATCH path = (jf:JsFunction {name: 'placeOrder'})-[:CALLS*0..3]->(callee:JsFunction)
        RETURN path
        """,
    ),
    (
        "Q7: 未解決AjaxCall一覧 (ControllerMethodに紐付かないもの)",
        """
        MATCH (a:AjaxCall)
        WHERE NOT (a)-[:RESOLVES_TO]->(:ControllerMethod)
        RETURN a.url AS url, a.method AS method, a.unresolved AS unresolved
        ORDER BY a.url
        """,
    ),
    (
        "Q8: ControllerMethodごとのDB書き込みテーブル一覧",
        """
        MATCH (cm:ControllerMethod)
          -[:CALLS]->(sm:ServiceMethod)
          -[:CALLS]->(dm:DaoMethod)
          -[:EXECUTES]->(sql:SqlStatement)
          -[:WRITES]->(t:Table)
        RETURN cm.url AS endpoint, cm.httpMethod AS method,
               collect(DISTINCT t.name) AS writeTables
        ORDER BY cm.url
        """,
    ),
    (
        "Q9: 画面ごとの使用テーブル一覧",
        """
        MATCH (s:Screen)-[:CONTAINS]->(b:Button)
          -[:SUBMITS_TO|NAVIGATES_TO]->(cm:ControllerMethod)
          -[:CALLS*1..2]->(dm:DaoMethod)
          -[:EXECUTES]->(sql:SqlStatement)
          -[:READS|WRITES]->(t:Table)
        RETURN s.viewName AS screen, collect(DISTINCT t.name) AS tables
        ORDER BY s.viewName
        """,
    ),
    (
        "Q10: 孤立ノード検出 (エッジを持たないノード)",
        """
        MATCH (n)
        WHERE NOT (n)--()
        RETURN labels(n)[0] AS label,
               coalesce(n.name, n.className, n.viewName, n.url, n.id, n.path) AS id
        LIMIT 20
        """,
    ),
    (
        "Q11: ノード・エッジ数サマリー",
        """
        MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count
        UNION ALL
        MATCH ()-[r]->() RETURN type(r) AS label, count(r) AS count
        ORDER BY count DESC
        """,
    ),
    (
        "Q12: window.location.href 経由ナビゲーション一覧",
        """
        MATCH (jf:JsFunction)-[:NAVIGATES_TO]->(cm:ControllerMethod)
        RETURN jf.name AS jsFunction,
               cm.url AS targetUrl, cm.httpMethod AS method
        ORDER BY jf.name
        """,
    ),
]

def run_all(cfg):
    neo4j_cfg = cfg["neo4j"]
    driver = GraphDatabase.driver(
        neo4j_cfg["uri"], auth=(neo4j_cfg["user"], neo4j_cfg["password"])
    )
    with driver.session() as session:
        for title, cypher in QUERIES:
            print(f"\n{'='*70}")
            print(f"  {title}")
            print('='*70)
            try:
                records = list(session.run(cypher.strip()))
                if not records:
                    print("  (結果なし)")
                    continue
                print(f"  → {len(records)} 件")
                for r in records:
                    print(fmt_record(r))
            except Exception as e:
                print(f"  ERROR: {e}")
    driver.close()

if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    cfg = load_config(cfg_path)
    run_all(cfg)
