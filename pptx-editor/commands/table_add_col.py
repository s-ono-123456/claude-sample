"""table-add-col コマンド — 既存テーブルに列を追加する"""
import argparse
from lib.pptx_utils import load_prs, save_prs, cm, get_slide, find_shape


def add_parser(subparsers):
    p = subparsers.add_parser("table-add-col", help="テーブルに列を追加")
    p.add_argument("file", help="pptxファイルパス")
    p.add_argument("--slide", type=int, required=True, help="スライド番号（1始まり）")
    p.add_argument("--shape", required=True, help="テーブルのシェイプ名（部分一致）または0始まりインデックス")
    p.add_argument("--at", type=int, default=None, help="挿入位置（0始まり）。省略時は末尾に追加")
    p.add_argument("--width", type=float, default=None, help="列幅（cm）。省略時は既存列の平均値")
    p.add_argument("--output", default=None, help="出力先（省略時は上書き）")
    p.set_defaults(func=run)


def run(args: argparse.Namespace):
    prs = load_prs(args.file)
    slide = get_slide(prs, args.slide)
    shape = find_shape(slide, args.shape)

    if not shape.has_table:
        raise ValueError(f"シェイプ '{args.shape}' はテーブルではありません")

    table = shape.table
    col_count = len(table.columns)
    row_count = len(table.rows)

    # 列幅を決定（指定なし → 既存列の平均値）
    if args.width is not None:
        col_width = cm(args.width)
    else:
        total_w = sum(c.width for c in table.columns)
        col_width = total_w // col_count if col_count > 0 else cm(3.0)

    from pptx.oxml.ns import qn

    tbl = table._tbl
    tbl_grid = tbl.tblGrid

    # gridCol を末尾に追加してから移動
    tbl_grid.add_gridCol(col_width)

    if args.at is not None:
        insert_at = max(0, min(args.at, col_count))
        grid_cols = tbl_grid.findall(qn("a:gridCol"))
        new_col = grid_cols[-1]
        tbl_grid.remove(new_col)
        if insert_at < len(grid_cols) - 1:
            grid_cols[insert_at].addprevious(new_col)
        else:
            tbl_grid.append(new_col)
        position_msg = f"位置 {insert_at}"
    else:
        insert_at = col_count  # 末尾
        position_msg = "末尾"

    # 各行に新しいセルを追加
    for row in table.rows:
        tr = row._tr
        new_tc = tr.add_tc()
        # 挿入位置が末尾以外の場合はセルを移動
        if args.at is not None and insert_at < col_count:
            tc_elements = tr.findall(qn("a:tc"))
            tr.remove(new_tc)
            if insert_at < len(tc_elements):
                tc_elements[insert_at].addprevious(new_tc)
            else:
                tr.append(new_tc)

    dest = save_prs(prs, args.file, args.output)
    print(f"列追加完了: {dest}  スライド{args.slide}  {position_msg}に追加")
