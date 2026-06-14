"""pptx-editor CLI エントリポイント"""
import argparse
import sys
from pathlib import Path

# スクリプトとして直接実行される場合に pptx-editor/ を sys.path に追加
sys.path.insert(0, str(Path(__file__).parent))

from commands import (
    inspect, capture, add_text, edit_text, add_image, add_shape, add_connector,
    add_table, edit_table, table_add_row, table_add_col, table_merge, table_split,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pptx-editor",
        description="PowerPoint ファイルをコマンドラインで操作するツール",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    subparsers.required = True

    inspect.add_parser(subparsers)
    capture.add_parser(subparsers)
    add_text.add_parser(subparsers)
    edit_text.add_parser(subparsers)
    add_image.add_parser(subparsers)
    add_shape.add_parser(subparsers)
    add_connector.add_parser(subparsers)
    add_table.add_parser(subparsers)
    edit_table.add_parser(subparsers)
    table_add_row.add_parser(subparsers)
    table_add_col.add_parser(subparsers)
    table_merge.add_parser(subparsers)
    table_split.add_parser(subparsers)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
