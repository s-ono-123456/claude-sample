"""inspect コマンド — スライド構造を表示する"""
import argparse
from lib.pptx_utils import load_prs, emu_to_cm

SHAPE_TYPE_NAMES = {
    1: "AUTO_SHAPE", 6: "GROUP", 9: "LINE", 13: "PICTURE",
    14: "PLACEHOLDER", 17: "TEXT_BOX", 19: "TABLE",
}


def add_parser(subparsers):
    p = subparsers.add_parser("inspect", help="スライド構造を表示")
    p.add_argument("file", help="pptxファイルパス")
    p.add_argument("--slide", type=int, default=None, help="スライド番号（省略時は全スライド）")
    p.set_defaults(func=run)


def run(args: argparse.Namespace):
    prs = load_prs(args.file)
    target = range(len(prs.slides)) if args.slide is None else [args.slide - 1]

    print(f"ファイル: {args.file}")
    print(f"スライド数: {len(prs.slides)}")
    print(f"サイズ: {emu_to_cm(prs.slide_width):.1f} x {emu_to_cm(prs.slide_height):.1f} cm")

    for idx in target:
        slide = prs.slides[idx]
        layout_name = slide.slide_layout.name
        print(f"\n=== スライド {idx + 1} / レイアウト: {layout_name} ===")
        for i, shape in enumerate(slide.shapes):
            stype = SHAPE_TYPE_NAMES.get(shape.shape_type, str(shape.shape_type))
            left = emu_to_cm(shape.left or 0)
            top = emu_to_cm(shape.top or 0)
            w = emu_to_cm(shape.width or 0)
            h = emu_to_cm(shape.height or 0)
            print(f"  [{i}] {stype:12s} name={shape.name!r:30s} "
                  f"pos=({left:.1f},{top:.1f})cm  size={w:.1f}x{h:.1f}cm")
            if shape.has_text_frame:
                text = shape.text_frame.text[:80].replace("\n", "\\n")
                print(f"       text: {text!r}")
