import os
import sys

import pandas as pd
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
    show_self_loops = st.sidebar.checkbox("同一画面遷移を表示", value=True, key="trans_self_loops")

    with st.spinner("グラフを生成中..."):
        paths = client.get_screen_transitions(selected, hops)

    if not paths:
        st.info("選択した画面からの遷移が見つかりませんでした。")
        return

    html = build_pyvis_graph(paths, show_edge_labels=True, show_self_loops=show_self_loops)
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


def page_transition_table():
    st.header("遷移条件一覧")
    client = get_client()
    rows = client.get_all_transitions()
    if not rows:
        st.warning("TRANSITIONS_TO エッジが見つかりません。ast-analyzer でグラフを構築してください。")
        return

    df = pd.DataFrame(rows, columns=["from_screen", "to_screen", "trigger", "condition",
                                      "from_view", "to_view"])

    # ── フィルタ ──────────────────────────────────────────────────────
    all_from = sorted(df["from_screen"].unique().tolist())
    selected_from = st.sidebar.multiselect("遷移元を絞り込む", all_from, default=[])
    if selected_from:
        df = df[df["from_screen"].isin(selected_from)]

    # 表示用: None → 「（条件なし）」
    display_df = df[["from_screen", "to_screen", "trigger", "condition"]].copy()
    display_df.columns = ["遷移元", "遷移先", "トリガー", "条件"]
    display_df["条件"] = display_df["条件"].fillna("（条件なし）")

    st.dataframe(display_df, use_container_width=True, hide_index=True)
    st.caption(f"{len(display_df)} 件の遷移を表示")

    # ── 2画面間の経路 ─────────────────────────────────────────────────
    st.subheader("2画面間の経路")
    screens = client.get_all_screens()
    if screens:
        col1, col2 = st.columns(2)
        with col1:
            from_view = st.selectbox(
                "遷移元", list(screens.keys()),
                format_func=lambda vn: screens[vn],
                key="path_from",
            )
        with col2:
            to_view = st.selectbox(
                "遷移先", list(screens.keys()),
                format_func=lambda vn: screens[vn],
                key="path_to",
            )
        if st.button("経路を検索"):
            with st.spinner("経路を検索中..."):
                paths = client.get_paths_between(from_view, to_view)
            if not paths:
                st.info("経路が見つかりませんでした。")
            else:
                html = build_pyvis_graph(paths, show_edge_labels=True, show_self_loops=True)
                components.html(html, height=500, scrolling=True)
                st.caption(f"{len(paths)} 本の経路を表示")


def main():
    st.set_page_config(page_title="Graph Explorer", layout="wide")
    st.title("Graph Explorer")

    page = st.sidebar.radio("機能", ["画面遷移グラフ", "フル呼び出し連鎖グラフ", "遷移条件一覧"])
    st.sidebar.divider()

    if page == "画面遷移グラフ":
        page_screen_transitions()
    elif page == "フル呼び出し連鎖グラフ":
        page_call_chain()
    else:
        page_transition_table()


if __name__ == "__main__":
    main()
