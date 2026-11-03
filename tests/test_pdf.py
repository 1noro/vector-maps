import re

import pytest

from vectormaps.pdf import svg_to_pdf

MM_TO_PT = 72 / 25.4

# A5 landscape with what a map uses: text along a path and a halo behind it.
SVG = """<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
 width="210mm" height="148mm" viewBox="0 0 210 148">
<rect width="210" height="148" fill="#f5f2ec"/>
<defs><path id="p" d="M20 70 L190 80"/></defs>
<text font-size="6" fill="#111" stroke="#fff" stroke-width="1" paint-order="stroke">
<textPath xlink:href="#p" startOffset="50%" text-anchor="middle">Rúa do Vilar</textPath></text>
</svg>"""


def test_pdf_has_the_paper_size(tmp_path):
    svg = tmp_path / "map.svg"
    svg.write_text(SVG, encoding="utf-8")
    pdf = svg_to_pdf(svg, tmp_path / "map.pdf")
    data = pdf.read_bytes()
    assert data.startswith(b"%PDF")
    box = re.search(rb"/MediaBox \[\s*0 0 ([\d.]+) ([\d.]+)\s*\]", data)
    assert box, "no MediaBox in the PDF"
    w, h = (float(v) for v in box.groups())
    assert (w, h) == pytest.approx((210 * MM_TO_PT, 148 * MM_TO_PT), abs=0.5)
    assert not list(tmp_path.glob("*.tmp.pdf"))


def test_a_broken_svg_is_an_error(tmp_path):
    svg = tmp_path / "bad.svg"
    svg.write_text("not an svg", encoding="utf-8")
    with pytest.raises(RuntimeError, match="inkscape"):
        svg_to_pdf(svg, tmp_path / "bad.pdf")
    assert not (tmp_path / "bad.pdf").exists()
