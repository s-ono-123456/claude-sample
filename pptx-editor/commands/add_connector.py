"""add-connector コマンド — 線・矢印をスライドに配置する"""
import argparse
from pptx.util import Pt, Emu
from pptx.oxml.ns import qn
from lxml import etree
from lib.pptx_utils import load_prs, save_prs, cm, get_slide, parse_color

_CONNECTOR_MAP = {"straight": 1, "elbow": 2, "curved": 3}


def add_parser(subparsers):
    p = subparsers.add_parser("add-connector", help="線・矢印を配置")
    p.add_argument("file", help="pptxファイルパス")
    p.add_argument("--slide", type=int, required=True, help="スライド番号（1始まり）")
    p.add_argument("--start-x", type=float, required=True, help="始点X（cm）")
    p.add_argument("--start-y", type=float, required=True, help="始点Y（cm）")
    p.add_argument("--end-x", type=float, required=True, help="終点X（cm）")
    p.add_argument("--end-y", type=float, required=True, help="終点Y（cm）")
    p.add_argument("--arrow", choices=["none", "start", "end", "both"], default="end",
                   help="矢印の向き（デフォルト: end）")
    p.add_argument("--connector-type", choices=list(_CONNECTOR_MAP.keys()), default="straight",
                   help="コネクタの種類")
    p.add_argument("--color", default=None, help="線の色 (#RRGGBB)")
    p.add_argument("--line-width", type=float, default=1.0, help="線幅 (pt)")
    p.add_argument("--output", default=None, help="出力先（省略時は上書き）")
    p.set_defaults(func=run)


def _set_arrow_head(line_elem, position: str):
    """始点/終点に矢印を設定する (position: 'headEnd' or 'tailEnd')"""
    arrow = etree.SubElement(line_elem, qn(f"a:{position}"))
    arrow.set("type", "arrow")
    arrow.set("w", "med")
    arrow.set("len", "med")


def run(args: argparse.Namespace):
    prs = load_prs(args.file)
    slide = get_slide(prs, args.slide)

    sx, sy = cm(args.start_x), cm(args.start_y)
    ex, ey = cm(args.end_x), cm(args.end_y)

    connector_type_id = _CONNECTOR_MAP[args.connector_type]
    connector = slide.shapes.add_connector(connector_type_id, sx, sy, ex, ey)

    line = connector.line
    if args.color:
        line.color.rgb = parse_color(args.color)
    line.width = Pt(args.line_width)

    ln = connector._element.find(".//" + qn("a:ln"))
    if ln is not None:
        if args.arrow in ("start", "both"):
            _set_arrow_head(ln, "headEnd")
        if args.arrow in ("end", "both"):
            _set_arrow_head(ln, "tailEnd")

    dest = save_prs(prs, args.file, args.output)
    print(f"矢印追加完了: {dest}  スライド{args.slide}  ({args.start_x},{args.start_y})→({args.end_x},{args.end_y})")
