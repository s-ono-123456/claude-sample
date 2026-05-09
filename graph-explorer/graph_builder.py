from pyvis.network import Network
from neo4j.graph import Node

_GRAPH_OPTIONS = """
{
  "nodes": {
    "shape": "circle",
    "font": {"size": 14, "color": "#ffffff"},
    "margin": 12
  },
  "edges": {
    "font": {"size": 12, "align": "top"},
    "smooth": {"type": "curvedCW", "roundness": 0.1}
  },
  "physics": {
    "barnesHut": {
      "springLength": 280,
      "springConstant": 0.03,
      "damping": 0.09,
      "avoidOverlap": 0.5
    }
  }
}
"""

NODE_COLORS: dict[str, str] = {
    "Screen": "#4287f5",
    "Button": "#f5a142",
    "ControllerMethod": "#a142f5",
    "ServiceMethod": "#42b883",
    "DaoMethod": "#c8a060",
    "SqlStatement": "#909090",
    "Table": "#f54242",
    "JsFunction": "#f5e642",
}


def _wrap(text: str, width: int = 6) -> str:
    """width 文字ごとに改行（日本語の長いラベルを正円に収める）"""
    if len(text) <= width:
        return text
    return "\n".join(text[i : i + width] for i in range(0, len(text), width))


def _display_label(node: Node) -> str:
    if "Screen" in node.labels and node.get("title"):
        return _wrap(str(node["title"]))
    for key in ["viewName", "label", "url", "name", "sqlId"]:
        if key in node:
            val = str(node[key])
            return val[-30:] if len(val) > 30 else val
    return next(iter(node.labels), "?")


def _tooltip(node: Node) -> str:
    label = next(iter(node.labels), "?")
    props = "\n".join(f"{k}: {v}" for k, v in node.items())
    return f"[{label}]\n{props}"


def _color(node: Node) -> str:
    for label in node.labels:
        if label in NODE_COLORS:
            return NODE_COLORS[label]
    return "#cccccc"


def build_pyvis_graph(paths: list, show_edge_labels: bool = True) -> str:
    net = Network(height="580px", width="100%", directed=True, bgcolor="#f8f9fa")
    net.set_options(_GRAPH_OPTIONS)

    seen_nodes: set[str] = set()
    seen_edges: set[tuple] = set()

    for path in paths:
        start = path.start_node
        if start.element_id not in seen_nodes:
            net.add_node(
                start.element_id,
                label=_display_label(start),
                color=_color(start),
                title=_tooltip(start),
                shape="circle",
                font={"size": 14, "color": "#ffffff"},
            )
            seen_nodes.add(start.element_id)

        for rel in path.relationships:
            end = rel.end_node
            if end.element_id not in seen_nodes:
                net.add_node(
                    end.element_id,
                    label=_display_label(end),
                    color=_color(end),
                    title=_tooltip(end),
                    shape="circle",
                    font={"size": 14, "color": "#ffffff"},
                )
                seen_nodes.add(end.element_id)

            edge_key = (rel.start_node.element_id, rel.end_node.element_id, rel.type)
            if edge_key not in seen_edges:
                if show_edge_labels:
                    edge_label = rel.get("trigger") or rel.type
                else:
                    edge_label = ""
                net.add_edge(
                    rel.start_node.element_id,
                    rel.end_node.element_id,
                    label=edge_label,
                )
                seen_edges.add(edge_key)

    return net.generate_html()
