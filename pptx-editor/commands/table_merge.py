"""table-merge コマンド — テーブルのセルを結合する"""
import argparse
from lib.pptx_utils import load_prs, save_prs, get_slide, find_shape


def add_parser(subparsers):
    p = subparsers.add_parser("table-merge", help="テーブルのセルを結合")
    p.add_argument("file", help="pptxファイルパス")
    p.add_argument("--slide", type=int, required=True, help="スライド番号（1始まり）")
    p.add_argument("--shape", required=True, help="テーブルのシェイプ名（部分一致）または0始まりインデックス")
    p.add_argument("--from-row", type=int, required=True, help="結合範囲の開始行（0始まり）")
    p.add_argument("--from-col", type=int, required=True, help="結合範囲の開始列（0始まり）")
    p.add_argument("--to-row", type=int, required=True, help="結合範囲の終了行（0始まり）")
    p.add_argument("--to-col", type=int, required=True, help="結合範囲の終了列（0始まり）")
    p.add_argument("--output", default=None, help="出力先（省略時は上書き）")
    p.set_defaults(func=run)


def run(args: argparse.Namespace):
    prs = load_prs(args.file)
    slide = get_slide(prs, args.slide)
    shape = find_shape(slide, args.shape)

    if not shape.has_table:
        raise ValueError(f"シェイプ '{args.shape}' はテーブルではありません")

    table = shape.table
    rows = len(table.rows)
    cols = len(table.columns)

    for r, label in [(args.from_row, "from-row"), (args.to_row, "to-row")]:
        if r < 0 or r >= rows:
            raise ValueError(f"--{label} {r} が範囲外です（0〜{rows - 1}）")
    for c, label in [(args.from_col, "from-col"), (args.to_col, "to-col")]:
        if c < 0 or c >= cols:
            raise ValueError(f"--{label} {c} が範囲外です（0〜{cols - 1}）")

    if args.from_row > args.to_row or args.from_col > args.to_col:
        raise ValueError("from-row/col は to-row/col 以下でなければなりません")

    table.cell(args.from_row, args.from_col).merge(table.cell(args.to_row, args.to_col))

    dest = save_prs(prs, args.file, args.output)
    print(
        f"セル結合完了: {dest}  スライド{args.slide}  "
        f"({args.from_row},{args.from_col})〜({args.to_row},{args.to_col})"
    )
