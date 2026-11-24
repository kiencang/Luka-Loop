"""Generate 10 realistic 5-page scientific PDFs that exercise running-header / page-number intrusion.

Layouts copy real typesetting habits seen in the DocLayNet failures:
  * floats at the top of a column/page right below the running head (LaTeX puts top floats there);
  * figures exported with a loose white bounding box (EPS/PDF with whitespace), so the figure's placement box
    reaches up into the running-head band;
  * a page number set on its own at the outer top corner;
  * book / thesis layouts with a deep top margin, so the running head sits lower than 10% of the page height,
    often with a rule under it;
  * floats at the bottom of the page right above a centred folio (footer).
Every file also has control pages: a figure in mid-page, a panel title or top-axis ticks right above the plot area,
so a fix that simply crops the top of every image is caught.
"""
import io
import random
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pymupdf  # noqa: E402

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.linewidth": 0.8, "pdf.fonttype": 42})

SENT = {
    "generic": [
        "The measured response follows the predicted trend over the full range of operating conditions.",
        "Uncertainties were estimated from five independent repetitions of each measurement.",
        "A detailed derivation of the correction terms is given in the supplementary material.",
        "This behaviour is consistent with earlier reports obtained under comparable conditions.",
        "We therefore restrict the analysis to the regime in which the linear approximation holds.",
        "Systematic deviations appear only at the lowest temperatures, where the signal-to-noise ratio drops.",
        "The fitting parameters are listed together with their standard errors in the accompanying table.",
        "Residuals show no significant structure, indicating that the model captures the dominant effects.",
        "All simulations were performed with identical boundary conditions and mesh resolution.",
        "The remaining discrepancy is attributed to finite-size effects in the experimental geometry.",
        "Sensitivity to the choice of hyper-parameters was assessed by a grid search over the main settings.",
        "In contrast to the reference method, the proposed estimator remains unbiased at small sample sizes.",
        "Figure panels share a common colour scale so that the magnitudes can be compared directly.",
        "The calibration was repeated before each session to compensate for slow thermal drift.",
        "These observations motivate the simplified model introduced in the following section.",
    ],
}
TOPICS = [
    ("Thermal transport in layered heterostructures", "temperature (K)", "conductance (nW/K)"),
    ("Sediment flux in braided river channels", "discharge (m$^3$/s)", "flux (kg/s)"),
    ("Spectral analysis of turbulent wakes", "frequency $fD/U$", "PSD"),
    ("Adaptive control of quadrotor swarms", "time (s)", "position error (m)"),
    ("Photoluminescence of silicon nanocrystals", "wavelength (nm)", "intensity (a.u.)"),
    ("Graph neural networks for crystal property prediction", "epoch", "MAE (eV/atom)"),
    ("Groundwater recharge under changing land use", "year", "recharge (mm/yr)"),
    ("Low-power wake-up receivers for IoT nodes", "input power (dBm)", "miss rate"),
    ("Mechanical metamaterials with tunable stiffness", "strain (%)", "stress (MPa)"),
    ("Protein folding kinetics from single-molecule FRET", "time (ms)", "FRET efficiency"),
]


def paragraph(rnd, n):
    return " ".join(rnd.choice(SENT["generic"]) for _ in range(n))


# ---------------------------------------------------------------- figures (matplotlib -> PDF bytes / PNG bytes)
def fig_lines(rnd, xl, yl, w, h, top_ticks=False, title=None, panels=1):
    fig, axes = plt.subplots(1, panels, figsize=(w, h))
    axes = np.atleast_1d(axes)
    for k, ax in enumerate(axes):
        x = np.linspace(0, 10, 200)
        for j, st in enumerate(["-", "--", ":"][: rnd.randint(2, 3)]):
            ax.plot(x, np.sin(x * (0.6 + 0.2 * j) + k) * np.exp(-x / (8 + 3 * j)) + 0.3 * j, st, lw=1.2, label=f"case {j + 1}")
        ax.set_xlabel(xl)
        ax.set_ylabel(yl)
        if panels > 1:
            ax.text(0.03, 0.92, f"({chr(97 + k)})", transform=ax.transAxes)
        if top_ticks:
            sec = ax.secondary_xaxis("top", functions=(lambda v: v * 2.5, lambda v: v / 2.5))
            sec.set_xlabel("scaled coordinate")
        ax.legend(frameon=False, fontsize=7)
    if title:
        fig.suptitle(title, fontsize=8)
    fig.tight_layout()
    return fig


def fig_bars(rnd, xl, yl, w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    cats = ["A", "B", "C", "D", "E"]
    for j in range(3):
        ax.bar(np.arange(5) + j * 0.25, [rnd.uniform(1, 5) for _ in cats], width=0.25, label=f"group {j + 1}")
    ax.set_xticks(np.arange(5) + 0.25, cats)
    ax.set_ylabel(yl)
    ax.legend(frameon=False, fontsize=7, ncol=3, loc="upper left")
    fig.tight_layout()
    return fig


def fig_heat(rnd, w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    z = np.add.outer(np.sin(np.linspace(0, 6, 60)), np.cos(np.linspace(0, 4, 80))) + np.random.default_rng(rnd.randint(0, 99)).normal(0, .2, (60, 80))
    im = ax.imshow(z, cmap="viridis", aspect="auto")
    fig.colorbar(im, ax=ax, label="amplitude")
    ax.set_xlabel("x (µm)")
    ax.set_ylabel("y (µm)")
    fig.tight_layout()
    return fig


def fig_scatter(rnd, xl, yl, w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    g = np.random.default_rng(rnd.randint(0, 99))
    x = g.uniform(0, 1, 120)
    ax.scatter(x, 2 * x + g.normal(0, .25, 120), s=8)
    ax.plot([0, 1], [0, 2], "k--", lw=1)
    ax.set_xlabel(xl)
    ax.set_ylabel(yl)
    fig.tight_layout()
    return fig


def as_pdf(fig, pad_in):
    buf = io.BytesIO()
    fig.savefig(buf, format="pdf", bbox_inches="tight", pad_inches=pad_in)  # loose white bounding box like EPS
    plt.close(fig)
    return pymupdf.open("pdf", buf.getvalue())


def as_png(fig, pad_in):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", pad_inches=pad_in, facecolor="white")
    plt.close(fig)
    return buf.getvalue()


# ---------------------------------------------------------------- page layout
class Doc:
    def __init__(self, style, seed):
        self.s = style
        self.rnd = random.Random(seed)
        self.doc = pymupdf.open()
        self.fig_no = 0
        self.topic = TOPICS[seed % len(TOPICS)]
        self.truth = {}  # page -> {"running": [rects], "figures": [rects], "controls": [...]}

    def mark(self, pno, kind, x, baseline, text, font, fs):
        w = pymupdf.get_text_length(text, font, fs)
        self.truth.setdefault(pno, {"running": [], "figures": []})["running"].append(
            {"kind": kind, "text": text, "rect": [round(x, 1), round(baseline - 0.8 * fs, 1), round(x + w, 1), round(baseline + 0.25 * fs, 1)]})

    def new_page(self, pno):
        s = self.s
        page = self.doc.new_page(width=s["W"], height=s["H"])
        # running head
        hy = s["head_y"]
        if pno == 1 and s.get("first_page_plain"):
            pass
        else:
            outer_right = s.get("alternate") is None or pno % 2 == 1
            folio = s["folio_fmt"].format(pno)
            if s["folio"] == "top-outer":
                x = s["W"] - s["margin"] - pymupdf.get_text_length(folio, "helv", s["head_fs"]) if outer_right else s["margin"]
                page.insert_text((x, hy), folio, fontname="helv", fontsize=s["head_fs"]); self.mark(pno, "folio", x, hy, folio, "helv", s["head_fs"])
            if s["folio"] == "top-centre":
                x = (s["W"] - pymupdf.get_text_length(folio, "helv", s["head_fs"])) / 2
                page.insert_text((x, hy), folio, fontname="helv", fontsize=s["head_fs"]); self.mark(pno, "folio", x, hy, folio, "helv", s["head_fs"])
            if s.get("head_text"):
                txt = s["head_text"]
                if outer_right:
                    x = s["margin"]
                else:
                    x = s["W"] - s["margin"] - pymupdf.get_text_length(txt, "helv", s["head_fs"])
                page.insert_text((x, hy), txt, fontname="helv", fontsize=s["head_fs"]); self.mark(pno, "head", x, hy, txt, "helv", s["head_fs"])
            if s.get("rule"):
                page.draw_line((s["margin"], hy + 4), (s["W"] - s["margin"], hy + 4), width=0.5)
            if s["folio"] == "bottom-centre":
                w = pymupdf.get_text_length(folio, "tiro", 10)
                page.insert_text(((s["W"] - w) / 2, s["H"] - s["foot_y"]), folio, fontname="tiro", fontsize=10); self.mark(pno, "folio", (s["W"] - w) / 2, s["H"] - s["foot_y"], folio, "tiro", 10)
        return page

    def text(self, page, rect, n):
        page.insert_textbox(rect, paragraph(self.rnd, n), fontname="tiro", fontsize=self.s["body_fs"], align=3)

    @staticmethod
    def _tint(pix, bg):
        """Replace pure white by the off-white paper tone, as in a scanned figure."""
        data = bytearray(pix.samples)
        for i in range(0, len(data), 3):
            if data[i] > 250 and data[i + 1] > 250 and data[i + 2] > 250:
                data[i] = data[i + 1] = data[i + 2] = bg
        out = pymupdf.Pixmap(pymupdf.csRGB, pix.width, pix.height, bytes(data), False)
        out.set_origin(pix.x, pix.y)
        return out

    def place_figure(self, page, rect, kind, loose_top=0.0, raster=False, control=None):
        """Draw a figure in `rect` (page coords). `loose_top` pt of white bounding box above the plot."""
        s, rnd, (_, xl, yl) = self.s, self.rnd, self.topic
        w_in, h_in = rect.width / 72, max(1.2, (rect.height - loose_top) / 72)
        if kind == "lines":
            fig = fig_lines(rnd, xl, yl, w_in, h_in, top_ticks=control == "top_ticks", title="Panel overview" if control == "title" else None)
        elif kind == "panels":
            fig = fig_lines(rnd, xl, yl, w_in, h_in, panels=2, top_ticks=control == "top_ticks")
        elif kind == "bars":
            fig = fig_bars(rnd, xl, yl, w_in, h_in)
        elif kind == "heat":
            fig = fig_heat(rnd, w_in, h_in)
        else:
            fig = fig_scatter(rnd, xl, yl, w_in, h_in)
        pad = 0.04
        if raster:
            png = as_png(fig, pad)
            pix = pymupdf.Pixmap(png)
            if pix.alpha:
                pix = pymupdf.Pixmap(pix, 0)
            rr = pymupdf.Rect(rect.x0, rect.y0 + loose_top, rect.x1, rect.y1)
            # white canvas reaching up by loose_top (scanned/exported figure with whitespace above the plot)
            canvas = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, pix.width, int(pix.height * rect.height / rr.height)), False)
            bg = self.s.get("raster_bg", 255)  # scanned figures carry off-white paper, not pure white
            canvas.set_rect(canvas.irect, (bg, bg, bg))
            if bg < 255:
                pix = self._tint(pix, bg)
            pix.set_origin(0, canvas.height - pix.height)
            canvas.copy(pix, pymupdf.IRect(0, canvas.height - pix.height, pix.width, canvas.height))
            page.insert_image(rect, pixmap=canvas, keep_proportion=False)
        else:
            src = as_pdf(fig, pad)
            # show the figure with its loose white box: grow the source page's box upwards by loose_top (scaled)
            sp = src[0]
            scale = rect.width / sp.rect.width
            extra = loose_top / scale
            if extra > 0:
                sp.set_mediabox(pymupdf.Rect(0, -extra, sp.rect.width, sp.rect.height))
                # white background patch over the enlarged box (as an EPS with a white frame would have)
                sh = sp.new_shape()
                sh.draw_rect(pymupdf.Rect(0, -extra, sp.rect.width, sp.rect.height))
                sh.finish(color=None, fill=(1, 1, 1))
                sh.commit(overlay=False)
            page.show_pdf_page(rect, src, 0, keep_proportion=False)
        self.fig_no += 1
        pno = page.number + 1
        self.truth.setdefault(pno, {"running": [], "figures": []})["figures"].append(
            {"no": self.fig_no, "kind": kind, "placement": [round(v, 1) for v in rect], "loose_top": loose_top,
             "raster": raster, "control": control})
        return self.fig_no

    def caption(self, page, rect, no):
        txt = f"{self.s['fig_word']} {no}. " + self.rnd.choice([
            "Measured and simulated response for the three configurations discussed in the text.",
            "Evolution of the main observable with the control parameter; dashed lines are model predictions.",
            "Comparison of the proposed method with the two baselines over the full test set.",
            "Spatial map of the signal amplitude recorded during the reference experiment.",
            "Correlation between predicted and measured values; the dashed line marks perfect agreement.",
        ])
        page.insert_textbox(rect, txt, fontname="tiro", fontsize=self.s["body_fs"] - 1, align=self.s.get("cap_align", 0))


def build(name, style, seed, plan):
    d = Doc(style, seed)
    s = style
    m, W, H = s["margin"], s["W"], s["H"]
    top = s["body_top"]
    bottom = H - s["body_bottom"]
    cols = s["cols"]
    gap = 14
    colw = (W - 2 * m - (cols - 1) * gap) / cols
    for pno, kind in enumerate(plan, 1):
        page = d.new_page(pno)
        y = top
        col_x = [m + c * (colw + gap) for c in range(cols)]
        if kind == "title":
            page.insert_textbox(pymupdf.Rect(m, y, W - m, y + 50), d.topic[0], fontname="tibo", fontsize=16, align=1)
            page.insert_textbox(pymupdf.Rect(m, y + 46, W - m, y + 62), "A. Researcher, B. Scientist and C. Engineer", fontname="tiro", fontsize=10, align=1)
            page.insert_textbox(pymupdf.Rect(m + 30, y + 74, W - m - 30, y + 150), "Abstract. " + paragraph(d.rnd, 5), fontname="tiro", fontsize=9, align=3)
            y += 160
            for cx in col_x:
                d.text(page, pymupdf.Rect(cx, y, cx + colw, bottom), 40)
            continue
        fig_spec = kind  # e.g. "top:lines:loose18", "top-wide:heat:raster", "mid:lines:title", "bottom:bars"
        pos, fkind, *opts = fig_spec.split(":")
        loose = next((float(o[5:]) for o in opts if o.startswith("loose")), 0.0)
        raster = "raster" in opts
        control = next((o for o in ("title", "top_ticks") if o in opts), None)
        fh = s.get("fig_h", 170)
        wide = pos.endswith("wide") or cols == 1
        fx0, fx1 = (m, W - m) if wide else (col_x[-1], col_x[-1] + colw)
        if cols == 1:
            fx0, fx1 = m + 0.08 * (W - 2 * m), W - m - 0.08 * (W - 2 * m)
        if pos.startswith("top"):
            fr = pymupdf.Rect(fx0, top - loose, fx1, top + fh)
            no = d.place_figure(page, fr, fkind, loose_top=loose, raster=raster, control=control)
            d.caption(page, pymupdf.Rect(fx0, fr.y1 + 4, fx1, fr.y1 + 34), no)
            ytext = fr.y1 + 40
            for cx in col_x:
                ys = ytext if (wide or cx == fx0) else top
                d.text(page, pymupdf.Rect(cx, ys, cx + colw, bottom), 40)
        elif pos == "mid":
            for cx in col_x:
                d.text(page, pymupdf.Rect(cx, top, cx + colw, top + 150), 12)
            fr = pymupdf.Rect(fx0, top + 165, fx1, top + 165 + fh)
            no = d.place_figure(page, fr, fkind, raster=raster, control=control)
            d.caption(page, pymupdf.Rect(fx0, fr.y1 + 4, fx1, fr.y1 + 34), no)
            for cx in col_x:
                ys = fr.y1 + 40 if (wide or cx == fx0) else top + 150
                d.text(page, pymupdf.Rect(cx, ys, cx + colw, bottom), 30)
        elif pos.startswith("bottom"):
            fr = pymupdf.Rect(fx0, bottom - fh - 30, fx1, bottom - 30 + loose)
            for cx in col_x:
                ye = fr.y0 - 10 if (wide or cx == fx0) else bottom
                d.text(page, pymupdf.Rect(cx, top, cx + colw, ye), 40)
            no = d.place_figure(page, pymupdf.Rect(fr.x0, fr.y0, fr.x1, fr.y1 - loose), fkind, raster=raster, control=control)
            d.caption(page, pymupdf.Rect(fx0, fr.y1 - loose + 2, fx1, fr.y1 - loose + 28), no)
    d.doc.set_metadata({"title": d.topic[0], "author": "Synthetic test set", "producer": "Luka-Loop header test generator"})
    d.doc.save(OUT / name, garbage=3, deflate=True)
    return {"pages": len(plan), "plan": plan, "truth": d.truth}


LETTER, A4 = (612, 792), (595.28, 841.89)
STYLES = {
    # two-column physics letter: lone page number at the outer top corner, top floats right under it
    "01_two_column_letter.pdf": dict(W=LETTER[0], H=LETTER[1], margin=54, cols=2, head_y=38, head_fs=9, folio="top-outer",
                                     folio_fmt="{}", head_text=None, body_top=50, body_bottom=60, body_fs=10, fig_word="FIG.", fig_h=150,
                                     first_page_plain=True),
    # two-column journal with running title left + folio right on one line
    "02_journal_running_title.pdf": dict(W=A4[0], H=A4[1], margin=48, cols=2, head_y=40, head_fs=8, folio="top-outer", folio_fmt="{}",
                                         head_text="J. Appl. Hydrodyn. 41 (2026)", body_top=52, body_bottom=64, body_fs=9.5, fig_word="Fig.", fig_h=160),
    # book chapter: deep top margin (head below the top 10% band) with a rule
    "03_book_chapter_deep_margin.pdf": dict(W=A4[0], H=A4[1], margin=72, cols=1, head_y=104, head_fs=9, folio="top-outer", folio_fmt="{}",
                                            head_text="Spectral analysis of turbulent wakes", rule=True, body_top=118, body_bottom=90,
                                            body_fs=10.5, fig_word="Fig.", fig_h=210, alternate=True),
    # thesis: chapter running head + folio, rule, deep margin
    "04_thesis_rule.pdf": dict(W=A4[0], H=A4[1], margin=80, cols=1, head_y=96, head_fs=10, folio="top-outer", folio_fmt="{}",
                               head_text="Chapter 3. Adaptive control of quadrotor swarms", rule=True, body_top=112, body_bottom=90,
                               body_fs=11, fig_word="Figure", fig_h=200),
    # preprint with loose EPS-style bounding boxes reaching into the head band
    "05_preprint_loose_bbox.pdf": dict(W=LETTER[0], H=LETTER[1], margin=60, cols=2, head_y=36, head_fs=9, folio="top-outer", folio_fmt="{}",
                                       head_text=None, body_top=48, body_bottom=60, body_fs=10, fig_word="FIG.", fig_h=150),
    # technical report: lone folio centred at the top, tight top margin
    "06_report_centred_folio.pdf": dict(W=A4[0], H=A4[1], margin=70, cols=1, head_y=38, head_fs=9, folio="top-centre", folio_fmt="{}",
                                       head_text=None, body_top=46, body_bottom=70, body_fs=10.5, fig_word="Figure", fig_h=190),
    # supplementary information: S-numbered folios, raster figures with white margins
    "07_supplement_raster.pdf": dict(W=A4[0], H=A4[1], margin=56, cols=1, head_y=40, head_fs=9, folio="top-outer", folio_fmt="S{}",
                                     head_text="Supplementary Information", body_top=50, body_bottom=64, body_fs=10, fig_word="Figure S", fig_h=200, raster_bg=243),
    # conference: lone folio, two columns, full-width top figures
    "08_conference_wide_figs.pdf": dict(W=LETTER[0], H=LETTER[1], margin=48, cols=2, head_y=36, head_fs=8, folio="top-outer", folio_fmt="{}",
                                        head_text=None, body_top=48, body_bottom=60, body_fs=9.5, fig_word="Fig.", fig_h=170),
    # proceedings with alternating heads (author left on even, title right on odd) + folio
    "09_proceedings_alternating.pdf": dict(W=A4[0], H=A4[1], margin=60, cols=2, head_y=42, head_fs=8, folio="top-outer", folio_fmt="{}",
                                           head_text="Proc. Mech. Metamater. 2026", body_top=54, body_bottom=64, body_fs=9.5, fig_word="Fig.",
                                           fig_h=160, alternate=True),
    # monograph: deep margin, head + folio, no rule, raster micrographs
    "10_monograph_deep_raster.pdf": dict(W=A4[0], H=A4[1], margin=76, cols=1, head_y=100, head_fs=9, folio="top-outer", folio_fmt="{}",
                                         head_text="Protein folding kinetics", body_top=114, body_bottom=90, body_fs=10.5, fig_word="Figure", fig_h=200),
}
PLANS = {
    "01_two_column_letter.pdf": ["title", "top:lines", "top:panels:loose14", "mid:lines:title", "top:scatter:top_ticks"],
    "02_journal_running_title.pdf": ["title", "top-wide:panels", "top:lines:loose10", "mid:bars", "top:heat"],
    "03_book_chapter_deep_margin.pdf": ["title", "top:lines", "top:panels", "mid:scatter:title", "top:lines:top_ticks"],
    "04_thesis_rule.pdf": ["title", "top:bars", "top:lines", "mid:lines:top_ticks", "top:heat"],
    "05_preprint_loose_bbox.pdf": ["title", "top:lines:loose20", "top:scatter:loose16", "mid:panels", "top-wide:lines:loose12"],
    "06_report_centred_folio.pdf": ["title", "top:lines", "top:bars", "mid:scatter:title", "top:heat:loose10"],
    "07_supplement_raster.pdf": ["title", "top:heat:raster:loose16", "top:lines:raster:loose12", "mid:panels:raster", "top:scatter:raster"],
    "08_conference_wide_figs.pdf": ["title", "top-wide:panels", "top-wide:lines:loose12", "mid:bars", "top-wide:panels:top_ticks"],
    "09_proceedings_alternating.pdf": ["title", "top-wide:lines", "top:panels", "mid:scatter:title", "top-wide:bars"],
    "10_monograph_deep_raster.pdf": ["title", "top:heat:raster", "top:lines:raster", "mid:lines:raster:title", "top:panels"],
}
import json  # noqa: E402
truth = {}
for i, (name, st) in enumerate(STYLES.items()):
    truth[name] = build(name, st, i, PLANS[name])
    print("wrote", name)
(OUT / "truth.json").write_text(json.dumps(truth, indent=1), encoding="utf-8")


