"""SVG を Microsoft 365 対応形式で pptx に埋め込むユーティリティ"""
import base64
import subprocess
import tempfile
from pathlib import Path
from lxml import etree
from pptx.util import Emu
from pptx.oxml.ns import qn, nsmap

SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"

# Microsoft 365 の SVG 拡張に使う URI
_SVG_URI = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
_A14_URI = "http://schemas.microsoft.com/office/drawing/2010/main"


def _svg_to_png_bytes(svg_path: Path) -> bytes:
    """LibreOffice で SVG → PNG に変換してバイト列で返す"""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [SOFFICE, "--headless", "--convert-to", "png", "--outdir", tmpdir, str(svg_path)],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"SVG→PNG変換失敗: {result.stderr.decode()}")
        pngs = list(Path(tmpdir).glob("*.png"))
        if not pngs:
            raise RuntimeError("LibreOfficeがPNGを生成しませんでした")
        return pngs[0].read_bytes()


def add_svg_picture(slide, svg_path: str, left: Emu, top: Emu, width: Emu, height: Emu):
    """
    SVG を Microsoft 365 向けの svgBlip 拡張付き Picture としてスライドに追加する。
    フォールバック用PNG も同時に埋め込むので旧環境でも表示可能。
    """
    svg_file = Path(svg_path).resolve()
    if not svg_file.exists():
        raise FileNotFoundError(f"SVGファイルが見つかりません: {svg_file}")

    svg_bytes = svg_file.read_bytes()
    png_bytes = _svg_to_png_bytes(svg_file)

    # フォールバック PNG を picture として追加
    import io
    from pptx.util import Emu as _Emu
    pic_shape = slide.shapes.add_picture(io.BytesIO(png_bytes), left, top, width, height)

    # pic の XML を取得して svgBlip 拡張を注入
    pic_elem = pic_shape._element
    blipFill = pic_elem.find(qn("p:blipFill"))
    if blipFill is None:
        return pic_shape

    blip = blipFill.find(qn("a:blip"))
    if blip is None:
        return pic_shape

    # SVG データを Part として追加して rId を取得
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    from pptx.opc.part import Part

    svg_part = Part(
        partname=f"/ppt/media/{svg_file.stem}_{id(pic_shape)}.svg",
        content_type="image/svg+xml",
        blob=svg_bytes,
    )
    slide.part.relate_to(svg_part, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image")
    rId = slide.part.relate_to(svg_part, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image")

    # a:extLst > a:ext (svgBlip)
    extLst = blip.find(qn("a:extLst"))
    if extLst is None:
        extLst = etree.SubElement(blip, qn("a:extLst"))

    ext = etree.SubElement(extLst, qn("a:ext"))
    ext.set("uri", "{96DAC541-7B7A-43D3-8B79-37D633B846F1}")

    svgBlip = etree.SubElement(ext, f"{{{_SVG_URI}}}svgBlip")
    svgBlip.set(
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed",
        rId,
    )

    return pic_shape
