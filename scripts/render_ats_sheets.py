"""Render the drawing sheets of ASCO wiring diagram 978741 that Hybrid v2 reads, from the local submittal PDF.

  python -m uv run python scripts/render_ats_sheets.py

The vendor PDF is never committed (docs/vendor/ is excluded from git) and neither are the images. Privacy rule: only
drawing areas are rendered. The submittal cover sheet, the outline and order pages, every title block (bottom right of
each sheet), the wire run list headers and the PDF metadata are never sent to the model: the crops below were checked
by eye to contain only circuit drawing, the TS control contact table and the main harness wire table. Needs PyMuPDF
(not a project dependency: pip install pymupdf).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "docs" / "vendor" / "asco_978741_submittal.pdf"
OUT = ROOT / "docs" / "vendor" / "crops"

# (file name, PDF page, crop as fractions of the page: x0, y0, x1, y1, dpi, what it shows)
SHEETS = [
    ("s3_power.png", 6, (0.00, 0.04, 0.50, 0.93), 150, "sheet 3: main power poles"),
    ("s3_operator.png", 6, (0.49, 0.04, 0.99, 0.62), 400, "sheet 3: TS operator circuit"),
    ("s3_table.png", 6, (0.53, 0.74, 0.73, 0.90), 300, "sheet 3: TS control (cut-off) contact table"),
    ("s4_sensing.png", 7, (0.00, 0.04, 0.50, 0.99), 300, "sheet 4: source sensing, load sensing, position contacts"),
    ("s4_position.png", 7, (0.34, 0.745, 0.50, 0.83), 600, "sheet 4: TS position contacts (enlarged)"),
    ("s2_engine.png", 5, (0.00, 0.04, 0.32, 0.55), 350, "sheet 2: engine starting signals and TS auxiliary contacts"),
    ("s6_wires.png", 9, (0.05, 0.10, 0.165, 0.38), 450, "sheet 6: main harness wire run listing (table body)"),
]


def main() -> None:
    try:
        import pymupdf
    except ImportError:
        sys.exit("needs PyMuPDF: pip install pymupdf")
    if not PDF.exists():
        sys.exit(f"missing {PDF} (the vendor PDF stays local)")
    OUT.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(PDF)
    for name, page_no, (x0, y0, x1, y1), dpi, what in SHEETS:
        page = doc[page_no - 1]
        r = page.rect
        clip = pymupdf.Rect(r.x0 + x0 * r.width, r.y0 + y0 * r.height, r.x0 + x1 * r.width, r.y0 + y1 * r.height)
        page.get_pixmap(dpi=dpi, clip=clip).save(OUT / name)  # pixels only: no PDF metadata goes into a PNG
        print(f"{name}: {what}")


if __name__ == "__main__":
    main()
