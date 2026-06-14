"""edit-text コマンド — 既存シェイプのテキストを書き換える"""
import argparse
from lib.pptx_utils import load_prs, save_prs, get_slide, find_shape


def add_parser(subparsers):
    p = subparsers.add_parser("edit-text", help="既存シェイプのテキストを修正")
    p.add_argument("file", help="pptxファイルパス")
    p.add_argument("--slide", type=int, required=True, help="スライド番号（1始まり）")
    p.add_argument("--shape", required=True, help="シェイプ名（部分一致）またはインデックス（0始まり）")
    p.add_argument("--text", required=True, help="新しいテキスト内容")
    p.add_argument("--output", default=None, help="出力先（省略時は上書き）")
    p.set_defaults(func=run)


def run(args: argparse.Namespace):
    prs = load_prs(args.file)
    slide = get_slide(prs, args.slide)
    shape = find_shape(slide, args.shape)

    if not shape.has_text_frame:
        raise ValueError(f"シェイプ '{shape.name}' にテキストフレームがありません")

    tf = shape.text_frame
    if tf.paragraphs:
        para = tf.paragraphs[0]
        if para.runs:
            para.runs[0].text = args.text
            for r in para.runs[1:]:
                r.text = ""
        else:
            run_ = para.add_run()
            run_.text = args.text
        for p in tf.paragraphs[1:]:
            for r in p.runs:
                r.text = ""
    else:
        tf.text = args.text

    dest = save_prs(prs, args.file, args.output)
    print(f"テキスト修正完了: {dest}  スライド{args.slide}  シェイプ: {shape.name!r}")
