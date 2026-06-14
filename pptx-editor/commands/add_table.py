"""add-table コマンド — 新規テーブルをスライドに追加する"""
import argparse
from pptx.util import Pt
from lib.pptx_utils import load_prs, save_prs, cm, get_slide, parse_color


def add_parser(subparsers):
    p = subparsers.add_parser("add-table", help="テーブルを新規作成して配置")
    p.add_argument("file", help="pptxファイルパス")
    p.add_argument("--slide", type=int, required=True, help="スライド番号（1始まり）")
    p.add_argument("--rows", type=int, required=True, help="行数")
    p.add_argument("--cols", type=int, required=True, help="列数")
    p.add_argument("--left", type=float, required=True, help="左端位置（cm）")
    p.add_argument("--top", type=float, required=True, help="上端位置（cm）")
    p.add_argument("--width", type=float, required=True, help="幅（cm）")
    p.add_argument("--height", type=float, required=True, help="高さ（cm）")
    p.add_argument("--data", default=None,
                   help='データ。行は";"区切り、セルは","区切り。例: "A,B;1,2"')
    p.add_argument("--col-widths", default=None,
                   help="各列の幅（cm）をカンマ区切りで指定。例: \"5,8,7\"")
    p.add_argument("--row-heights", default=None,
                   help="各行の高さ（cm）をカンマ区切りで指定。例: \"1.5,1,1\"")
    p.add_argument("--header", action="store_true", help="先頭行をヘッダー行として強調")
    p.add_argument("--header-fill", default=None, help="ヘッダー行の背景色 (#RRGGBB)")
    p.add_argument("--output", default=None, help="出力先（省略時は上書き）")
    p.set_defaults(func=run)


def _parse_data(data_str: str, rows: int, cols: int) -> list[list[str]]:
    """";A,B;C,D" 形式を [[row], ...] に変換。不足セルは空文字で補完"""
    result = []
    for row_str in data_str.split(";"):
        cells = row_str.split(",")
        # 列数に合わせてパディング
        cells = (cells + [""] * cols)[:cols]
        result.append(cells)
    # 行数に合わせてパディング
    while len(result) < rows:
        result.append([""] * cols)
    return result[:rows]


def run(args: argparse.Namespace):
    prs = load_prs(args.file)
    slide = get_slide(prs, args.slide)

    gf = slide.shapes.add_table(
        args.rows, args.cols,
        cm(args.left), cm(args.top), cm(args.width), cm(args.height)
    )
    table = gf.table

    # ヘッダー強調
    if args.header:
        table.first_row = True

    # 列幅設定
    if args.col_widths:
        widths = [float(w.strip()) for w in args.col_widths.split(",")]
        for i, w in enumerate(widths[:args.cols]):
            table.columns[i].width = cm(w)

    # 行高設定
    if args.row_heights:
        heights = [float(h.strip()) for h in args.row_heights.split(",")]
        for i, h in enumerate(heights[:args.rows]):
            table.rows[i].height = cm(h)

    # データ入力
    if args.data:
        grid = _parse_data(args.data, args.rows, args.cols)
        for r, row_data in enumerate(grid):
            for c, text in enumerate(row_data):
                table.cell(r, c).text = text

    # ヘッダー行の背景色
    if args.header and args.header_fill:
        color = parse_color(args.header_fill)
        for c in range(args.cols):
            cell = table.cell(0, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = color

    dest = save_prs(prs, args.file, args.output)
    print(f"テーブル追加完了: {dest}  スライド{args.slide}  {args.rows}行×{args.cols}列")
