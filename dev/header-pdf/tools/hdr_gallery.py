"""Review page: every page of dev/header-pdf with the extracted image boxes, plus the crops themselves (PNG folder)."""
import base64
import html
import json
import sys
from pathlib import Path
import pymupdf

REPO = Path(__file__).resolve().parents[3]  # repo root (this file: dev/header-pdf/tools/)
RUN = Path(sys.argv[1])
report = json.loads((RUN / "report.json").read_text(encoding="utf-8"))


def b64(data):
    return "data:image/png;base64," + base64.b64encode(data).decode()


cards = []
for name, rep in report.items():
    doc = pymupdf.open(REPO / "dev" / "header-pdf" / name)
    for pno, page in enumerate(doc, 1):
        figs = [i for i in rep["items"] if i["page"] == pno]
        if not figs:
            continue
        view = pymupdf.open()
        vp = view.new_page(width=page.rect.width, height=page.rect.height)
        vp.show_pdf_page(vp.rect, doc, pno - 1)
        for i in figs:
            r = pymupdf.Rect(i["img"])
            sh = vp.new_shape()
            sh.draw_rect(r)
            sh.finish(color=(0.9, 0.05, 0.05) if i["header_hits"] else (0.1, 0.35, 0.95), width=2)
            sh.commit()
        pv = b64(vp.get_pixmap(matrix=pymupdf.Matrix(0.75, 0.75)).tobytes("png"))
        crops = "".join(
            f"<figure><img src='{b64((RUN / Path(name).stem / i['file']).read_bytes())}'><figcaption>{i['file']}"
            f"{' — ' + html.escape('; '.join(i['header_hits'])) if i['header_hits'] else ''}</figcaption></figure>" for i in figs)
        st = [f for f in rep["figures"] if f["page"] == pno]
        tag = " ".join(("cắt hụt" if f["status"] == "cut" else "bỏ sót" if f["status"] == "missed" else "hình đủ") + (" (trang đối chứng)" if f["control"] else "") for f in st)
        bad = any(i["header_hits"] for i in figs)
        cards.append(f"<section class='{'bad' if bad else ''}'><h2>{html.escape(name)} · trang {pno} · {'DÍNH tiêu đề/số trang' if bad else 'sạch'} · {tag}</h2><div class='row'><img class='pg' src='{pv}'>"
                     f"<div class='crops'>{crops}</div></div></section>")
page = f"""<!doctype html><html lang='vi'><head><meta charset='utf-8'><title>Header test: v1.1.22</title><style>
body{{font-family:system-ui,sans-serif;margin:16px;background:#f5f5f3}} section.bad{{border-left:6px solid #d22}} section{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:10px;margin-bottom:14px}}
h2{{font-size:16px;margin:0 0 8px}} .row{{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start}} .pg{{width:420px;max-width:100%;border:1px solid #bbb}}
.crops{{display:flex;flex-direction:column;gap:10px;flex:1;min-width:280px}} .crops img{{max-width:100%;max-height:420px;border:1px solid #888}} figcaption{{font-size:13px;color:#444}}</style></head><body>
<h1>Bộ đề 10 tệp header-pdf · kết quả v1.1.22 (baseline)</h1><p>Tổng: 42 ảnh, 18 ảnh dính tiêu đề chạy/số trang; 40 hình, 0 bỏ sót, 7 cắt hụt (nhóm lỗi khác, không thuộc đợt này).</p><p>Khung xanh dương = ảnh công cụ cắt ra (đỏ nếu máy phát hiện dính tiêu đề/số trang). Bên phải là đúng ảnh xuất ra.</p>
{''.join(cards)}</body></html>"""
(Path(sys.argv[2])).write_text(page, encoding="utf-8")
print(len(cards), "pages with figures")
