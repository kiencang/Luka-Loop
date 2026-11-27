"""Statistics of DocLayNet scientific pages as the detector sees them, from `dev/doclaynet_facts.py`. Dev-only tool.

The report gives the measured distributions behind each kind of detector rule (dev/detector_rules.md), so new
thresholds can be read from data instead of fixed case by case:

  1  text blocks by DocLayNet class (figure labels vs body text, captions, headings ...): word count, size, width,
     the main-text features and score, the widest word gap; how each current "prose" definition and label test
     splits labels from body text
  2  figure labels outside the visible part of the figure (trimmed images + clip-cut drawings): distance and side,
     with and without chaining, against the text of other classes found as close to the figure
  3  raster images: white margins, how the annotated Picture box sits against the placement and trimmed boxes, and
     how often text is printed over the trimmed margin (intentional white space) and whose text it is
  4  drawings cut by their clip ("ribbons") inside figures
  5  figure-caption placement: side, gap, overlap, what lies between
  6  multi-part figures: gaps between the parts of one figure vs gaps between two figures
  7  page header / footer bands

Thresholds should be chosen on `tune` only; `val`/`test` are for checking them.

Example:
  python -X utf8 dev\\doclaynet_stats.py --subset tune
  python -X utf8 dev\\doclaynet_stats.py --subset val --subset test --collection arxiv_two_columns
Output: work-dev\\doclaynet_stats\\report_<subsets>[_<collection>].md (+ .json with the raw summaries).
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import re
import sys
import tempfile
from pathlib import Path

DEV_DIR = Path(__file__).resolve().parent
if str(DEV_DIR) not in sys.path:
    sys.path.insert(0, str(DEV_DIR))
from doclaynet_facts import FACTS_VERSION, MAX_DRAWINGS, SUBSETS, area, centre, inside, overlap  # noqa: E402

REPO_ROOT = DEV_DIR.parent
SRC_DIR = REPO_ROOT / "tools" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
from figure_detector.pipeline import _EQUATION_NUMBER_RE, _is_bullet_line  # noqa: E402
BODY = ("Text", "List-item")
CLASS_ORDER = ("Picture", "Caption", "Text", "List-item", "Formula", "Section-header", "Title", "Footnote",
               "Page-header", "Page-footer", "Table", "none")
TRIM_MIN_GAIN = 0.03          # DetectorConfig.raster_trim_min_gain
PART_TOL = 5.0                # vector clustering tolerance (cluster_tol_x/y)
NEAR = 80.0                   # pt: text of other classes this close to a figure's visible part is counted
DIST_STEPS = (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 35, 40, 50, 60, 80)
SIDES = ("left", "right", "top", "bottom", "overlap")


# ==============================================================================
# Pure helpers (unit-tested in tests\test_doclaynet_stats.py)
# ==============================================================================


def quantiles(values) -> dict:
    v = sorted(x for x in values if x is not None)
    n = len(v)
    if not n:
        return {"n": 0}

    def at(p: float) -> float:
        return round(v[min(n - 1, int(p * n))], 3)

    return {"n": n, "p1": at(0.01), "p10": at(0.10), "p50": at(0.50), "p90": at(0.90), "p99": at(0.99),
            "max": round(v[-1], 3)}


def union(rects):
    rects = [r for r in rects if r]
    if not rects:
        return None
    return [min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects)]


def rect_gap(a, b) -> float:
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return (dx * dx + dy * dy) ** 0.5


def axis_gap(a, b) -> float:
    """Larger of the horizontal and vertical gaps (0 when the rects overlap), as vector clustering measures."""
    return max(max(a[0], b[0]) - min(a[2], b[2]), max(a[1], b[1]) - min(a[3], b[3]), 0.0)


def side_of(r, core) -> str:
    """Side of `core` on which `r` lies: the direction of the largest separation, or 'overlap'."""
    seps = {"left": core[0] - r[2], "right": r[0] - core[2], "top": core[1] - r[3], "bottom": r[1] - core[3]}
    s, v = max(seps.items(), key=lambda kv: kv[1])
    return s if v > 0 else "overlap"


def chain_gaps(core, rects: list) -> list[float]:
    """For each rect, the smallest possible largest step from `core` to it through the other rects (minimax path).

    With chaining, a label 30 pt from the figure is reachable in 10 pt steps when two labels sit in between.
    """
    n = len(rects)
    best = [rect_gap(r, core) for r in rects]
    done = [False] * n
    for _ in range(n):
        i = min((k for k in range(n) if not done[k]), key=lambda k: best[k], default=None)
        if i is None:
            break
        done[i] = True
        for j in range(n):
            if not done[j]:
                best[j] = min(best[j], max(best[i], rect_gap(rects[i], rects[j])))
    return best


def components(rects: list, tol: float) -> list[list[int]]:
    """Groups of rects chained by `axis_gap` <= tol (union-find)."""
    parent = list(range(len(rects)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = sorted(range(len(rects)), key=lambda k: rects[k][0])
    for a_i, i in enumerate(order):
        for j in order[a_i + 1:]:
            if rects[j][0] - rects[i][2] > tol:
                break
            if axis_gap(rects[i], rects[j]) <= tol:
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(rects)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def mst_edges(boxes: list) -> list[float]:
    """Edges (axis gaps) of the minimum spanning tree joining `boxes`: the gaps a merge rule must bridge."""
    n = len(boxes)
    if n < 2:
        return []
    best = [axis_gap(boxes[0], b) for b in boxes]
    used = [False] * n
    used[0] = True
    edges = []
    for _ in range(n - 1):
        i = min((k for k in range(n) if not used[k]), key=lambda k: best[k])
        used[i] = True
        edges.append(best[i])
        for j in range(n):
            if not used[j]:
                best[j] = min(best[j], axis_gap(boxes[i], boxes[j]))
    return edges


def within(values, steps=DIST_STEPS) -> list[tuple[float, float]]:
    """Cumulative share (%) of `values` at or below each step."""
    v = sorted(values)
    n = max(1, len(v))
    out, k = [], 0
    for s in steps:
        while k < len(v) and v[k] <= s:
            k += 1
        out.append((s, round(100.0 * k / n, 1)))
    return out


# ==============================================================================
# Loading
# ==============================================================================


def load_pages(cache_dir: Path, subsets: list[str], collection: str | None, folder: str | None,
               docs: set | None = None) -> list[dict]:
    base = cache_dir / "facts" / (folder or f"v{FACTS_VERSION}")
    pages = []
    for f in sorted(base.glob("*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                p = json.loads(line)
                if p.get("subset") not in subsets or "blocks" not in p:
                    continue
                if collection and p.get("collection") != collection:
                    continue
                if docs is not None and p.get("doc") not in docs:
                    continue
                pages.append(p)
    return pages


# ==============================================================================
# Figure geometry from the facts
# ==============================================================================


def picture_parts(p: dict, gi: int) -> tuple[list, list]:
    """Visible parts of Picture `gi`: (image rects as the tool keeps them, clip-cut drawing rects)."""
    pic = p["gt"][gi]["r"]
    page_area = p["w"] * p["h"]
    imgs = []
    for im in p["images"]:
        if not (im["gi"] == gi or overlap(im["r"], pic) >= 0.5 * max(1e-6, area(im["r"]))):
            continue
        if im["ink"] == []:
            continue  # blank image
        trimmed = im["ink"] and area(im["ink"]) < (1 - TRIM_MIN_GAIN) * area(im["r"])
        imgs.append(im["ink"] if trimmed else im["r"])
    drs = []
    for r, _u, kind, _w, _n in p["drawings"]:
        if not inside(centre(r), pic):
            continue
        a = area(r)
        if a >= 0.9 * page_area or (kind == "f" and a > 2.0 * area(pic)):
            continue  # page or panel background
        drs.append(r)
    for r, k, _n in p.get("drawings_overflow", ()):
        if k == gi:
            drs.append(r)  # union of the drawings past the per-page cap whose centre lies in this Picture
    return imgs, drs


# ==============================================================================
# Sections
# ==============================================================================


def s1_text_blocks(pages: list[dict]) -> dict:
    feats = ("wc", "rows", "width", "height", "size", "size_rel", "width_rel", "chars_per_line", "lower_frac",
             "alpha_frac", "digit_frac", "gap_em", "score")
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    flags = collections.defaultdict(collections.Counter)
    mixed = collections.Counter()
    pure_blocks = []
    for p in pages:
        for b in p["blocks"]:
            cls = b["gt"]
            if b["share"] < 0.5:
                mixed[cls] += 1
                continue
            r, f = b["r"], b["f"]
            row = {"wc": b["wc"], "rows": b["rows"], "width": r[2] - r[0], "height": r[3] - r[1], "size": f["size"],
                   "size_rel": f["size_rel"], "width_rel": f["width_rel"], "chars_per_line": f["chars_per_line"],
                   "lower_frac": f["lower_frac"], "alpha_frac": f["alpha_frac"], "digit_frac": f["digit_frac"],
                   "gap_em": b["gap_em"], "score": b["score"]}
            for k in feats:
                by[cls][k].append(row[k])
            c = flags[cls]
            c["n"] += 1
            c["kind=" + b["kind"]] += 1
            c["short_axis"] += b["short_axis"]
            c["label_row"] += b["label_row"]
            c["heading_re"] += b["heading_re"]
            c["period"] += b["period"]
            c["same_font"] += f["same_font"]
            c["main_text"] += b["kind"] == "text" and b["wc"] >= 13 and b["score"] >= 70
            pure_blocks.append((cls, b))
    dist = {cls: {k: quantiles(v) for k, v in d.items()} for cls, d in by.items()}

    # current "prose" definitions (dev/detector_rules.md 11.1) and label tests, on labels vs body vs captions
    defs = {
        ">=4 words": lambda b: b["wc"] >= 4,
        ">=6 words, not short label": lambda b: b["wc"] >= 6 and not b["short_axis"],
        ">=10 words": lambda b: b["wc"] >= 10,
        ">=12 words": lambda b: b["wc"] >= 12,
        ">=12 words, not short label": lambda b: b["wc"] >= 12 and not b["short_axis"],
        ">=12, not short label, not label row": lambda b: b["wc"] >= 12 and not b["short_axis"] and not b["label_row"],
        "main text (>=13 words, >=70 pts)": lambda b: b["wc"] >= 13 and b["score"] >= 70,
        "main text, gap < 8 em": lambda b: b["wc"] >= 13 and b["score"] >= 70 and b["gap_em"] < 8,
        "short axis label": lambda b: b["short_axis"],
        "label row": lambda b: b["label_row"],
    }
    groups = {"label (in Picture)": ("Picture",), "body (Text, List-item)": BODY, "Caption": ("Caption",),
              "Formula": ("Formula",), "Section-header": ("Section-header",), "Page-header/footer": ("Page-header", "Page-footer")}
    def_rates = {}
    for name, fn in defs.items():
        row = {}
        for gname, classes in groups.items():
            bs = [b for cls, b in pure_blocks if cls in classes and b["kind"] == "text"]
            row[gname] = round(100.0 * sum(1 for b in bs if fn(b)) / max(1, len(bs)), 2)
        def_rates[name] = row
    group_n = {g: sum(1 for cls, b in pure_blocks if cls in c and b["kind"] == "text") for g, c in groups.items()}

    # separability, label vs body, for single thresholds
    lab = [b for cls, b in pure_blocks if cls == "Picture" and b["kind"] == "text"]
    body = [b for cls, b in pure_blocks if cls in BODY and b["kind"] == "text"]
    sep = {}
    for name, key, steps in (("words >= t", "wc", (2, 3, 4, 5, 6, 8, 10, 12, 13, 14, 16, 20, 25, 30, 40)),
                             ("score >= t (blocks >= 13 words)", "score", (40, 50, 60, 65, 70, 75, 80, 85, 90)),
                             ("gap_em >= t (blocks >= 6 words)", "gap_em", (1, 2, 3, 4, 5, 6, 7, 8, 10, 12))):
        rows = []
        for t in steps:
            if key == "score":
                lv = [b for b in lab if b["wc"] >= 13]
                bv = [b for b in body if b["wc"] >= 13]
            elif key == "gap_em":
                lv = [b for b in lab if b["wc"] >= 6]
                bv = [b for b in body if b["wc"] >= 6]
            else:
                lv, bv = lab, body
            rows.append((t, round(100.0 * sum(1 for b in lv if b[key] >= t) / max(1, len(lv)), 2), len(lv),
                         round(100.0 * sum(1 for b in bv if b[key] >= t) / max(1, len(bv)), 2), len(bv)))
        sep[name] = rows
    return {"dist": dist, "flags": {k: dict(v) for k, v in flags.items()}, "mixed": dict(mixed),
            "defs": def_rates, "group_n": group_n, "sep": sep}


def s2_labels(pages: list[dict]) -> dict:
    lab_gap, lab_chain, lab_side = [], [], collections.Counter()
    lab_side_gap = collections.defaultdict(list)
    lab_props = collections.defaultdict(list)
    lab_flags = collections.Counter()
    foreign = collections.defaultdict(list)          # class -> gaps to the nearest figure
    foreign_side = collections.defaultdict(list)     # side -> gaps (all classes)
    foreign_side_cls = collections.defaultdict(collections.Counter)
    pics_n = pics_core = pics_text_only = pics_with_outside = 0
    on_graphic = 0
    gt_beyond_core = collections.defaultdict(list)
    capped = 0
    kinds = collections.defaultdict(lambda: {"pictures": 0, "with_labels": 0, "captioned": 0,
                                             "captioned_with_labels": 0, "gap": [], "chain": []})
    std_lab = []                                    # (chain gap, meets label standard) of every label line
    std_for = collections.defaultdict(list)         # class group -> (chained gap, meets label standard)
    blockers = collections.defaultdict(collections.Counter)  # class -> which existing guard stops the line
    miss = collections.Counter()                    # why a label line fails `_label_lines`
    for p in pages:
        cores = {}
        chained = {}                                # gi -> [(label rect, chain gap)]
        caps = [g["r"] for g in p["gt"] if g["c"] == "Caption"]
        if p.get("drawings_dropped"):
            capped += sum(1 for g in p["gt"] if g["c"] == "Picture")  # visible part uses the overflow union
        for gi, g in enumerate(p["gt"]):
            if g["c"] != "Picture":
                continue
            pics_n += 1
            imgs, drs = picture_parts(p, gi)
            core = union(imgs + drs)
            if core is None:
                pics_text_only += 1
                continue
            pics_core += 1
            cores[gi] = core
            pic = g["r"]
            loose = [d for d in drs if not any(inside(centre(d), im, 2.0) for im in imgs)]
            kind = "raster" if imgs and not loose else "vector" if not imgs else "hybrid"
            kd = kinds[kind]
            kd["pictures"] += 1
            has_cap = any(rect_gap(pic, c) <= 100 for c in caps)
            kd["captioned"] += has_cap
            for s, v in (("left", core[0] - pic[0]), ("right", pic[2] - core[2]), ("top", core[1] - pic[1]),
                         ("bottom", pic[3] - core[3])):
                gt_beyond_core[s].append(v)
            mine = [ln for ln in p["lines"] if ln["gt"] == "Picture" and ln["gi"] == gi]
            outside = [ln for ln in mine if not inside(centre(ln["r"]), core)]
            on_graphic += len(mine) - len(outside)
            if outside:
                pics_with_outside += 1
                kd["with_labels"] += 1
                kd["captioned_with_labels"] += has_cap
            chains = chain_gaps(core, [ln["r"] for ln in outside])
            chained[gi] = [(ln["r"], ch) for ln, ch in zip(outside, chains)]
            for ln, ch in zip(outside, chains):
                d = rect_gap(ln["r"], core)
                kd["gap"].append(d)
                kd["chain"].append(ch)
                std_lab.append((ch, _meets_label_standard(p, ln)))
                if not ln["label_like"]:
                    miss[_label_miss_reason(p, ln)] += 1
                s = side_of(ln["r"], core)
                lab_gap.append(d)
                lab_chain.append(ch)
                lab_side[s] += 1
                lab_side_gap[s].append(d)
                lab_props["words"].append(ln["nw"])
                lab_props["width"].append(ln["r"][2] - ln["r"][0])
                lab_props["size_rel"].append(ln["size"] / p["page_size"] if p["page_size"] else None)
                lab_flags["n"] += 1
                lab_flags["label_like"] += ln["label_like"]
                if ln["owner"] >= 0:
                    ob = p["blocks"][ln["owner"]]
                    lab_flags["owner_short_axis"] += ob["short_axis"]
                    lab_flags["owner_wc>=12"] += ob["wc"] >= 12
                    lab_flags["owner_main_text"] += ob["wc"] >= 13 and ob["score"] >= 70
        if not cores:
            continue
        for ln in p["lines"]:
            if ln["gt"] == "Picture":
                continue
            best = None
            for core in cores.values():
                d = rect_gap(ln["r"], core)
                if best is None or d < best[0]:
                    best = (d, side_of(ln["r"], core))
            if best and best[0] <= NEAR:
                foreign[ln["gt"]].append(best[0])
                foreign_side[best[1]].append(best[0])
                foreign_side_cls[best[1]][ln["gt"]] += 1
                # chained: a detector that takes labels in steps can reach this line through the figure's labels
                ch = min(min([rect_gap(ln["r"], core)] + [max(c, rect_gap(ln["r"], r)) for r, c in chained.get(gi, ())])
                         for gi, core in cores.items())
                grp = "Caption" if ln["gt"] == "Caption" else "Text, List-item" if ln["gt"] in BODY else "khác"
                ok = _meets_label_standard(p, ln)
                std_for[grp].append((ch, ok))
                if ok and ch <= 16:
                    blockers[ln["gt"]][_blocker(p, ln)] += 1
    combo = []
    for t in (4, 8, 12, 16, 20, 24, 30, 40):
        row = {"t": t,
               "labels": round(100.0 * sum(1 for c, ok in std_lab if c <= t) / max(1, len(std_lab)), 2),
               "labels_std": round(100.0 * sum(1 for c, ok in std_lab if c <= t and ok) / max(1, len(std_lab)), 2)}
        for grp, v in std_for.items():
            row[grp] = sum(1 for c, ok in v if c <= t)
            row[grp + " std"] = sum(1 for c, ok in v if c <= t and ok)
        combo.append(row)
    seps = {}
    for s in SIDES:
        lv, fv = lab_side_gap.get(s, []), foreign_side.get(s, [])
        seps[s] = [(t, a, sum(1 for x in fv if x <= t)) for (t, a) in within(lv)]
    return {
        "pictures": pics_n, "capped": capped, "with_visible_part": pics_core, "text_only": pics_text_only,
        "with_labels_outside": pics_with_outside, "label_lines_on_graphic": on_graphic,
        "gt_beyond_core": {s: quantiles(v) for s, v in gt_beyond_core.items()},
        "label_gap": quantiles(lab_gap), "label_chain_gap": quantiles(lab_chain),
        "label_within": within(lab_gap), "label_chain_within": within(lab_chain),
        "label_side": dict(lab_side), "label_side_gap": {s: quantiles(v) for s, v in lab_side_gap.items()},
        "label_props": {k: quantiles(v) for k, v in lab_props.items()}, "label_flags": dict(lab_flags),
        "foreign": {c: quantiles(v) for c, v in foreign.items()},
        "foreign_within": {c: within(v) for c, v in foreign.items()},
        "foreign_n": {c: len(v) for c, v in foreign.items()},
        "side_sep": seps, "foreign_side_cls": {s: dict(c) for s, c in foreign_side_cls.items()},
        "kinds": {k: {"pictures": v["pictures"], "with_labels": v["with_labels"], "captioned": v["captioned"],
                      "captioned_with_labels": v["captioned_with_labels"], "gap": quantiles(v["gap"]),
                      "chain": quantiles(v["chain"])} for k, v in kinds.items()},
        "combo": combo, "combo_n_labels": len(std_lab),
        "blockers": {c: dict(v) for c, v in blockers.items()},
        "label_miss": dict(miss),
    }


def _blocker(p: dict, ln: dict) -> str:
    """First existing guard that would stop a label step from taking this foreign line (approximation)."""
    h = p["h"]
    r = ln["r"]
    if r[3] <= 0.10 * h or r[1] >= 0.94 * h:
        return "dải 10% đầu / 6% cuối"
    ob = p["blocks"][ln["owner"]] if ln["owner"] >= 0 else None
    if ob and ob["kind"] != "text":
        return "khối chú thích"
    if ob and ob["wc"] >= 13 and ob["score"] >= 70:
        return "văn bản chính"
    if ob and ob["wc"] >= 12:
        return "khối ≥ 12 từ"
    if any(g["c"] == "Table" and inside(centre(r), g["r"]) for g in p["gt"]):
        return "trong bảng (khung DocLayNet)"
    return "không chốt nào"


def _line_fails(ln: dict, pw: float):
    ws = ln["text"].split()
    if ln["nw"] > 8:
        return "> 8 từ"
    if ln["r"][2] - ln["r"][0] > 0.55 * pw:
        return "rộng > 55% trang"
    if not ws:
        return None
    if len(ws) >= 2 and ws[-1].endswith((".", ";", ":", ",")):
        return "kết thúc . ; : ,"
    if ws[-1].endswith("-") and len(ws[-1]) > 1:
        return "gạch nối cuối dòng"
    if _EQUATION_NUMBER_RE.match(ws[-1]):
        return "số công thức (12)"
    return None


def _label_miss_reason(p: dict, ln: dict) -> str:
    """Why `_label_lines` leaves out this line, approximately, in the order its tests run."""
    if ln["owner"] < 0:
        return "không thuộc khối chữ nào"
    why = _line_fails(ln, p["w"])
    if why:
        return "dòng: " + why
    for o in p["lines"]:
        if o is not ln and o["owner"] == ln["owner"]:
            why = _line_fails(o, p["w"])
            if why:
                return "dòng khác cùng khối: " + why
    r, h = ln["r"], p["h"]
    if r[3] <= 0.10 * h or r[1] >= 0.94 * h:
        return "dải 10% đầu / 6% cuối"
    if _is_bullet_line(ln["text"].split()):
        return "giống gạch đầu dòng"
    ob = p["blocks"][ln["owner"]]
    if ob["kind"] != "text":
        return "khối bị coi là chú thích"
    if ob["heading_re"]:
        return "khối giống tiêu đề mục"
    return "nối tiếp dòng chú thích/văn xuôi cùng hàng (≤ 40 pt)"


def _meets_label_standard(p: dict, ln: dict) -> bool:
    """The line looks like a label (`_label_lines`) or its block is a short axis label."""
    if ln["label_like"]:
        return True
    return ln["owner"] >= 0 and bool(p["blocks"][ln["owner"]]["short_axis"])


def _picture_caption(p: dict, gi: int):
    """(caption index, caption rect, side) of the nearest Caption within 100 pt above or below Picture `gi`."""
    pic = p["gt"][gi]["r"]
    best = None
    for k, c in enumerate(p["gt"]):
        if c["c"] != "Caption":
            continue
        cr = c["r"]
        if min(pic[2], cr[2]) - max(pic[0], cr[0]) <= 0:
            continue
        side = "below" if cr[1] >= pic[3] - 2 else "above" if cr[3] <= pic[1] + 2 else None
        d = rect_gap(pic, cr)
        if side and d <= 100 and (best is None or d < best[0]):
            best = (d, k, cr, side)
    return best[1:] if best else None


def _window(d: float) -> str:
    return "≤ 64" if d <= 64 else "64–96 (cần cầu)" if d <= 96 else "> 96 (ngoài vùng tìm)"


def s8_labels_before_caption(pages: list[dict]) -> dict:
    """Labels lying between the visible part and its caption: what taking them first does to the caption gap."""
    n = with_band = 0
    before, after, shrink = [], [], []
    moved = collections.Counter()
    for p in pages:
        for gi, g in enumerate(p["gt"]):
            if g["c"] != "Picture":
                continue
            cap = _picture_caption(p, gi)
            imgs, drs = picture_parts(p, gi)
            core = union(imgs + drs)
            if not cap or core is None:
                continue
            _ci, cr, side = cap
            n += 1
            x0, x1 = max(core[0], cr[0]), min(core[2], cr[2])
            y0, y1 = (core[3], cr[1]) if side == "below" else (cr[3], core[1])
            band = [ln["r"] for ln in p["lines"] if ln["gt"] == "Picture" and ln["gi"] == gi
                    and x0 - 20 <= centre(ln["r"])[0] <= x1 + 20 and y0 <= centre(ln["r"])[1] <= y1]
            d0 = rect_gap(core, cr)
            d1 = rect_gap(union([core] + band), cr)
            before.append(d0)
            after.append(d1)
            if band:
                with_band += 1
                shrink.append(d0 - d1)
                if side == "below":
                    moved[f"{_window(d0)} → {_window(d1)}"] += 1
    return {"pictures": n, "with_band_labels": with_band, "gap_before": quantiles(before), "gap_after": quantiles(after),
            "moved": dict(moved), "shrink": quantiles(shrink)}


def s9_uncaptioned_raster(pages: list[dict]) -> dict:
    """Raster pictures without a caption, and images that are not figures at all: labels vs label-like strangers."""
    rows = collections.defaultdict(collections.Counter)
    non_fig = collections.Counter()
    non_fig_near = collections.Counter()
    for p in pages:
        for gi, g in enumerate(p["gt"]):
            if g["c"] != "Picture":
                continue
            imgs, drs = picture_parts(p, gi)
            if not imgs:
                continue
            if any(not any(inside(centre(d), im, 2.0) for im in imgs) for d in drs):
                continue  # hybrid
            core = union(imgs + drs)
            key = "raster có chú thích" if any(
                c["c"] == "Caption" and rect_gap(g["r"], c["r"]) <= 100 for c in p["gt"]) else "raster không chú thích"
            row = rows[key]
            row["hình"] += 1
            labs = [ln for ln in p["lines"] if ln["gt"] == "Picture" and ln["gi"] == gi and not inside(centre(ln["r"]), core)]
            row["có nhãn ngoài"] += bool(labs)
            row["dòng nhãn ngoài"] += len(labs)
            row["dòng nhãn ≤ 16 pt"] += sum(1 for ln in labs if rect_gap(ln["r"], core) <= 16)
            lure = [ln for ln in p["lines"] if ln["gt"] != "Picture" and rect_gap(ln["r"], core) <= 16
                    and _meets_label_standard(p, ln)]
            row["có chữ lạ đạt chuẩn ≤ 16 pt"] += bool(lure)
            row["dòng chữ lạ đạt chuẩn ≤ 16 pt"] += len(lure)
        for im in p["images"]:
            if im["gt"] == "Picture" or area(im["r"]) < 1600 or im["ink"] == []:
                continue
            r = im["ink"] or im["r"]
            non_fig[im["gt"]] += 1
            non_fig_near[im["gt"]] += sum(1 for ln in p["lines"] if ln["gt"] != "Picture" and rect_gap(ln["r"], r) <= 16
                                          and not inside(centre(ln["r"]), r) and _meets_label_standard(p, ln))
    return {"rows": {k: dict(v) for k, v in rows.items()}, "non_figure_images": dict(non_fig),
            "non_figure_near_label_like": dict(non_fig_near)}


def _caption_head(text: str, k: int) -> str:
    """First `k` words with digits masked: 'Figure 3 shows ...' -> 'Figure # shows'."""
    return " ".join(re.sub(r"\d+", "#", text).split()[:k])


def s10_caption_kinds(pages: list[dict]) -> dict:
    """Blocks the tool calls a figure caption that are not captions, and figure captions it misses."""
    false_next = collections.Counter()
    false_by_cls = collections.Counter()
    missed = collections.Counter()
    found = n_caps = 0
    for p in pages:
        for b in p["blocks"]:
            if b["kind"] == "fig_caption" and b["gt"] != "Caption" and b["share"] >= 0.5:
                false_by_cls[b["gt"]] += 1
                ws = _caption_head(b["text"], 3).split()
                false_next[ws[2] if len(ws) > 2 else "(hết khối)"] += 1
        for gi, g in enumerate(p["gt"]):
            if g["c"] != "Picture":
                continue
            cap = _picture_caption(p, gi)
            if not cap:
                continue
            mine = [b for b in p["blocks"] if b["gi"] == cap[0] and b["gt"] == "Caption"]
            if not mine:
                continue
            n_caps += 1
            if any(b["kind"] == "fig_caption" for b in mine):
                found += 1
                continue
            first = min(mine, key=lambda b: (b["r"][1], b["r"][0]))
            missed[f"{_caption_head(first['text'], 2)} → {first['kind']}"] += 1
    return {"false_by_class": dict(false_by_cls), "false_next_word": dict(false_next.most_common(15)),
            "figure_captions": n_caps, "found": found, "missed_heads": dict(missed.most_common(15))}


def s3_raster(pages: list[dict]) -> dict:
    margins = collections.defaultdict(list)
    gt_vs_ink = collections.defaultdict(list)
    gt_vs_place = collections.defaultdict(list)
    stats = collections.Counter()
    margin_text_cls = collections.Counter()
    margin_label_gap = []
    for p in pages:
        for im in p["images"]:
            if im["gt"] != "Picture" or not im["ink"]:
                continue
            pl, ink = im["r"], im["ink"]
            stats["images_in_pictures"] += 1
            if area(ink) >= (1 - TRIM_MIN_GAIN) * area(pl):
                continue
            stats["trimmed"] += 1
            for s, v in (("left", ink[0] - pl[0]), ("right", pl[2] - ink[2]), ("top", ink[1] - pl[1]),
                         ("bottom", pl[3] - ink[3])):
                margins[s].append(v)
            pic = p["gt"][im["gi"]]["r"]
            if sum(1 for o in p["images"] if o["gi"] == im["gi"]) > 1 or any(
                    inside(centre(d[0]), pic) for d in p["drawings"] if area(d[0]) > 0.05 * area(pic)):
                single = False  # several images or sizeable drawings: the Picture box is not about this image
            else:
                single = True
                stats["single_image_pictures"] += 1
            for s, a, b in (("left", ink[0] - pic[0], pl[0] - pic[0]), ("right", pic[2] - ink[2], pic[2] - pl[2]),
                            ("top", ink[1] - pic[1], pl[1] - pic[1]), ("bottom", pic[3] - ink[3], pic[3] - pl[3])):
                if single:
                    gt_vs_ink[s].append(a)
                    gt_vs_place[s].append(b)
            in_margin = [ln for ln in p["lines"] if inside(centre(ln["r"]), pl) and not inside(centre(ln["r"]), ink)]
            own = [ln for ln in in_margin if ln["gt"] == "Picture" and ln["gi"] == im["gi"]]
            other = [ln for ln in in_margin if not (ln["gt"] == "Picture" and ln["gi"] == im["gi"])]
            stats["with_own_label_in_margin"] += bool(own)
            stats["with_foreign_text_in_margin"] += bool(other)
            stats["margin_empty"] += not in_margin
            for ln in own:
                margin_label_gap.append(rect_gap(ln["r"], ink))
            for ln in other:
                margin_text_cls[ln["gt"]] += 1
    return {"stats": dict(stats), "margins": {s: quantiles(v) for s, v in margins.items()},
            "gt_vs_ink": {s: quantiles(v) for s, v in gt_vs_ink.items()},
            "gt_vs_place": {s: quantiles(v) for s, v in gt_vs_place.items()},
            "margin_text_cls": dict(margin_text_cls), "margin_label_gap": quantiles(margin_label_gap),
            "margin_label_within": within(margin_label_gap)}


def s4_ribbons(pages: list[dict]) -> dict:
    excess = []
    pics_any = pics = 0
    for p in pages:
        for gi, g in enumerate(p["gt"]):
            if g["c"] != "Picture":
                continue
            pics += 1
            worst = 0.0
            for r, u, *_ in p["drawings"]:
                if u is None or not inside(centre(r), g["r"]):
                    continue
                e = max(r[0] - u[0], u[2] - r[2], r[1] - u[1], u[3] - r[3])
                excess.append(e)
                worst = max(worst, e)
            pics_any += worst >= 3.0
    return {"pictures": pics, "pictures_ribbon_3pt": pics_any, "excess": quantiles(excess)}


def s5_captions(pages: list[dict]) -> dict:
    gaps = collections.defaultdict(list)
    hov = collections.defaultdict(list)
    between = collections.Counter()
    between_words = []
    none_100 = none_150 = pics = 0
    cap_kind = collections.Counter()
    for p in pages:
        caps = [g for g in p["gt"] if g["c"] == "Caption"]
        for g in p["gt"]:
            if g["c"] != "Picture":
                continue
            pics += 1
            pic = g["r"]
            best = None
            for c in caps:
                d = rect_gap(pic, c["r"])
                if best is None or d < best[0]:
                    best = (d, c)
            if best is None or best[0] > 150:
                none_150 += 1
            if best is None or best[0] > 100:
                none_100 += 1
                continue
            d, c = best
            cr = c["r"]
            h = max(0.0, min(pic[2], cr[2]) - max(pic[0], cr[0]))
            if h > 0 and cr[1] >= pic[3] - 2:
                side, band = "below", [max(pic[0], cr[0]), pic[3], min(pic[2], cr[2]), cr[1]]
            elif h > 0 and cr[3] <= pic[1] + 2:
                side, band = "above", [max(pic[0], cr[0]), cr[3], min(pic[2], cr[2]), pic[1]]
            else:
                side, band = "side", None
            gaps[side].append(d)
            hov[side].append(h / max(1e-6, min(pic[2] - pic[0], cr[2] - cr[0])))
            if band and band[3] - band[1] > 1:
                words = 0
                for o in p["gt"]:
                    if o is g or o is c:
                        continue
                    if overlap(o["r"], band) > 0.3 * max(1e-6, area(o["r"])):
                        between[o["c"]] += 1
                for ln in p["lines"]:
                    if ln["gt"] not in ("Picture", "Caption") and inside(centre(ln["r"]), band):
                        words += ln["nw"]
                between_words.append(words)
        for b in p["blocks"]:
            if b["share"] >= 0.5:
                if b["gt"] == "Caption":
                    cap_kind["Caption -> " + b["kind"]] += 1
                elif b["kind"] == "fig_caption":
                    cap_kind["fig_caption block in " + b["gt"]] += 1
    return {"pictures": pics, "no_caption_100pt": none_100, "no_caption_150pt": none_150,
            "gap": {s: quantiles(v) for s, v in gaps.items()}, "gap_within": {s: within(v) for s, v in gaps.items()},
            "h_overlap": {s: quantiles(v) for s, v in hov.items()}, "between_classes": dict(between),
            "between_words": quantiles(between_words), "caption_kind": dict(cap_kind)}


def s6_parts(pages: list[dict]) -> dict:
    intra_max, intra_all, inter = [], [], []
    multi = pics = 0
    for p in pages:
        comps_of = {}
        if p.get("drawings_dropped"):
            continue  # parts past the cap are only kept as one union: no part structure
        for gi, g in enumerate(p["gt"]):
            if g["c"] != "Picture":
                continue
            imgs, drs = picture_parts(p, gi)
            parts = imgs + drs
            if not parts:
                continue
            pics += 1
            boxes = [union([parts[k] for k in grp]) for grp in components(parts, PART_TOL)]
            comps_of[gi] = boxes
            if len(boxes) >= 2:
                multi += 1
                edges = mst_edges(boxes)
                intra_all.extend(edges)
                intra_max.append(max(edges))
        keys = list(comps_of)
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                inter.append(min(axis_gap(x, y) for x in comps_of[a] for y in comps_of[b]))
    steps = (5, 10, 15, 20, 30, 40, 50, 60, 68, 74, 80, 100, 150)
    return {"pictures": pics, "multi_part": multi, "intra_max": quantiles(intra_max), "intra_edges": quantiles(intra_all),
            "inter": quantiles(inter), "intra_max_within": within(intra_max, steps), "inter_within": within(inter, steps)}


def s7_margins(pages: list[dict]) -> dict:
    head, foot, head_rel, foot_rel, head_pic, foot_pic = [], [], [], [], [], []
    for p in pages:
        pics = [g["r"] for g in p["gt"] if g["c"] == "Picture"]
        for g in p["gt"]:
            r = g["r"]
            if g["c"] == "Page-header":
                head.append(r[3])
                head_rel.append(100.0 * r[3] / p["h"])
                if pics:
                    head_pic.append(min(rect_gap(r, q) for q in pics))
            elif g["c"] == "Page-footer":
                foot.append(p["h"] - r[1])
                foot_rel.append(100.0 * (p["h"] - r[1]) / p["h"])
                if pics:
                    foot_pic.append(min(rect_gap(r, q) for q in pics))
    return {"header_bottom_pt": quantiles(head), "header_bottom_pct": quantiles(head_rel),
            "footer_top_from_bottom_pt": quantiles(foot), "footer_top_from_bottom_pct": quantiles(foot_rel),
            "header_to_picture": quantiles(head_pic), "footer_to_picture": quantiles(foot_pic)}


# ==============================================================================
# Report
# ==============================================================================


def _qrow(name: str, q: dict) -> str:
    if not q.get("n"):
        return f"| {name} | 0 | | | | | | |"
    return f"| {name} | {q['n']} | {q['p1']} | {q['p10']} | {q['p50']} | {q['p90']} | {q['p99']} | {q['max']} |"


QHEAD = "| | n | p1 | p10 | p50 | p90 | p99 | max |\n| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"


def _within_table(cols: dict[str, list[tuple[float, float]]], title: str) -> list[str]:
    names = list(cols)
    out = [f"| {title} | " + " | ".join(names) + " |", "| ---: | " + " | ".join("---:" for _ in names) + " |"]
    steps = [s for s, _ in next(iter(cols.values()))] if cols else []
    for i, s in enumerate(steps):
        out.append(f"| ≤ {s} | " + " | ".join(f"{cols[n][i][1]}%" for n in names) + " |")
    return out


def write_report(res: dict, meta: dict, path: Path) -> None:
    L = [f"# DocLayNet: thống kê cho bộ dò hình — {meta['label']}", "",
         f"{meta['pages']} trang (bỏ trang xoay và trang lỗi). Dữ kiện: {meta['facts']}. "
         "Mọi khoảng cách tính bằng pt. Ngưỡng chỉ được chọn trên `tune`.", ""]

    s1 = res["s1"]
    L += ["## 1. Khối chữ theo loại DocLayNet", "",
          "Khối chữ = `TextBlock` của công cụ, gắn với khung DocLayNet chứa tâm của nó (chỉ khối nằm ≥ 50% trong khung đó). "
          "`Picture` = chữ nằm trong hình, tức nhãn.", ""]
    L += ["Số khối: " + ", ".join(f"{c} {s1['flags'].get(c, {}).get('n', 0)}" for c in CLASS_ORDER) + ".",
          "Khối lai (dưới 50% trong một khung): " + ", ".join(f"{c} {n}" for c, n in sorted(s1["mixed"].items())) + ".", ""]
    for feat in ("wc", "rows", "width", "height", "size", "size_rel", "width_rel", "chars_per_line", "lower_frac",
                 "alpha_frac", "digit_frac", "gap_em", "score"):
        L += [f"### {feat}", "", QHEAD]
        L += [_qrow(c, s1["dist"].get(c, {}).get(feat, {})) for c in CLASS_ORDER if c in s1["dist"]]
        L.append("")
    L += ["### Tỷ lệ cờ theo loại (%)", "",
          "| loại | n | kind=text | short_axis | label_row | heading_re | kết thúc '.' | cùng phông trang | văn bản chính |",
          "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for c in CLASS_ORDER:
        f = s1["flags"].get(c)
        if not f:
            continue
        n = max(1, f["n"])
        pct = lambda k: round(100.0 * f.get(k, 0) / n, 1)  # noqa: E731
        L.append(f"| {c} | {f['n']} | {pct('kind=text')} | {pct('short_axis')} | {pct('label_row')} | {pct('heading_re')} | "
                 f"{pct('period')} | {pct('same_font')} | {pct('main_text')} |")
    L += ["", "### Các định nghĩa \"đoạn văn\" và phép thử nhãn hiện có: tỷ lệ khối (kind=text) bị gọi là ... (%)", ""]
    g = list(s1["group_n"])
    L += ["| định nghĩa | " + " | ".join(f"{x} (n={s1['group_n'][x]})" for x in g) + " |",
          "| :--- | " + " | ".join("---:" for _ in g) + " |"]
    for name, row in s1["defs"].items():
        L.append(f"| {name} | " + " | ".join(str(row[x]) for x in g) + " |")
    L += ["", "### Tách nhãn khỏi văn bản thân bài bằng một ngưỡng", ""]
    for name, rows in s1["sep"].items():
        L += [f"**{name}**", "", "| t | nhãn ≥ t | n nhãn | thân bài ≥ t | n thân bài |", "| ---: | ---: | ---: | ---: | ---: |"]
        L += [f"| {t} | {a}% | {na} | {b}% | {nb} |" for t, a, na, b, nb in rows]
        L.append("")

    s2 = res["s2"]
    L += ["## 2. Nhãn nằm ngoài phần nhìn thấy của hình", "",
          "Phần nhìn thấy = hợp các ảnh (đã xén trắng như công cụ) và nét vẽ (đã cắt clip) có tâm trong khung Picture. "
          "Nhãn = dòng chữ thuộc Picture có tâm nằm ngoài phần nhìn thấy.", "",
          f"Hình: {s2['pictures']} (trong đó {s2['capped']} hình trên trang quá {MAX_DRAWINGS} nét vẽ: phần vượt được gộp thành một khung); có phần nhìn thấy {s2['with_visible_part']}; chỉ có chữ {s2['text_only']}; "
          f"có nhãn ngoài phần nhìn thấy {s2['with_labels_outside']}. Dòng nhãn nằm trên phần nhìn thấy: {s2['label_lines_on_graphic']}.", "",
          "### Khung Picture vượt ra ngoài phần nhìn thấy, mỗi phía (dương = Picture lớn hơn)", "", QHEAD]
    L += [_qrow(s, q) for s, q in s2["gt_beyond_core"].items()]
    L += ["", "### Khoảng cách dòng nhãn đến phần nhìn thấy", "", QHEAD,
          _qrow("trực tiếp", s2["label_gap"]), _qrow("nối chuỗi (bước lớn nhất)", s2["label_chain_gap"])]
    L += [_qrow(f"phía {s} ({s2['label_side'].get(s, 0)})", q) for s, q in s2["label_side_gap"].items()]
    L += ["", "### Đặc điểm dòng nhãn ngoài phần nhìn thấy", "", QHEAD]
    L += [_qrow(k, q) for k, q in s2["label_props"].items()]
    lf = s2["label_flags"]
    n = max(1, lf.get("n", 0))
    L += ["", f"Trong {lf.get('n', 0)} dòng nhãn: trông như nhãn (`_label_lines`) {round(100 * lf.get('label_like', 0) / n, 1)}%, "
          f"khối chứa là nhãn trục ngắn {round(100 * lf.get('owner_short_axis', 0) / n, 1)}%, "
          f"khối chứa ≥ 12 từ {round(100 * lf.get('owner_wc>=12', 0) / n, 1)}%, "
          f"khối chứa là văn bản chính {round(100 * lf.get('owner_main_text', 0) / n, 1)}%.", ""]
    L += ["### Chữ không thuộc hình nằm gần phần nhìn thấy (≤ 80 pt)", "", QHEAD]
    L += [_qrow(f"{c}", s2["foreign"][c]) for c in CLASS_ORDER if c in s2["foreign"]]
    L += ["", "### Tỷ lệ cộng dồn theo khoảng cách: nhãn (trực tiếp / nối chuỗi) và chữ không thuộc hình", ""]
    cols = {"nhãn": s2["label_within"], "nhãn nối chuỗi": s2["label_chain_within"]}
    for c in ("Caption", "Text", "List-item", "Formula", "Section-header", "Page-header", "Page-footer", "none"):
        if c in s2["foreign_within"]:
            cols[f"{c} (n={s2['foreign_n'][c]})"] = s2["foreign_within"][c]
    L += _within_table(cols, "khoảng cách")
    L += ["### Theo loại hình", "",
          "Raster thuần: chỉ có ảnh (nét vẽ nằm trên ảnh không tính). Vector thuần: không có ảnh. Lai: cả hai. "
          "Có chú thích: Caption cách khung Picture ≤ 100 pt.", "",
          "| loại | hình | có chú thích | có nhãn ngoài | có nhãn ngoài và có chú thích | dòng nhãn | khoảng cách p50 / p90 / p99 | nối chuỗi p50 / p90 / p99 |",
          "| :--- | ---: | ---: | ---: | ---: | ---: | :--- | :--- |"]
    for k in ("raster", "hybrid", "vector"):
        v = s2["kinds"].get(k)
        if not v:
            continue
        g, c = v["gap"], v["chain"]
        fmt = lambda q: f"{q['p50']} / {q['p90']} / {q['p99']}" if q.get("n") else ""  # noqa: E731
        L.append(f"| {k} | {v['pictures']} | {v['captioned']} | {v['with_labels']} | {v['captioned_with_labels']} | "
                 f"{g.get('n', 0)} | {fmt(g)} | {fmt(c)} |")
    L += ["", "### Chuẩn nhãn + khoảng cách nối chuỗi: bao nhiêu nhãn lấy được, bao nhiêu dòng lạ lọt vào", "",
          f"Chuẩn nhãn = dòng trông như nhãn (`_label_lines`) hoặc khối chứa là nhãn trục ngắn. Khoảng cách đo theo bước nối "
          f"chuỗi qua các nhãn của hình. Cột nhãn tính % trên {s2['combo_n_labels']} dòng nhãn; cột dòng lạ là số dòng.", ""]
    grps = [g for g in ("Caption", "Text, List-item", "khác") if s2["combo"] and g in s2["combo"][0]]
    L += ["| ≤ t | nhãn (mọi) | nhãn đạt chuẩn | " + " | ".join(f"{g}: mọi / đạt chuẩn" for g in grps) + " |",
          "| ---: | ---: | ---: | " + " | ".join("---:" for _ in grps) + " |"]
    for row in s2["combo"]:
        L.append(f"| {row['t']} | {row['labels']}% | {row['labels_std']}% | " +
                 " | ".join(f"{row[g]} / {row[g + ' std']}" for g in grps) + " |")
    L.append("")
    sides = [s for s in SIDES if s != "overlap"]
    L += ["", "### Theo từng phía: % nhãn trong ngưỡng / số dòng chữ không thuộc hình trong cùng ngưỡng", "",
          "| ≤ t | " + " | ".join(f"{s} ({s2['label_side'].get(s, 0)} nhãn)" for s in sides) + " |",
          "| ---: | " + " | ".join("---:" for _ in sides) + " |"]
    for i, t in enumerate(DIST_STEPS):
        L.append(f"| {t} | " + " | ".join(f"{s2['side_sep'][s][i][1]}% / {s2['side_sep'][s][i][2]}" for s in sides) + " |")
    L += [""] + [f"- chữ lạ phía {s}: {s2['foreign_side_cls'].get(s, {})}" for s in sides] + [""]

    s3 = res["s3"]
    st = s3["stats"]
    L += ["## 3. Ảnh raster: lề trắng và chữ đè lên lề", "",
          f"Ảnh trong Picture có thể xén: {st.get('images_in_pictures', 0)}; xén được ≥ 3%: {st.get('trimmed', 0)}. "
          f"Trong số ảnh được xén: lề hoàn toàn trống {st.get('margin_empty', 0)}, có nhãn của chính hình đè lên lề "
          f"{st.get('with_own_label_in_margin', 0)}, có chữ không thuộc hình trên lề {st.get('with_foreign_text_in_margin', 0)} "
          f"(loại: {s3['margin_text_cls']}).", "", "### Lề trắng bị xén, mỗi phía", "", QHEAD]
    L += [_qrow(s, q) for s, q in s3["margins"].items()]
    L += ["", f"### Khung Picture so với phần đã xén (dương = Picture lớn hơn; chỉ {st.get('single_image_pictures', 0)} hình gồm đúng một ảnh)", "", QHEAD]
    L += [_qrow(s, q) for s, q in s3["gt_vs_ink"].items()]
    L += ["", "### Khung Picture so với khung đặt ảnh (dương = Picture lớn hơn)", "", QHEAD]
    L += [_qrow(s, q) for s, q in s3["gt_vs_place"].items()]
    L += ["", "### Nhãn đè lên lề: khoảng cách đến phần đã xén", "", QHEAD, _qrow("nhãn trên lề", s3["margin_label_gap"]), ""]

    s4 = res["s4"]
    L += ["## 4. Nét vẽ bị clip cắt (ruy băng) trong hình", "",
          f"Hình có nét vượt clip ≥ 3 pt: {s4['pictures_ribbon_3pt']} / {s4['pictures']}.", "", QHEAD,
          _qrow("phần vượt clip (pt, phía lớn nhất)", s4["excess"]), ""]

    s5 = res["s5"]
    L += ["## 5. Hình và chú thích", "",
          f"Hình: {s5['pictures']}; không có Caption trong 100 pt: {s5['no_caption_100pt']}; trong 150 pt: {s5['no_caption_150pt']}.", "",
          "### Khoảng cách đến Caption gần nhất", "", QHEAD]
    L += [_qrow(s, q) for s, q in s5["gap"].items()]
    L += ["", "### Độ trùng ngang/dọc (so với cạnh nhỏ hơn)", "", QHEAD]
    L += [_qrow(s, q) for s, q in s5["h_overlap"].items()]
    L += ["", f"Khung nằm giữa hình và chú thích: {s5['between_classes']}.", "", QHEAD,
          _qrow("số từ không thuộc hình/chú thích nằm giữa", s5["between_words"]), "",
          f"Bộ phân loại chú thích của công cụ: {s5['caption_kind']}.", ""]
    L += _within_table(s5["gap_within"], "khoảng cách")
    L.append("")

    s6 = res["s6"]
    L += ["## 6. Hình nhiều phần", "",
          f"Hình có phần nhìn thấy: {s6['pictures']}; gồm ≥ 2 mảnh (nối trong 5 pt): {s6['multi_part']}.", "", QHEAD,
          _qrow("khe lớn nhất phải nối trong một hình", s6["intra_max"]), _qrow("mọi khe nối trong một hình", s6["intra_edges"]),
          _qrow("khe giữa hai hình khác nhau", s6["inter"]), ""]
    L += _within_table({"khe trong một hình": s6["intra_max_within"], "khe giữa hai hình": s6["inter_within"]}, "khe")
    L.append("")

    s7 = res["s7"]
    L += ["## 7. Đầu trang và chân trang", "", QHEAD,
          _qrow("đáy Page-header (pt từ đỉnh)", s7["header_bottom_pt"]), _qrow("đáy Page-header (% trang)", s7["header_bottom_pct"]),
          _qrow("đỉnh Page-footer (pt từ đáy)", s7["footer_top_from_bottom_pt"]),
          _qrow("đỉnh Page-footer (% trang)", s7["footer_top_from_bottom_pct"]),
          _qrow("Page-header đến hình gần nhất", s7["header_to_picture"]),
          _qrow("Page-footer đến hình gần nhất", s7["footer_to_picture"]), ""]
    s8 = res["s8"]
    L += ["## 8. Nhãn nằm giữa hình và chú thích", "",
          f"Hình có chú thích trên/dưới (≤ 100 pt) và có phần nhìn thấy: {s8['pictures']}; có dòng nhãn nằm trong dải giữa "
          f"phần nhìn thấy và chú thích: {s8['with_band_labels']}.", "", QHEAD,
          _qrow("khoảng cách đến chú thích, đo từ phần nhìn thấy", s8["gap_before"]),
          _qrow("đo từ phần nhìn thấy + nhãn trong dải", s8["gap_after"]),
          _qrow("khoảng rút ngắn (hình có nhãn trong dải)", s8["shrink"]), "",
          "Chú thích dưới, hình có nhãn trong dải: vùng tìm trước → sau khi gom nhãn: " +
          ", ".join(f"{k}: {v}" for k, v in sorted(s8["moved"].items())) + ".", ""]
    s9 = res["s9"]
    keys = ["hình", "có nhãn ngoài", "dòng nhãn ngoài", "dòng nhãn ≤ 16 pt", "có chữ lạ đạt chuẩn ≤ 16 pt",
            "dòng chữ lạ đạt chuẩn ≤ 16 pt"]
    L += ["## 9. Ảnh raster không chú thích, và ảnh không phải hình", "",
          "Raster thuần (như mục 2). Chữ lạ đạt chuẩn = dòng không thuộc hình, đạt chuẩn nhãn, cách phần đã xén ≤ 16 pt.", "",
          "| | " + " | ".join(keys) + " |", "| :--- | " + " | ".join("---:" for _ in keys) + " |"]
    for k, row in sorted(s9["rows"].items()):
        L.append(f"| {k} | " + " | ".join(str(row.get(x, 0)) for x in keys) + " |")
    L += ["", f"Ảnh ≥ 1600 pt² không nằm trong Picture, theo loại khung DocLayNet chứa nó: {s9['non_figure_images']}; "
          f"số dòng chữ lạ đạt chuẩn nhãn trong 16 pt quanh chúng: {s9['non_figure_near_label_like']}.", ""]
    s10 = res["s10"]
    L += ["## 10. Phân loại chú thích hình", "",
          f"Chú thích của Picture (Caption gần nhất trên/dưới ≤ 100 pt): {s10['figure_captions']}; công cụ nhận ra là "
          f"`fig_caption` {s10['found']}.", "",
          f"Chú thích bị bỏ sót, theo hai từ đầu (số thay bằng #) → loại công cụ gán: {s10['missed_heads']}.", "",
          f"Khối `fig_caption` nằm ngoài Caption, theo loại: {s10['false_by_class']}; từ đứng sau \"Figure #\": "
          f"{s10['false_next_word']}.", ""]
    L += ["## 11. Vì sao dòng nhãn trượt `_label_lines`", "",
          "Dòng nhãn ngoài phần nhìn thấy mà `_label_lines` không nhận, theo điều kiện đầu tiên làm nó trượt (xấp xỉ, "
          "theo thứ tự kiểm tra của hàm):", "", "| lý do | dòng |", "| :--- | ---: |"]
    L += [f"| {k} | {v} |" for k, v in sorted(s2["label_miss"].items(), key=lambda kv: -kv[1])]
    L += ["", "## 12. Chữ lạ đạt chuẩn nhãn trong bước nối chuỗi 16 pt: chốt nào hiện có chặn được", "",
          "Xấp xỉ các chốt của bước lấy nhãn; \"trong bảng\" dùng khung Table của DocLayNet thay cho bộ tìm bảng.", ""]
    cats = ["dải 10% đầu / 6% cuối", "khối chú thích", "văn bản chính", "khối ≥ 12 từ", "trong bảng (khung DocLayNet)",
            "không chốt nào"]
    L += ["| loại | " + " | ".join(cats) + " |", "| :--- | " + " | ".join("---:" for _ in cats) + " |"]
    for c in CLASS_ORDER:
        b = s2["blockers"].get(c)
        if b:
            L.append(f"| {c} | " + " | ".join(str(b.get(x, 0)) for x in cats) + " |")
    L.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--subset", action="append", choices=SUBSETS, help="Repeatable; default: tune")
    ap.add_argument("--collection", default=None, help="arxiv_doublespaced | arxiv_mediumspaced | arxiv_two_columns")
    ap.add_argument("--facts", default=None, help="Facts folder name under <cache-dir>/facts (default: v<FACTS_VERSION>)")
    ap.add_argument("--docs", type=Path, default=None, help="Text file of document names (one per line) to keep")
    ap.add_argument("--cache-dir", type=Path, default=Path(tempfile.gettempdir()) / "luka_doclaynet_eval")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "work-dev" / "doclaynet_stats")
    args = ap.parse_args(argv)
    subsets = args.subset or ["tune"]
    docs = set(args.docs.read_text(encoding="utf-8").split()) if args.docs else None
    pages = load_pages(args.cache_dir, subsets, args.collection, args.facts, docs)
    if not pages:
        raise SystemExit("No facts found: run dev/doclaynet_facts.py first")
    res = {"s1": s1_text_blocks(pages), "s2": s2_labels(pages), "s3": s3_raster(pages), "s4": s4_ribbons(pages),
           "s5": s5_captions(pages), "s6": s6_parts(pages), "s7": s7_margins(pages),
           "s8": s8_labels_before_caption(pages), "s9": s9_uncaptioned_raster(pages), "s10": s10_caption_kinds(pages)}
    label = "+".join(subsets) + (f" · {args.collection}" if args.collection else "") + (f" · {args.facts}" if args.facts else "") + (f" · tài liệu trong {args.docs.name}" if args.docs else "")
    stem = "report_" + "+".join(subsets) + (f"_{args.collection}" if args.collection else "") + (f"_{args.facts}" if args.facts else "") + (f"_{args.docs.stem}" if args.docs else "")
    meta = {"label": label, "pages": len(pages), "facts": args.facts or f"v{FACTS_VERSION}"}
    write_report(res, meta, args.out / f"{stem}.md")
    (args.out / f"{stem}.json").write_text(json.dumps({"meta": meta, **res}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(pages)} pages -> {args.out / (stem + '.md')}")


if __name__ == "__main__":
    main()
