"""Core packaging, HTML QA, transcript lookup, and headless PDF export logic for luka-loop."""

from __future__ import annotations

import base64
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Callable

from path_guards import (
    assert_local_no_unc_path,
    assert_safe_output_path,
    file_uri_to_local_path,
    get_repo_root,
    get_tools_dir,
    resolve_safe_sub_image_path,
    safe_clean_dir,
)

IMG_TAG_RX = re.compile(r'(?is)<img\b((?:[^>"\']|"[^"]*"|\'[^\']*\')*)>')
IMG_SRC_RX = re.compile(r'(?is)((?:^|\s)src\s*=\s*)(?:"([^"]*)"|\'([^\']*)\'|([^\s"\'=<>`]+))')
_DATA_IMG_RX = re.compile(r"^data:image/(?:png|jpeg|jpg|webp);base64,", re.IGNORECASE)
_EXT_IMG_RX = re.compile(r"(?i)^(?:data:|https?://)")
_LOCAL_OPT_EXT_RX = re.compile(r"(?i)\.(?:png|jpe?g)$")
_STRIP_SCRIPT_STYLE_RX = re.compile(r"(?is)<(?:script|style)\b[^>]*>.*?</(?:script|style)>")
_STRIP_PRE_RX = re.compile(r"(?is)<pre\b[^>]*>.*?</pre>")
_STRIP_CODE_RX = re.compile(r"(?is)<code\b[^>]*>.*?</code>")
_STRIP_TEXTAREA_RX = re.compile(r"(?is)<textarea\b[^>]*>.*?</textarea>")
_DATA_URI_PAYLOAD_RX = re.compile(r"(?i)(data:image/[a-z0-9.+-]+;base64,)[A-Za-z0-9+/=\s]+")


def _resolve_pdf_from_line(line: str) -> str | None:
    if '"type"' not in line or "USER_INPUT" not in line or "pdf" not in line.lower():
        return None
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(entry, dict) or entry.get("type") != "USER_INPUT":
        return None
    media = entry.get("media")
    if not isinstance(media, list):
        return None
    for item in media:
        if not isinstance(item, dict):
            continue
        uri = str(item.get("uri") or "")
        mime = str(item.get("mime_type") or "")
        if uri and (mime == "application/pdf" or uri.lower().endswith(".pdf")):
            assert_local_no_unc_path(uri, "TranscriptMediaUri")
            return file_uri_to_local_path(uri)
    return None


def find_latest_pdf_in_transcript(transcript_path: str | Path) -> Path:
    """Locate the most recent USER_INPUT PDF attachment inside transcript.jsonl."""
    assert_local_no_unc_path(transcript_path, "-TranscriptPath")
    raw = str(transcript_path or "").strip()
    if not raw or not os.path.isfile(raw):
        raise FileNotFoundError(f"Transcript file not found: {transcript_path}")
    abs_transcript = Path(os.path.abspath(raw))
    assert_local_no_unc_path(abs_transcript, "-TranscriptPath")

    lines = abs_transcript.read_text(encoding="utf-8-sig").splitlines()
    for line in reversed(lines):
        found = _resolve_pdf_from_line(line)
        if found:
            assert_local_no_unc_path(found, "ResolvedPdf")
            if not os.path.isfile(found):
                raise FileNotFoundError(f"Resolved PDF file does not exist: {found}")
            return Path(os.path.abspath(found))
    raise RuntimeError(f"No PDF attachment found in USER_INPUT entries of transcript: {abs_transcript}")


def limit_manifest_words(text: str | None, max_words: int = 20) -> str:
    """Truncate caption/context text cleanly to `max_words` words for compact stdout output."""
    if text is None:
        return ""
    normalized = re.sub(r"[\x00-\x1F]+", " ", str(text)).strip()
    if not normalized or max_words <= 0:
        return normalized
    words = normalized.split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]) + "..."


def emit_compacted_manifest_stdout(
    manifest_dict: dict,
    manifest_path: Path,
    max_words: int = 20,
    max_bytes: int = 16384,
) -> None:
    """Print compacted manifest JSON to stdout when within `max_bytes`, otherwise print disk path."""
    compacted = copy.deepcopy(manifest_dict)
    if max_words > 0:
        for fig in compacted.get("figures", []):
            if isinstance(fig, dict):
                if fig.get("caption") is not None:
                    fig["caption"] = limit_manifest_words(str(fig["caption"]), max_words=max_words)
                if fig.get("context") is not None:
                    fig["context"] = limit_manifest_words(str(fig["context"]), max_words=max_words)

    stdout_json = json.dumps(compacted, ensure_ascii=False, indent=2)
    stdout_bytes = len(stdout_json.encode("utf-8"))
    if stdout_bytes <= max_bytes:
        print("=== MANIFEST JSON START ===")
        print(stdout_json)
        print("=== MANIFEST JSON END ===")
    else:
        print(
            f"Manifest too large for stdout ({stdout_bytes:,} bytes > {max_bytes:,} limit); "
            f"use read_file -> {os.path.abspath(str(manifest_path))}"
        )


def _get_img_src_value(src_match: re.Match[str]) -> str:
    if src_match.group(2) is not None:
        return src_match.group(2)
    if src_match.group(3) is not None:
        return src_match.group(3)
    return src_match.group(4) or ""


def _get_shell_section(template: str, tag_name: str) -> str:
    m = re.search(rf"(?is)<!--\s*{re.escape(tag_name)}_START\s*-->(.*?)<!--\s*{re.escape(tag_name)}_END\s*-->", template)
    if not m:
        raise ValueError(f"Reader shell template missing section: {tag_name}")
    return m.group(1).strip()


def inject_reader_shell(html_text: str, shell_path: Path | None = None) -> tuple[str, list[str]]:
    """Idempotently inject reader CSS, toolbar, and script from tools/reader_shell.html."""
    resolved_shell = shell_path if shell_path is not None else (get_tools_dir() / "reader_shell.html")
    if not resolved_shell.is_file():
        raise FileNotFoundError(f"Reader shell template not found: {resolved_shell}")
    if (
        not re.search(r"(?i)</head>", html_text)
        or not re.search(r"(?i)<body\b[^>]*>", html_text)
        or not re.search(r"(?i)</body>", html_text)
    ):
        raise ValueError("HTML must contain <head>...</head> and <body>...</body> for reader shell injection.")

    tpl = resolved_shell.read_text(encoding="utf-8-sig")
    shell_css = _get_shell_section(tpl, "SHELL_CSS")
    shell_toolbar = _get_shell_section(tpl, "SHELL_TOOLBAR")
    shell_script = _get_shell_section(tpl, "SHELL_SCRIPT")

    injected: list[str] = []
    out = html_text

    has_css = bool(
        re.search(r'(?i)data-reader-shell\s*=\s*"1"', out)
        or (re.search(r"(?i)\.reader-toolbar\b", out) and re.search(r"(?i)\.img-lightbox\b", out))
    )
    if not has_css:
        out = re.sub(r"(?i)</head>", lambda m: f"{shell_css}\n{m.group(0)}", out, count=1)
        injected.append("CSS")

    has_toolbar = bool(
        re.search(r'(?i)data-reader-shell\s*=\s*"toolbar"', out)
        or re.search(r'(?i)class\s*=\s*"[^"]*\b(?:rsfv-toolbar|reader-toolbar)\b', out)
    )
    if not has_toolbar:
        out = re.sub(r"(?i)<body\b[^>]*>", lambda m: f"{m.group(0)}\n{shell_toolbar}", out, count=1)
        injected.append("Toolbar")

    has_script = bool(
        re.search(r'(?i)data-reader-shell\s*=\s*"script"', out)
        or re.search(r'(?i)\bid\s*=\s*"(?:rsfv-img-lightbox|img-lightbox)"', out)
    )
    if not has_script:
        out = re.sub(r"(?i)</body>", lambda m: f"{shell_script}\n{m.group(0)}", out, count=1)
        injected.append("Script")

    return out, injected


def run_html_qa_check(html_text: str, skip_table_wrapper_check: bool = False) -> None:
    """Validate structure, Base64 images, alt tags, table wrappers, MathJax, and internal anchors."""
    issues: list[str] = []
    if (
        not re.search(r"(?i)<head\b[^>]*>", html_text)
        or not re.search(r"(?i)</head>", html_text)
        or not re.search(r"(?i)<body\b[^>]*>", html_text)
        or not re.search(r"(?i)</body>", html_text)
    ):
        issues.append("HTML must contain complete <head>...</head> and <body>...</body> sections.")

    dom_only = _STRIP_SCRIPT_STYLE_RX.sub("", html_text)
    qa_scan = _DATA_URI_PAYLOAD_RX.sub(r"\1OK", dom_only)

    b64_count = 0
    unembedded = 0
    missing_alt = 0
    for img_match in IMG_TAG_RX.finditer(qa_scan):
        attrs = img_match.group(1)
        if not re.search(r"(?is)(?:^|\s)alt\s*=", attrs):
            missing_alt += 1
        for src_match in IMG_SRC_RX.finditer(attrs):
            raw_src = _get_img_src_value(src_match)
            if raw_src == "":
                continue
            src_val = raw_src.strip()
            if _DATA_IMG_RX.match(src_val):
                b64_count += 1
            elif not _EXT_IMG_RX.match(src_val):
                unembedded += 1

    if unembedded > 0:
        issues.append(f"Found {unembedded} un-embedded local <img> src link(s).")
    if missing_alt > 0:
        issues.append(f"Found {missing_alt} <img> tag(s) missing alt attribute.")

    table_count = len(re.findall(r"(?i)<table\b", qa_scan))
    wrapper_count = len(
        re.findall(
            r'(?i)\bclass\s*=\s*(?:"[^"]*\btable-wrapper\b[^"]*"|\'[^\']*\btable-wrapper\b[^\']*\')',
            qa_scan,
        )
    )
    if not skip_table_wrapper_check and table_count > wrapper_count:
        issues.append(f"Found {table_count} <table> element(s) but only {wrapper_count} .table-wrapper container(s).")

    prose_for_latex = _STRIP_PRE_RX.sub("", qa_scan)
    prose_for_latex = _STRIP_CODE_RX.sub("", prose_for_latex)
    prose_for_latex = _STRIP_TEXTAREA_RX.sub("", prose_for_latex)
    has_latex = (r"\(" in prose_for_latex) or (r"\[" in prose_for_latex)
    has_mathjax = bool(re.search(r"(?i)<script\b[^>]*MathJax", html_text))
    if has_latex and not has_mathjax:
        issues.append("Detected LaTeX math delimiters without MathJax <script> in <head>.")

    broken_anchors: list[str] = []
    for m in re.finditer(r'(?i)\bhref\s*=\s*(?:"#([^"]+)"|\'#([^\']+)\')', qa_scan):
        anchor = m.group(1) if m.group(1) is not None else m.group(2)
        esc = re.escape(anchor)
        if not re.search(rf'(?i)\bid\s*=\s*(?:"{esc}"|\'{esc}\')', qa_scan):
            broken_anchors.append(f"#{anchor}")
    if broken_anchors:
        issues.append(f"Broken internal anchor(s): {', '.join(broken_anchors)}")

    if issues:
        raise ValueError("HTML Auto-QA FAILED:\n - " + "\n - ".join(issues))

    table_status = f"Tables: {table_count} (wrapper optional)" if skip_table_wrapper_check else f"Tables wrapped: {wrapper_count}/{table_count}"
    print(f"[QA PASS] Base64 images: {b64_count} | {table_status} | LaTeX/MathJax OK | Broken anchors: 0")


def get_indexed_file_path(base_path: Path, index: int) -> Path:
    """Return `base_path` for index<=1, otherwise `<stem>_<index><ext>` in same directory."""
    if index <= 1:
        return base_path
    return base_path.with_name(f"{base_path.stem}_{index}{base_path.suffix}")


def find_next_available_index(candidate_paths: list[Path]) -> int:
    """Find lowest >=1 suffix index where none of `candidate_paths` exist on disk."""
    idx = 1
    while True:
        if not any(os.path.lexists(get_indexed_file_path(base, idx)) for base in candidate_paths):
            return idx
        idx += 1


def find_headless_browser() -> str | None:
    """Locate Microsoft Edge (preferred) or Google Chrome executable on Windows."""
    roots_and_subpaths = [
        (os.environ.get("ProgramFiles(x86)", ""), os.path.join("Microsoft", "Edge", "Application", "msedge.exe")),
        (os.environ.get("ProgramFiles", ""), os.path.join("Microsoft", "Edge", "Application", "msedge.exe")),
        (os.environ.get("LocalAppData", ""), os.path.join("Microsoft", "Edge", "Application", "msedge.exe")),
        (os.environ.get("ProgramFiles", ""), os.path.join("Google", "Chrome", "Application", "chrome.exe")),
        (os.environ.get("ProgramFiles(x86)", ""), os.path.join("Google", "Chrome", "Application", "chrome.exe")),
        (os.environ.get("LocalAppData", ""), os.path.join("Google", "Chrome", "Application", "chrome.exe")),
    ]
    for base, sub in roots_and_subpaths:
        if not base or not base.strip():
            continue
        candidate = os.path.join(base, sub)
        if os.path.isfile(candidate):
            return candidate
    return None


def html_to_pdf(
    html_path: str | Path,
    out_pdf_path: str | Path = "",
    clean_dir: str = "",
    timeout_seconds: int = 60,
) -> Path | None:
    """Convert HTML to printable PDF via headless Microsoft Edge/Chrome with collision numbering."""
    if timeout_seconds < 5 or timeout_seconds > 600:
        raise ValueError(f"PdfTimeoutSeconds out of range (5..600): {timeout_seconds}")
    assert_local_no_unc_path(html_path, "-HtmlPath")
    assert_local_no_unc_path(out_pdf_path, "-OutPdfPath")
    assert_local_no_unc_path(clean_dir, "-CleanDir")

    raw_html = str(html_path or "").strip()
    if not raw_html or not os.path.isfile(raw_html):
        raise FileNotFoundError(f"HTML file not found: {html_path}")
    abs_html = Path(os.path.abspath(raw_html))
    assert_local_no_unc_path(abs_html, "-HtmlPath")

    raw_pdf = str(out_pdf_path or "").strip()
    base_pdf = Path(os.path.abspath(raw_pdf)) if raw_pdf else abs_html.with_suffix(".pdf")
    dest_pdf = assert_safe_output_path(base_pdf, label="-OutPdfPath", is_directory=False)
    assert dest_pdf is not None

    pdf_idx = find_next_available_index([dest_pdf])
    if pdf_idx > 1:
        dest_pdf = assert_safe_output_path(get_indexed_file_path(dest_pdf, pdf_idx), label="-OutPdfPath", is_directory=False)
        assert dest_pdf is not None
        print(f"Output collision avoided; auto-numbered -> {dest_pdf}")

    dest_pdf.parent.mkdir(parents=True, exist_ok=True)

    browser = find_headless_browser()
    if not browser:
        print(f"WARNING: Microsoft Edge/Chrome not found; skipped automatic PDF export for {abs_html}", file=sys.stderr)
        return None

    tmp_profile = Path(tempfile.gettempdir()) / f"edge_pdf_{uuid.uuid4().hex}"
    tmp_profile.mkdir(parents=True, exist_ok=True)
    try:
        uri = abs_html.as_uri()
        err_log = tmp_profile / "edge_err.log"
        out_log = tmp_profile / "edge_out.log"
        cmd = [
            browser,
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--log-level=3",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=4000",
            f"--user-data-dir={tmp_profile}",
            f"--print-to-pdf={dest_pdf}",
            uri,
        ]
        with open(out_log, "wb") as fout, open(err_log, "wb") as ferr:
            proc = subprocess.Popen(cmd, stdout=fout, stderr=ferr)
            try:
                proc.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except OSError:
                    pass
                raise TimeoutError(f"Headless browser timed out after {timeout_seconds} s while exporting PDF: {dest_pdf}")

        if not dest_pdf.is_file() or dest_pdf.stat().st_size == 0:
            err_detail = ""
            for lf in (err_log, out_log):
                if lf.is_file():
                    raw_log = lf.read_text(encoding="utf-8", errors="replace").strip()
                    if raw_log:
                        err_detail = ("..." + raw_log[-600:]) if len(raw_log) > 600 else raw_log
                        break
            msg = f"Headless browser failed to export PDF (exit={proc.returncode}): {dest_pdf}"
            if err_detail:
                msg += f" | Browser log: {err_detail}"
            raise RuntimeError(msg)

        pdf_sz = dest_pdf.stat().st_size
        print(f"Exported PDF -> {dest_pdf} ({pdf_sz:,} bytes)")
        if clean_dir and clean_dir.strip():
            safe_clean_dir(clean_dir, protected_paths=[dest_pdf])
        return dest_pdf
    finally:
        time.sleep(0.2)
        shutil.rmtree(tmp_profile, ignore_errors=True)


def embed_images_and_package(
    html_path: str | Path,
    optimize_image_bytes_fn: Callable[[Path, int, int], tuple[bytes, str, int]],
    out_html_path: str = "",
    out_pdf_path: str = "",
    also_pdf: bool = False,
    preserve_layout: bool = False,
    quality: int = 90,
    max_width: int = 1400,
    clean_dir: str = "",
    timeout_seconds: int = 60,
    shell_path: Path | None = None,
) -> tuple[Path, Path | None]:
    """Embed & optimize local images in memory, inject reader shell, run Auto-QA, and optionally export PDF."""
    if quality < 1 or quality > 100:
        raise ValueError(f"JpegQuality out of valid range (1..100): {quality}")
    if max_width < 0 or max_width > 10000:
        raise ValueError(f"MaxImageWidth out of valid range (0..10000): {max_width}")
    if timeout_seconds < 5 or timeout_seconds > 600:
        raise ValueError(f"PdfTimeoutSeconds out of range (5..600): {timeout_seconds}")

    assert_local_no_unc_path(html_path, "-HtmlPath")
    assert_local_no_unc_path(out_html_path, "-OutHtmlPath")
    assert_local_no_unc_path(out_pdf_path, "-OutPdfPath")
    assert_local_no_unc_path(clean_dir, "-CleanDir")

    raw_in = str(html_path or "").strip()
    if not raw_in or not os.path.isfile(raw_in):
        raise FileNotFoundError(f"HTML file not found: {html_path}")
    abs_html = Path(os.path.abspath(raw_in))
    assert_local_no_unc_path(abs_html, "-HtmlPath")
    base_dir = abs_html.parent
    content = abs_html.read_text(encoding="utf-8-sig")

    opt_cache: dict[str, tuple[str, int, int]] = {}
    stats = {"total": 0, "compressed": 0, "orig_bytes": 0, "final_bytes": 0}

    def _replace_src(src_match: re.Match[str]) -> str:
        prefix = src_match.group(1)
        rel = _get_img_src_value(src_match).strip()
        if not rel or _EXT_IMG_RX.match(rel):
            return src_match.group(0)
        if _LOCAL_OPT_EXT_RX.search(rel):
            img_path = resolve_safe_sub_image_path(base_dir, rel)
            if img_path is not None:
                key = str(img_path).lower()
                if key not in opt_cache:
                    out_bytes, mime, orig_len = optimize_image_bytes_fn(img_path, quality, max_width)
                    b64 = base64.b64encode(out_bytes).decode("ascii")
                    opt_cache[key] = (f"data:{mime};base64,{b64}", orig_len, len(out_bytes))
                data_uri, orig_len, final_len = opt_cache[key]
                stats["total"] += 1
                stats["orig_bytes"] += orig_len
                stats["final_bytes"] += final_len
                if final_len < orig_len:
                    stats["compressed"] += 1
                return f'{prefix}"{data_uri}"'
        return src_match.group(0)

    def _replace_img_tag(img_match: re.Match[str]) -> str:
        return "<img" + IMG_SRC_RX.sub(_replace_src, img_match.group(1)) + ">"

    updated = IMG_TAG_RX.sub(_replace_img_tag, content)

    shell_injected: list[str] = []
    if not preserve_layout:
        updated, shell_injected = inject_reader_shell(updated, shell_path=shell_path)

    run_html_qa_check(updated, skip_table_wrapper_check=preserve_layout)

    has_explicit_out_html = bool(out_html_path and out_html_path.strip())
    raw_dest = Path(os.path.abspath(out_html_path.strip())) if has_explicit_out_html else abs_html
    dest = assert_safe_output_path(raw_dest, label="-OutHtmlPath", is_directory=False)
    assert dest is not None

    has_custom_out_pdf = bool(out_pdf_path and out_pdf_path.strip())
    want_pdf = also_pdf or has_custom_out_pdf
    pdf_protected: Path | None = None
    if want_pdf:
        raw_pdf = Path(os.path.abspath(out_pdf_path.strip())) if has_custom_out_pdf else dest.with_suffix(".pdf")
        pdf_protected = assert_safe_output_path(raw_pdf, label="-OutPdfPath", is_directory=False)

    if has_explicit_out_html and not has_custom_out_pdf:
        candidates = [dest, pdf_protected] if pdf_protected is not None else [dest]
        pair_idx = find_next_available_index(candidates)
        if pair_idx > 1:
            dest = assert_safe_output_path(get_indexed_file_path(dest, pair_idx), label="-OutHtmlPath", is_directory=False)
            assert dest is not None
            print(f"Output collision avoided; auto-numbered -> {dest}")
            if pdf_protected is not None:
                pdf_protected = assert_safe_output_path(
                    get_indexed_file_path(pdf_protected, pair_idx), label="-OutPdfPath", is_directory=False
                )
    else:
        if has_explicit_out_html:
            html_idx = find_next_available_index([dest])
            if html_idx > 1:
                dest = assert_safe_output_path(get_indexed_file_path(dest, html_idx), label="-OutHtmlPath", is_directory=False)
                assert dest is not None
                print(f"Output collision avoided; auto-numbered -> {dest}")
        if pdf_protected is not None:
            pdf_idx = find_next_available_index([pdf_protected])
            if pdf_idx > 1:
                pdf_protected = assert_safe_output_path(
                    get_indexed_file_path(pdf_protected, pdf_idx), label="-OutPdfPath", is_directory=False
                )

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(updated, encoding="utf-8")
    sz = dest.stat().st_size

    if stats["total"] > 0:
        saved_kb = round((stats["orig_bytes"] - stats["final_bytes"]) / 1024.0, 1)
        print(f"Optimized {stats['compressed']}/{stats['total']} images (Quality={quality}%, saved {saved_kb:,.1f} KB raw)")

    if preserve_layout:
        print("PreserveLayout mode: skipped reader shell injection")
    elif shell_injected:
        print(f"Injected reader shell -> {', '.join(shell_injected)}")
    else:
        print("Reader shell already present (skipped injection)")

    print(f"Embedded images into HTML -> {dest} ({sz:,} bytes)")

    exported_pdf: Path | None = None
    if want_pdf and pdf_protected is not None:
        exported_pdf = html_to_pdf(dest, out_pdf_path=pdf_protected, clean_dir="", timeout_seconds=timeout_seconds)

    if clean_dir and clean_dir.strip():
        protected = [dest] + ([exported_pdf] if exported_pdf is not None else [pdf_protected] if pdf_protected else [])
        safe_clean_dir(clean_dir, protected_paths=protected)

    return dest, exported_pdf
