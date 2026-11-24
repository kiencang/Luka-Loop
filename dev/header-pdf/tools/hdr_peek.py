"""Render chosen pages (top part or full) with the extracted image boxes: red = contains running head."""
import json, sys
from pathlib import Path
import pymupdf

SRC = Path(__file__).resolve().parents[1]  # dev/header-pdf
RUN = Path(sys.argv[1]); out = Path(sys.argv[2]); frac = float(sys.argv[3])
rep = json.loads((RUN / "report.json").read_text(encoding="utf-8"))
sel = [(a.split("@")[0], int(a.split("@")[1])) for a in sys.argv[4:]]
outdoc = pymupdf.open()
for name, p in sel:
    full = next(n for n in rep if n.startswith(name))
    d = pymupdf.open(SRC / full); pg = d[p - 1]
    clip = pymupdf.Rect(0, 0, pg.rect.width, pg.rect.height * frac)
    op = outdoc.new_page(width=clip.width, height=clip.height)
    op.show_pdf_page(op.rect, d, p - 1, clip=clip)
    for i in rep[full]["items"]:
        if i["page"] == p:
            op.draw_rect(pymupdf.Rect(i["img"]), color=(0.9, 0.05, 0.05) if i["header_hits"] else (0.1, 0.35, 0.95), width=1.6)
    op.insert_text((4, 10), f"{full} p{p}", fontsize=7, color=(0.8, 0, 0.6))
for k, pg in enumerate(outdoc):
    pg.get_pixmap(matrix=pymupdf.Matrix(1.25, 1.25)).save(f"{out}_{k}.png")
