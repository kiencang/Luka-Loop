#!/usr/bin/env python3
# ==============================================================================
# [BUILD SOURCE / REFERENCE ONLY — DO NOT EXECUTE WITH SYSTEM PYTHON]
#
# Mục đích tệp này: Đây CHỈ là mã nguồn Python gốc dùng khi cần chỉnh sửa logic
# và đóng gói (PyInstaller) ra tệp chạy độc lập `tools\extract_assets\extract_assets.exe`.
#
# LƯU Ý CHO AI AGENT:
#   - KHÔNG chạy tệp `.py` này bằng `python` / `python3` / `py` / `pip`.
#   - Máy người dùng chạy qua bộ công cụ portable không cần Python hệ thống.
#   - Khi tách ảnh PDF, hãy gọi `tools\extract_pdf_assets.ps1` (tự động gọi
#     `tools\extract_assets\extract_assets.exe`) theo hướng dẫn trong SKILL.md.
# ==============================================================================
"""
CLI Entry Point & PyInstaller Build Source for `extract_assets.exe`.

Dispatches all portable operations across dedicated modules:
  - `figure_detector/`: Layout-aware figure/caption detection and extraction (package, one module per phase)
  - `image_ops.py`: Lazy PyMuPDF loader, page rendering, JSON cropping, image optimization
  - `packager.py`: Step 4 entry point — Base64 embedding, then reader shell, Auto-QA and optional PDF via:
      `reader_shell.py` (shell + CSP injection), `html_qa.py` (Auto-QA scanner),
      `pdf_export.py` (headless Edge/Chrome), `output_paths.py` (output naming & post-output cleanup)
  - `transcript.py`: Latest PDF attachment lookup in transcript.jsonl (Antigravity)
  - `manifest.py`: Compacted manifest stdout output (stdlib only, no project imports)
  - `path_guards.py`: Path safety, UNC/reparse-point guards, and safe cleanup

Build target:
  tools/extract_assets/extract_assets.exe (invoked via tools/*.ps1 wrappers)
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

from figure_detector import (
    _classify_text_block,
    _clean_text,
    _ensure_pymupdf,
    _split_dict_block,
    collect_page_figures,
    extract_images,
)
from image_ops import (
    _analyze_sample_grid,
    _optimize_image_bytes,
    crop_from_json,
    render_pages,
)
from packager import embed_images_and_package
from path_guards import assert_local_no_unc_path
from pdf_export import html_to_pdf
from transcript import find_latest_pdf_in_transcript

__all__ = [
    "_analyze_sample_grid",
    "_classify_text_block",
    "_clean_text",
    "_ensure_pymupdf",
    "_optimize_image_bytes",
    "_split_dict_block",
    "collect_page_figures",
    "crop_from_json",
    "extract_images",
    "main",
    "render_pages",
]


def _configure_utf8_stdio() -> None:
    """Ensure stdout/stderr emit UTF-8 on Windows even when piped under cp1252."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _validate_dpi(value: str) -> int:
    dpi = int(value)
    if dpi < 36 or dpi > 1200:
        raise argparse.ArgumentTypeError(f"--dpi must be between 36 and 1200 (got {dpi})")
    return dpi


def _validate_scale(value: str) -> float:
    scale = float(value)
    if not math.isfinite(scale) or scale < 0.5 or scale > 10.0:
        raise argparse.ArgumentTypeError(f"--scale must be between 0.5 and 10.0 (got {value})")
    return scale


def _validate_quality(value: str) -> int:
    quality = int(value)
    if quality < 1 or quality > 100:
        raise argparse.ArgumentTypeError(f"--quality must be between 1 and 100 (got {quality})")
    return quality


def _validate_max_width(value: str) -> int:
    width = int(value)
    if width < 0 or width > 10000:
        raise argparse.ArgumentTypeError(f"--max-width must be between 0 and 10000 (got {width})")
    return width


def _validate_timeout(value: str) -> int:
    t = int(value)
    if t < 5 or t > 600:
        raise argparse.ArgumentTypeError(f"--timeout-seconds must be between 5 and 600 (got {t})")
    return t


def _validate_non_negative_int(value: str) -> int:
    v = int(value)
    if v < 0:
        raise argparse.ArgumentTypeError(f"Expected non-negative integer (got {v})")
    return v


def _dispatch_cli(raw_argv: list[str]) -> None:
    modes = ("extract", "render-pages", "crop-json", "embed-images", "html-to-pdf")
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--mode", choices=modes, default=None)
    known, rest = pre.parse_known_args(raw_argv)
    mode = known.mode or "extract"

    if mode == "extract":
        ap = argparse.ArgumentParser(
            description="Layout-aware figure image extractor & standalone PDF/HTML packager (PyMuPDF)"
        )
        ap.add_argument("--mode", choices=modes, default="extract", help="Operation mode (default: extract)")
        ap.add_argument("pdf", nargs="?", type=Path, default=None)
        ap.add_argument("--transcript", type=str, default="", help="Resolve latest PDF attachment from transcript.jsonl")
        ap.add_argument("--out-dir", type=Path, required=True)
        ap.add_argument("--dpi", type=_validate_dpi, default=180)
        ap.add_argument("--meta", action="store_true", help="Write manifest.json mapping extracted images")
        ap.add_argument("--stdout-meta", action="store_true", help="Also print compacted manifest JSON to stdout")
        ap.add_argument("--max-meta-bytes", type=_validate_non_negative_int, default=16384)
        ap.add_argument("--max-meta-words", type=_validate_non_negative_int, default=20)
        ap.add_argument("--print-resolved", action="store_true", help="Print 'Resolved PDF -> ...' line")
        args = ap.parse_args(rest)

        if args.pdf is not None and str(args.pdf).strip():
            assert_local_no_unc_path(args.pdf, "-PdfPath")
            if not args.pdf.is_file():
                raise FileNotFoundError(f"Resolved PDF file does not exist: {args.pdf}")
            target_pdf = Path(os.path.abspath(str(args.pdf)))
        elif args.transcript and args.transcript.strip():
            target_pdf = find_latest_pdf_in_transcript(args.transcript)
        else:
            raise ValueError("Either pdf path or --transcript must be provided.")

        if args.print_resolved or args.transcript:
            print(f"Resolved PDF -> {target_pdf}")

        extract_images(
            target_pdf,
            args.out_dir,
            args.dpi,
            write_meta=args.meta,
            stdout_meta=args.stdout_meta,
            max_meta_words=args.max_meta_words,
            max_meta_bytes=args.max_meta_bytes,
        )
    elif mode == "render-pages":
        ap = argparse.ArgumentParser(description="Render PDF pages to PNG images")
        ap.add_argument("pdf", type=Path)
        ap.add_argument("--out-dir", type=Path, required=True)
        ap.add_argument("--scale", type=_validate_scale, default=2.5)
        ap.add_argument("--pages", type=str, default="")
        args = ap.parse_args(rest)
        render_pages(args.pdf, args.out_dir, scale=args.scale, pages=args.pages)
    elif mode == "crop-json":
        ap = argparse.ArgumentParser(description="Crop PNG regions from JSON spec with optional auto-trim")
        ap.add_argument("--spec", type=Path, required=True)
        ap.add_argument("--out-dir", type=Path, required=True)
        args = ap.parse_args(rest)
        crop_from_json(args.spec, args.out_dir)
    elif mode == "embed-images":
        ap = argparse.ArgumentParser(description="Embed images in memory, inject reader shell, run QA, and optionally export PDF")
        ap.add_argument("--html", type=Path, required=True)
        ap.add_argument("--out-html", type=str, default="")
        ap.add_argument("--out-pdf", type=str, default="")
        ap.add_argument("--also-pdf", action="store_true")
        ap.add_argument("--preserve-layout", action="store_true")
        ap.add_argument("--quality", type=_validate_quality, default=95)
        ap.add_argument("--max-width", type=_validate_max_width, default=1400)
        ap.add_argument("--clean-dir", type=str, default="")
        ap.add_argument("--timeout-seconds", type=_validate_timeout, default=60)
        args = ap.parse_args(rest)
        embed_images_and_package(
            html_path=args.html,
            optimize_image_bytes_fn=_optimize_image_bytes,
            out_html_path=args.out_html,
            out_pdf_path=args.out_pdf,
            also_pdf=args.also_pdf,
            preserve_layout=args.preserve_layout,
            quality=args.quality,
            max_width=args.max_width,
            clean_dir=args.clean_dir,
            timeout_seconds=args.timeout_seconds,
        )
    else:
        ap = argparse.ArgumentParser(description="Convert self-contained HTML to PDF via headless Edge/Chrome")
        ap.add_argument("--html", type=Path, required=True)
        ap.add_argument("--out-pdf", type=str, default="")
        ap.add_argument("--clean-dir", type=str, default="")
        ap.add_argument("--timeout-seconds", type=_validate_timeout, default=60)
        args = ap.parse_args(rest)
        html_to_pdf(
            html_path=args.html,
            out_pdf_path=args.out_pdf,
            clean_dir=args.clean_dir,
            timeout_seconds=args.timeout_seconds,
        )


def main(argv: list[str] | None = None) -> None:
    _configure_utf8_stdio()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        _dispatch_cli(raw_argv)
    except (ValueError, FileNotFoundError, RuntimeError, TimeoutError, PermissionError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
