"""add-shape コマンド — 図形をスライドに配置する"""
import argparse
from pptx.util import Pt
from lib.pptx_utils import load_prs, save_prs, cm, get_slide, parse_color

_SHAPE_MAP = {
    "rect": 1,
    "rounded-rect": 5,
    "ellipse": 9,
    "diamond": 4,
    "triangle": 6,
    "parallelogram": 60,
    "hexagon": 10,
    "cloud": 35,
    "cylinder": 22,
    "note": 54,
}


def add_parser(subparsers):
    p = subparsers.add_parser("add-shape", help="図形を配置")
    p.add_argument("file", help="pptxファイルパス")
    p.add_argument("--slide", type=int, required=True, help="スライド番号（1始まり）")
    p.add_argument("--type", dest="shape_type", default="rect",
                   choices=list(_SHAPE_MAP.keys()), help="図形の種類")
    p.add_argument("--left", type=float, required=True, help="左端位置（cm）")
    p.add_argument("--top", type=float, required=True, help="上端位置（cm）")
    p.add_argument("--width", type=float, required=True, help="幅（cm）")
    p.add_argument("--height", type=float, required=True, help="高さ（cm）")
    p.add_argument("--fill", default=None, help="塗り色 (#RRGGBB)、省略時はテーマ色")
    p.add_argument("--line-color", default=None, help="枠線色 (#RRGGBB)、省略時はテーマ色")
    p.add_argument("--line-width", type=float, default=None, help="枠線幅 (pt)")
    p.add_argument("--no-fill", action="store_true", help="塗りなし")
    p.add_argument("--no-line", action="store_true", help="枠線なし")
    p.add_argument("--text", default=None, help="図形内テキスト")
    p.add_argument("--output", default=None, help="出力先（省略時は上書き）")
    p.set_defaults(func=run)


def run(args: argparse.Namespace):
    prs = load_prs(args.file)
    slide = get_slide(prs, args.slide)

    shape_id = _SHAPE_MAP[args.shape_type]
    shape = slide.shapes.add_shape(
        shape_id,
        cm(args.left), cm(args.top), cm(args.width), cm(args.height)
    )

    fill = shape.fill
    if args.no_fill:
        fill.background()
    elif args.fill:
        fill.solid()
        fill.fore_color.rgb = parse_color(args.fill)

    line = shape.line
    if args.no_line:
        line.fill.background()
    else:
        if args.line_color:
            line.color.rgb = parse_color(args.line_color)
        if args.line_width is not None:
            line.width = Pt(args.line_width)

    if args.text:
        shape.text = args.text

    dest = save_prs(prs, args.file, args.output)
    print(f"図形追加完了: {dest}  スライド{args.slide}  種類: {args.shape_type}")
