import os
import sys

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.dirname(__file__))

from neo4j_client_graph import Neo4jClient, load_neo4j_config
from graph_builder import NODE_COLORS, build_pyvis_graph

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "ast-analyzer", "config.yaml")


@st.cache_resource
def get_client() -> Neo4jClient:
    cfg = load_neo4j_config(_CONFIG_PATH)
    return Neo4jClient(cfg["uri"], cfg["user"], cfg["password"])


def _legend():
    st.subheader("凡例")
    cols = st.columns(4)
    for i, (label, color) in enumerate(NODE_COLORS.items()):
        with cols[i % 4]:
            st.markdown(
                f'<span style="background:{color};padding:2px 10px;border-radius:4px;'
                f'color:#fff;font-size:13px">{label}</span>',
                unsafe_allow_html=True,
            )


def page_screen_transitions():
    st.header("画面遷移グラフ")
    client = get_client()
    screens = client.get_all_screens()
    if not screens:
        st.warning("Screen ノードが見つかりません。Neo4j にデータが登録されているか確認してください。")
        return

    selected = st.sidebar.selectbox(
        "画面を選択",
        list(screens.keys()),
        format_func=lambda vn: screens[vn],
        key="trans_screen",
    )
    hops = st.sidebar.slider("最大ホップ数", 1, 5, 3, key="trans_hops")

    with st.spinner("グラフを生成中..."):
        paths = client.get_screen_transitions(selected, hops)

    if not paths:
        st.info("選択した画面からの遷移が見つかりませんでした。")
        return

    html = build_pyvis_graph(paths, show_edge_labels=True)
    components.html(html, height=620, scrolling=True)
    st.caption(f"{len(paths)} 本のパスを表示")


def page_call_chain():
    st.header("フル呼び出し連鎖グラフ")
    client = get_client()
    screens = client.get_all_screens()
    if not screens:
        st.warning("Screen ノードが見つかりません。Neo4j にデータが登録されているか確認してください。")
        return

    selected = st.sidebar.selectbox(
        "画面を選択",
        list(screens.keys()),
        format_func=lambda vn: screens[vn],
        key="chain_screen",
    )

    with st.spinner("グラフを生成中..."):
        paths = client.get_call_chain(selected)

    if not paths:
        st.info("呼び出し連鎖が見つかりませんでした。")
        return

    html = build_pyvis_graph(paths, show_edge_labels=True)
    components.html(html, height=620, scrolling=True)
    st.caption(f"{len(paths)} 本のパスを表示")
    _legend()


def main():
    st.set_page_config(page_title="Graph Explorer", layout="wide")
    st.title("Graph Explorer")

    page = st.sidebar.radio("機能", ["画面遷移グラフ", "フル呼び出し連鎖グラフ"])
    st.sidebar.divider()

    if page == "画面遷移グラフ":
        page_screen_transitions()
    else:
        page_call_chain()


if __name__ == "__main__":
    main()
