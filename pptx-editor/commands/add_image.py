"""add-image コマンド — PNG または SVG 画像をスライドに配置する"""
import argparse
from pathlib import Path
from lib.pptx_utils import load_prs, save_prs, cm, get_slide
from lib.svg_embed import add_svg_picture


def add_parser(subparsers):
    p = subparsers.add_parser("add-image", help="画像（PNG/SVG）を配置")
    p.add_argument("file", help="pptxファイルパス")
    p.add_argument("--slide", type=int, required=True, help="スライド番号（1始まり）")
    p.add_argument("--image", required=True, help="画像ファイルパス（PNG または SVG）")
    p.add_argument("--left", type=float, required=True, help="左端位置（cm）")
    p.add_argument("--top", type=float, required=True, help="上端位置（cm）")
    p.add_argument("--width", type=float, required=True, help="幅（cm）")
    p.add_argument("--height", type=float, required=True, help="高さ（cm）")
    p.add_argument("--output", default=None, help="出力先（省略時は上書き）")
    p.set_defaults(func=run)


def run(args: argparse.Namespace):
    prs = load_prs(args.file)
    slide = get_slide(prs, args.slide)
    img_path = Path(args.image).resolve()

    if not img_path.exists():
        raise FileNotFoundError(f"画像ファイルが見つかりません: {img_path}")

    left, top, width, height = cm(args.left), cm(args.top), cm(args.width), cm(args.height)

    if img_path.suffix.lower() == ".svg":
        add_svg_picture(slide, str(img_path), left, top, width, height)
    else:
        slide.shapes.add_picture(str(img_path), left, top, width, height)

    dest = save_prs(prs, args.file, args.output)
    print(f"画像配置完了: {dest}  スライド{args.slide}  画像: {img_path.name}")
