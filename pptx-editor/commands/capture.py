"""capture コマンド — soffice PDF変換 + PyMuPDF でスライドをPNG化する"""
import argparse
import subprocess
import tempfile
from pathlib import Path

SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"


def add_parser(subparsers):
    p = subparsers.add_parser("capture", help="スライドをPNG画像として出力")
    p.add_argument("file", help="pptxファイルパス")
    p.add_argument("--slide", type=int, required=True, help="スライド番号（1始まり）")
    p.add_argument("--output", required=True, help="出力PNGファイルパス")
    p.add_argument("--dpi", type=int, default=150, help="解像度DPI（デフォルト: 150）")
    p.set_defaults(func=run)


def run(args: argparse.Namespace):
    import fitz  # PyMuPDF

    src = Path(args.file).resolve()
    out = Path(args.output).resolve()
    slide_idx = args.slide - 1

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Step1: pptx → PDF（soffice）
        result = subprocess.run(
            [SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", str(tmp_path), str(src)],
            capture_output=True, timeout=60
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("mbcs", errors="replace")
            raise RuntimeError(f"PDF変換エラー:\n{stderr}")

        pdfs = list(tmp_path.glob("*.pdf"))
        if not pdfs:
            raise RuntimeError("LibreOfficeがPDFを生成しませんでした")

        # Step2: PDF の指定ページ → PNG（PyMuPDF）
        doc = fitz.open(str(pdfs[0]))
        total = doc.page_count
        if slide_idx < 0 or slide_idx >= total:
            raise ValueError(f"スライド {args.slide} は存在しません（全{total}枚）")

        page = doc[slide_idx]
        mat = fitz.Matrix(args.dpi / 72, args.dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        doc.close()

        out.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(out))

    print(f"キャプチャ完了: {out}  （スライド{args.slide}、{args.dpi}dpi）")
