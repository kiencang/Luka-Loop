"""Score the extractor on dev/header-pdf against truth.json (written by the generator).

Per extracted image: 'header' if it contains >= 50% of a running head / folio box (the error we target).
Per figure: 'missed' if no image covers its centre, 'cut' if its inked area (white page render inside the
placement box, ignoring the loose white box) reaches > 2 pt outside the covering image.
"""
import contextlib, io, json, shutil, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]  # repo root (this file: dev/header-pdf/tools/)
sys.path.insert(0, str(REPO / "tools" / "src"))
import pymupdf
from figure_detector.extract import extract_images

SRC = REPO / "dev" / "header-pdf"
OUT = Path(sys.argv[1])
if OUT.exists():
    shutil.rmtree(OUT)
truth = json.loads((SRC / "truth.json").read_text(encoding="utf-8"))


def ink_points(page, rect):
    """Page-space points of dark pixels of the figure body (2 px/pt render, every 2nd pixel)."""
    pix = page.get_pixmap(clip=rect, matrix=pymupdf.Matrix(2, 2), colorspace=pymupdf.csGRAY, alpha=False)
    s, w, h = pix.samples, pix.width, pix.height
    pts = []
    for yy in range(0, h, 2):
        row = s[yy * w:(yy + 1) * w]
        for xx in range(0, w, 2):
            if row[xx] < 200:
                pts.append((rect.x0 + xx / 2, rect.y0 + yy / 2))
    return pts


report, tot = {}, {"images": 0, "header": 0, "figures": 0, "missed": 0, "cut": 0}
for name, t in truth.items():
    od = OUT / Path(name).stem
    with contextlib.redirect_stdout(io.StringIO()):
        extract_images(SRC / name, od, dpi=150, write_meta=True)
    meta = json.loads((od / "manifest.json").read_text(encoding="utf-8"))
    doc = pymupdf.open(SRC / name)
    items, figs = [], []
    for f in meta["figures"]:
        pr = doc[f["page"] - 1].rect
        b = f["box"]
        img = pymupdf.Rect(b[0] * pr.width - 4, b[1] * pr.height - 4, b[2] * pr.width + 4, b[3] * pr.height + 4)
        run = t["truth"].get(str(f["page"]), {}).get("running", [])
        hits = [r["text"] for r in run if (pymupdf.Rect(r["rect"]) & img).get_area() >= 0.5 * pymupdf.Rect(r["rect"]).get_area()]
        items.append({"file": f["file"], "page": f["page"], "img": [round(v, 1) for v in img], "header_hits": hits})
    for pno, pt in t["truth"].items():
        page = doc[int(pno) - 1]
        imgs = [pymupdf.Rect(i["img"]) for i in items if i["page"] == int(pno)]
        for fg in pt["figures"]:
            pl = pymupdf.Rect(fg["placement"])
            body = pymupdf.Rect(pl.x0, pl.y0 + fg["loose_top"], pl.x1, pl.y1)
            pts = ink_points(page, body)
            grown = [im + (-1.5, -1.5, 1.5, 1.5) for im in imgs]
            outside = [p for p in pts if not any(g.x0 <= p[0] <= g.x1 and g.y0 <= p[1] <= g.y1 for g in grown)]
            share = len(outside) / max(1, len(pts))
            status = "missed" if share > 0.5 else ("cut" if share > 0.004 and len(outside) >= 6 else "ok")
            figs.append({"page": int(pno), "no": fg["no"], "kind": fg["kind"], "control": fg["control"],
                         "loose_top": fg["loose_top"], "raster": fg["raster"], "status": status,
                         "outside_share": round(share, 4), "outside_sample": [[round(a, 1), round(b, 1)] for a, b in outside[:5]]})
    nh = sum(bool(i["header_hits"]) for i in items)
    report[name] = {"items": items, "figures": figs}
    tot["images"] += len(items); tot["header"] += nh; tot["figures"] += len(figs)
    tot["missed"] += sum(f["status"] == "missed" for f in figs); tot["cut"] += sum(f["status"] == "cut" for f in figs)
    print(f"{name:34} images {len(items)}  header {nh}  | figures {len(figs)}: "
          + " ".join(f"p{f['page']}:{f['status']}{'(ctrl)' if f['control'] else ''}" for f in figs)
          + " | hits: " + "; ".join(f"p{i['page']}:{'+'.join(i['header_hits'])}" for i in items if i["header_hits"]))
print("TOTAL", tot)
(OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
