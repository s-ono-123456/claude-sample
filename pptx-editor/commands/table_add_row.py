"""table-add-row コマンド — 既存テーブルに行を追加する"""
import argparse
from pptx.util import Emu
from lib.pptx_utils import load_prs, save_prs, cm, get_slide, find_shape


def add_parser(subparsers):
    p = subparsers.add_parser("table-add-row", help="テーブルに行を追加")
    p.add_argument("file", help="pptxファイルパス")
    p.add_argument("--slide", type=int, required=True, help="スライド番号（1始まり）")
    p.add_argument("--shape", required=True, help="テーブルのシェイプ名（部分一致）または0始まりインデックス")
    p.add_argument("--at", type=int, default=None, help="挿入位置（0始まり）。省略時は末尾に追加")
    p.add_argument("--height", type=float, default=None, help="行の高さ（cm）。省略時は既存行の平均値")
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

    # 行の高さを決定（指定なし → 既存行の平均値）
    if args.height is not None:
        row_height = cm(args.height)
    else:
        total_h = sum(r.height for r in table.rows)
        row_height = total_h // row_count if row_count > 0 else cm(1.0)

    tbl = table._tbl

    # 新しい行XMLを生成（末尾に追加してから移動）
    new_tr = tbl.add_tr(row_height)
    for _ in range(col_count):
        new_tr.add_tc()

    # 挿入位置が指定された場合、末尾から目的の位置へ移動
    if args.at is not None:
        insert_at = max(0, min(args.at, row_count))
        # tbl の子要素のうち a:tr タグのリストを取得して並び替え
        from pptx.oxml.ns import qn
        tr_elements = tbl.findall(qn("a:tr"))
        # new_tr は末尾にある。insert_at の前に移動させる
        tbl.remove(new_tr)
        if insert_at < len(tr_elements):
            tr_elements[insert_at].addprevious(new_tr)
        else:
            tbl.append(new_tr)
        position_msg = f"位置 {insert_at}"
    else:
        position_msg = "末尾"

    dest = save_prs(prs, args.file, args.output)
    print(f"行追加完了: {dest}  スライド{args.slide}  {position_msg}に追加")
