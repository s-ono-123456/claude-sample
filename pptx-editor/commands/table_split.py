"""table-split コマンド — テーブルのセル結合を解除する"""
import argparse
from lib.pptx_utils import load_prs, save_prs, get_slide, find_shape


def add_parser(subparsers):
    p = subparsers.add_parser("table-split", help="テーブルのセル結合を解除")
    p.add_argument("file", help="pptxファイルパス")
    p.add_argument("--slide", type=int, required=True, help="スライド番号（1始まり）")
    p.add_argument("--shape", required=True, help="テーブルのシェイプ名（部分一致）または0始まりインデックス")
    p.add_argument("--row", type=int, required=True, help="解除するセルの行（0始まり）")
    p.add_argument("--col", type=int, required=True, help="解除するセルの列（0始まり）")
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

    if args.row < 0 or args.row >= rows:
        raise ValueError(f"--row {args.row} が範囲外です（0〜{rows - 1}）")
    if args.col < 0 or args.col >= cols:
        raise ValueError(f"--col {args.col} が範囲外です（0〜{cols - 1}）")

    cell = table.cell(args.row, args.col)

    if not cell.is_merge_origin:
        raise ValueError(
            f"セル ({args.row},{args.col}) は結合元ではありません。"
            "結合元セル（左上のセル）を指定してください"
        )

    cell.split()

    dest = save_prs(prs, args.file, args.output)
    print(f"セル結合解除完了: {dest}  スライド{args.slide}  ({args.row},{args.col})")
