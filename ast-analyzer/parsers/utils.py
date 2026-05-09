import re
from typing import List, Type, TypeVar

try:
    import javalang
    import javalang.tree
except ImportError:
    javalang = None

T = TypeVar("T")


def walk_for_type(node, target_type: Type[T], _visited: set = None) -> List[T]:
    """javalangのASTノードを再帰的に走査して target_type のノードをすべて返す"""
    if _visited is None:
        _visited = set()

    results = []
    if node is None:
        return results

    node_id = id(node)
    if node_id in _visited:
        return results
    if javalang and isinstance(node, javalang.tree.Node):
        _visited.add(node_id)

    if javalang and isinstance(node, target_type):
        results.append(node)

    if javalang and isinstance(node, javalang.tree.Node):
        # node.attrs で直接の子フィールド名のみを取得し、walk_treeの全子孫展開を避ける
        for attr in node.attrs:
            child = getattr(node, attr, None)
            if child is None:
                continue
            if isinstance(child, javalang.tree.Node):
                results.extend(walk_for_type(child, target_type, _visited))
            elif isinstance(child, (list, tuple, frozenset, set)):
                for item in child:
                    if item is not None:
                        results.extend(walk_for_type(item, target_type, _visited))
    elif isinstance(node, (list, tuple)):
        for item in node:
            if item is not None:
                results.extend(walk_for_type(item, target_type, _visited))
    return results


def get_annotation_url(ann) -> str:
    """@GetMapping("/path") や @RequestMapping(value="/path") からURL文字列を抽出する"""
    if not javalang:
        return ""
    el = ann.element
    if el is None:
        return ""
    # @GetMapping("/path") の形式 — 単一リテラル
    if isinstance(el, javalang.tree.Literal):
        return el.value.strip('"\'')
    # @RequestMapping(value="/path") の形式 — ElementValuePair のリスト
    if isinstance(el, list):
        for item in el:
            if isinstance(item, javalang.tree.ElementValuePair) and item.name in ("value", "path"):
                v = item.value
                if isinstance(v, javalang.tree.Literal):
                    return v.value.strip('"\'')
                # value={"/p1", "/p2"} → 先頭のみ取得
                if hasattr(v, "initializers") and v.initializers:
                    first = v.initializers[0]
                    if isinstance(first, javalang.tree.Literal):
                        return first.value.strip('"\'')
    return ""


def build_signature(method) -> str:
    """メソッドの簡易シグネチャ文字列を生成する: methodName(Type1, Type2)"""
    params = []
    for param in (method.parameters or []):
        type_name = param.type.name if param.type else "Object"
        params.append(type_name)
    return f"{method.name}({', '.join(params)})"


def extract_table_names(sql: str) -> List[str]:
    """SQL文からテーブル名を正規表現で抽出する。MyBatisの #{} ${} 記法を事前に除去する"""
    sql = re.sub(r"#\{[^}]+\}", "?", sql)
    sql = re.sub(r"\$\{[^}]+\}", "?", sql)
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)

    tables: set = set()

    for pattern in (
        r"\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        r"\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        r"\bINTO\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        r"\bUPDATE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
    ):
        for m in re.finditer(pattern, sql, re.IGNORECASE):
            name = m.group(1).upper()
            # サブクエリのエイリアスや予約語を除外
            if name not in ("SELECT", "WHERE", "SET", "VALUES", "ON", "AND", "OR"):
                tables.add(name)

    return list(tables)
