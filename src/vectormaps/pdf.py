"""The SVG as a PDF of the same paper size, through Inkscape (ADR 0007).

Inkscape draws everything the SVG uses: text along paths (`textPath`), the label
halos (`paint-order`) and the opacity of a stacked zone. The page is the SVG's
width and height in mm, so the PDF comes out at the paper size.
"""

import subprocess
from pathlib import Path


def svg_to_pdf(svg: Path, pdf: Path) -> Path:
    tmp = pdf.with_name(pdf.stem + ".tmp.pdf")  # Inkscape wants the .pdf ending
    cmd = [
        "inkscape",
        str(svg),
        "--export-type=pdf",
        "--export-area-page",
        f"--export-filename={tmp}",
    ]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"inkscape could not write the PDF: {done.stderr.strip()[-500:]}")
    tmp.replace(pdf)
    return pdf
