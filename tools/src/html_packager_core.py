"""Core packaging, HTML QA, transcript lookup, and headless PDF export logic for Luka-Loop."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from path_guards import (
    assert_local_no_unc_path,
    assert_safe_output_path,
    file_uri_to_local_path,
    get_repo_root,
    get_tools_dir,
    is_reparse_point,
    resolve_safe_sub_image_path,
    safe_clean_dir,
    sanitize_output_filename,
)

MAX_INPUT_HTML_BYTES = 256 * 1024 * 1024  # 256 MB sanity ceiling for raw input HTML

IMG_TAG_RX = re.compile(r'(?is)<img\b((?:[^>"\']|"[^"]*"|\'[^\']*\')*)>')
IMG_SRC_RX = re.compile(r'(?is)((?:^|\s)src\s*=\s*)(?:"([^"]*)"|\'([^\']*)\'|([^\s"\'=<>`]+))')
_DATA_IMG_RX = re.compile(r"^data:image/(?:png|jpeg|jpg|webp|gif);base64,", re.IGNORECASE)
_EXT_IMG_RX = re.compile(r"(?i)^(?:data:|https?://)")
_EXTERNAL_URL_RX = re.compile(r"^(?:https?:)?//", re.IGNORECASE)
_LOCAL_OPT_EXT_RX = re.compile(r"(?i)\.(?:png|jpe?g)$")
_HTML_IGNORED_SEGMENTS_RX = re.compile(
    r"(?is)<!--.*?-->|<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>|<textarea\b[^>]*>.*?</textarea>"
)
_SCRIPT_BODY_RX = re.compile(r"(?is)<script\b[^>]*>(.*?)</script>")
_ALLOWED_MATHJAX_SRC_RX = re.compile(
    r"^https://(?:"
    r"cdn\.jsdelivr\.net/npm/mathjax@3(?:\.\d+){0,2}/es5/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*\.js"
    r"|cdnjs\.cloudflare\.com/ajax/libs/mathjax/3(?:\.\d+){1,2}/es5/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*\.js"
    r")$",
    re.IGNORECASE,
)
_ALLOWED_CSS_REMOTE_RX = re.compile(
    r"^https://fonts\.(?:googleapis|gstatic)\.com(?:/|$)",
    re.IGNORECASE,
)
_FORBIDDEN_HTML_TAGS = frozenset(
    {
        "iframe",
        "object",
        "embed",
        "applet",
        "base",
        "form",
        "frame",
        "frameset",
        "portal",
        "fencedframe",
        "foreignobject",
        "animate",
        "animatemotion",
        "animatetransform",
        "set",
        "handler",
        "template",
        "noscript",
    }
)
_FORBIDDEN_META_HTTP_EQUIV = frozenset({"refresh", "set-cookie"})
_EVENT_HANDLER_ATTR_RX = re.compile(r"^on[a-z]+$", re.IGNORECASE)
_URI_ATTRS = frozenset({"href", "src", "xlink:href", "action", "formaction", "poster", "data", "background"})
_SVG_EXTERNAL_HREF_TAGS = frozenset({"image", "use", "feimage"})
_MEDIA_SRC_TAGS = frozenset({"audio", "video", "source", "track"})
_ALLOWED_LINK_RELS = frozenset({"stylesheet", "preconnect", "font"})
_STRIP_CTRL_WS_RX = re.compile(r"[\x00-\x20\x7f]+")
_URI_SCHEME_RX = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_SAFE_LINK_SCHEME_RX = re.compile(r"^(?:https?://|mailto:)", re.IGNORECASE)
_DANGEROUS_URI_SCHEME_RX = re.compile(r"^(?:javascript|vbscript|file):", re.IGNORECASE)
_CSS_COMMENT_RX = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_ESCAPE_RX = re.compile(r"\\([0-9a-fA-F]{1,6})\s?|\\(.)")
_CSS_URL_RX = re.compile(
    r"""(?i)\burl\s*\(\s*(?:"([^"]*)"|'([^']*)'|([^)\s"']+))\s*\)"""
    r"""|@import\s+(?:url\s*\(\s*)?(?:"([^"]*)"|'([^']*)'|([^;\s"']+))"""
)
_CSS_IMAGE_SET_RX = re.compile(r"""(?is)(?:-webkit-)?image-set\s*\(([^)]*)\)""")
_CSS_QUOTED_STR_RX = re.compile(r"""(?:"([^"]*)"|'([^']*)')""")
_LATEX_HREF_URL_RX = re.compile(r"""\\(?:href|url)\s*\{([^{}]*)\}""", re.IGNORECASE)
_LATEX_STYLE_RX = re.compile(r"""\\style\s*\{([^{}]*)\}""", re.IGNORECASE)
_MANIFEST_MARKER_RX = re.compile(r"===\s*MANIFEST\s+JSON\s+(?:START|END)\s*===", re.IGNORECASE)
_CSP_META_TAG_RX = re.compile(r"""(?is)<meta\b[^>]*\bdata-luka-csp\s*=\s*["']1["'][^>]*>\s*""")
_HEADLESS_ALLOWED_HOSTS_RULE = (
    "MAP * ~NOTFOUND, "
    "EXCLUDE cdn.jsdelivr.net, "
    "EXCLUDE cdnjs.cloudflare.com, "
    "EXCLUDE fonts.googleapis.com, "
    "EXCLUDE fonts.gstatic.com"
)
_LIGHTBOX_IDS = frozenset({"rsfv-img-lightbox", "img-lightbox"})
_HTML_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_RAW_DOM_EXCLUDED_TAGS = frozenset({"script", "style", "textarea"})
_LATEX_IGNORED_TAGS = frozenset({"script", "style", "pre", "code", "textarea"})
_P_AUTO_CLOSE_TRIGGERS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "details",
        "dialog",
        "dd",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "hr",
        "li",
        "main",
        "menu",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "ul",
    }
)
_P_SCOPE_BOUNDARIES = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "body",
        "details",
        "dialog",
        "div",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "header",
        "html",
        "li",
        "main",
        "nav",
        "section",
        "table",
        "td",
        "th",
    }
)


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


def _sanitize_manifest_text(text: str) -> str:
    """Strip control characters and neutralize stdout manifest delimiter spoofing."""
    cleaned = re.sub(r"[\x00-\x1F\x7F]+", " ", str(text)).strip()
    return _MANIFEST_MARKER_RX.sub("[manifest-marker]", cleaned)


def limit_manifest_words(text: str | None, max_words: int = 20) -> str:
    """Truncate caption/context text cleanly to `max_words` words for compact stdout output."""
    if text is None:
        return ""
    normalized = _sanitize_manifest_text(str(text))
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
    if compacted.get("pdf") is not None:
        compacted["pdf"] = _sanitize_manifest_text(str(compacted["pdf"]))
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


def _resolve_safe_shell_path(shell_path: Path | None = None, *, required: bool = True) -> Path | None:
    """Resolve tools/reader_shell.html while refusing symlinks/junctions."""
    resolved_shell = shell_path if shell_path is not None else (get_tools_dir() / "reader_shell.html")
    assert_local_no_unc_path(resolved_shell, "ReaderShellPath")
    if os.path.lexists(resolved_shell.parent) and is_reparse_point(resolved_shell.parent):
        raise ValueError(f"Refusing to read reader shell through symlink/junction: {resolved_shell.parent}")
    if os.path.lexists(resolved_shell) and is_reparse_point(resolved_shell):
        raise ValueError(f"Refusing to read symlink/junction reader shell: {resolved_shell}")
    if not resolved_shell.is_file():
        if required or shell_path is not None:
            raise FileNotFoundError(f"Reader shell template not found: {resolved_shell}")
        return None
    return resolved_shell


def _strip_html_comments(html_text: str) -> str:
    """Remove HTML comments while leaving <script>, <style>, and <textarea> contents intact."""
    return _HTML_IGNORED_SEGMENTS_RX.sub(
        lambda m: "" if m.group(0).startswith("<!--") else m.group(0),
        html_text,
    )


def _sub_outside_ignored(
    text: str,
    target_rx: re.Pattern[str],
    repl: Callable[[re.Match[str]], str] | str,
    count: int = 0,
) -> tuple[str, int]:
    """Apply `target_rx` substitutions only on HTML markup outside comments, scripts, styles, and textareas."""
    parts: list[str] = []
    pos = 0
    total_subs = 0
    for ign in _HTML_IGNORED_SEGMENTS_RX.finditer(text):
        seg = text[pos : ign.start()]
        if seg and (count == 0 or total_subs < count):
            rem = (count - total_subs) if count > 0 else 0
            seg, n = target_rx.subn(repl, seg, count=rem)
            total_subs += n
        parts.append(seg)
        parts.append(ign.group(0))
        pos = ign.end()
    tail = text[pos:]
    if tail and (count == 0 or total_subs < count):
        rem = (count - total_subs) if count > 0 else 0
        tail, n = target_rx.subn(repl, tail, count=rem)
        total_subs += n
    parts.append(tail)
    return "".join(parts), total_subs


def inject_reader_shell(html_text: str, shell_path: Path | None = None) -> tuple[str, list[str]]:
    """Idempotently inject reader CSS, toolbar, and script from tools/reader_shell.html."""
    resolved_shell = _resolve_safe_shell_path(shell_path, required=True)
    assert resolved_shell is not None
    dom_check = _HTML_IGNORED_SEGMENTS_RX.sub("", html_text)
    if (
        not re.search(r"(?i)</head>", dom_check)
        or not re.search(r"(?i)<body\b[^>]*>", dom_check)
        or not re.search(r"(?i)</body>", dom_check)
    ):
        raise ValueError("HTML must contain <head>...</head> and <body>...</body> for reader shell injection.")

    tpl = resolved_shell.read_text(encoding="utf-8-sig")
    shell_css = _get_shell_section(tpl, "SHELL_CSS")
    shell_toolbar = _get_shell_section(tpl, "SHELL_TOOLBAR")
    shell_script = _get_shell_section(tpl, "SHELL_SCRIPT")

    injected: list[str] = []
    out = html_text
    no_comments = _strip_html_comments(out)

    has_css = bool(
        re.search(r'(?i)data-reader-shell\s*=\s*"1"', no_comments)
        or (re.search(r"(?i)\.reader-toolbar\b", no_comments) and re.search(r"(?i)\.img-lightbox\b", no_comments))
    )
    if not has_css:
        out, _ = _sub_outside_ignored(out, re.compile(r"(?i)</head>"), lambda m: f"{shell_css}\n{m.group(0)}", count=1)
        injected.append("CSS")

    has_toolbar = bool(
        re.search(r'(?i)data-reader-shell\s*=\s*"toolbar"', no_comments)
        or re.search(r'(?i)class\s*=\s*"[^"]*\b(?:rsfv-toolbar|reader-toolbar)\b', no_comments)
    )
    if not has_toolbar:
        out, _ = _sub_outside_ignored(
            out,
            re.compile(r"(?i)<body\b[^>]*>"),
            lambda m: f"{m.group(0)}\n{shell_toolbar}",
            count=1,
        )
        injected.append("Toolbar")

    has_script = bool(
        re.search(r'(?i)data-reader-shell\s*=\s*"script"', no_comments)
        or re.search(r'(?i)\bid\s*=\s*"(?:rsfv-img-lightbox|img-lightbox)"', no_comments)
    )
    if not has_script:
        out, _ = _sub_outside_ignored(out, re.compile(r"(?i)</body>"), lambda m: f"{shell_script}\n{m.group(0)}", count=1)
        injected.append("Script")

    return out, injected


def _normalize_script_body(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _extract_trusted_shell_scripts(shell_path: Path | None = None) -> frozenset[str]:
    """Return normalized exact inline JS bodies allowed from the trusted reader_shell.html template."""
    resolved_shell = _resolve_safe_shell_path(shell_path, required=False)
    if resolved_shell is None:
        return frozenset()
    tpl = resolved_shell.read_text(encoding="utf-8-sig")
    shell_script_section = _get_shell_section(tpl, "SHELL_SCRIPT")
    bodies = {
        _normalize_script_body(m.group(1))
        for m in _SCRIPT_BODY_RX.finditer(shell_script_section)
        if m.group(1).strip()
    }
    return frozenset(bodies)


def inject_csp_meta(
    html_text: str,
    *,
    has_mathjax: bool,
    inline_script_raw_bodies: list[str],
) -> str:
    """Idempotently inject a defense-in-depth Content-Security-Policy <meta> right inside <head>."""
    cleaned, _ = _sub_outside_ignored(html_text, _CSP_META_TAG_RX, "")

    script_tokens: list[str] = []
    seen_hashes: set[str] = set()
    for raw_body in inline_script_raw_bodies:
        norm_lf = raw_body.replace("\r\n", "\n").replace("\r", "\n")
        if not norm_lf.strip():
            continue
        digest = base64.b64encode(hashlib.sha256(norm_lf.encode("utf-8")).digest()).decode("ascii")
        token = f"'sha256-{digest}'"
        if token not in seen_hashes:
            seen_hashes.add(token)
            script_tokens.append(token)
    if has_mathjax:
        script_tokens.extend(["https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com"])
    script_src = " ".join(script_tokens) if script_tokens else "'none'"

    font_tokens = ["https://fonts.gstatic.com", "data:"]
    if has_mathjax:
        font_tokens.extend(["https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com"])
    font_src = " ".join(font_tokens)

    policy = (
        f"default-src 'none'; "
        f"img-src data:; "
        f"style-src 'unsafe-inline' https://fonts.googleapis.com; "
        f"font-src {font_src}; "
        f"script-src {script_src}; "
        f"connect-src 'none'; "
        f"object-src 'none'; "
        f"frame-src 'none'; "
        f"base-uri 'none'; "
        f"form-action 'none';"
    )
    meta_tag = f'<meta http-equiv="Content-Security-Policy" data-luka-csp="1" content="{policy}">'
    updated, count = _sub_outside_ignored(
        cleaned,
        re.compile(r"(?i)<head\b[^>]*>"),
        lambda m: f"{m.group(0)}\n{meta_tag}",
        count=1,
    )
    return updated if count > 0 else cleaned


def _decode_css_escapes(text: str) -> str:
    """Decode CSS backslash escapes (e.g. `\\68 ttps://`) before URL scheme inspection."""

    def _repl(m: re.Match[str]) -> str:
        hex_part = m.group(1)
        if hex_part is not None:
            try:
                cp = int(hex_part, 16)
                if 0 < cp <= 0x10FFFF:
                    return chr(cp)
            except ValueError:
                pass
            return ""
        return m.group(2) or ""

    return _CSS_ESCAPE_RX.sub(_repl, text)


def _is_allowed_css_url(raw_url: str) -> bool:
    """Allowlist-only CSS URL filter: permits empty, #fragment, Base64 raster images, and Google Fonts."""
    cleaned = _STRIP_CTRL_WS_RX.sub("", raw_url)
    if not cleaned or cleaned.startswith("#"):
        return True
    if _DATA_IMG_RX.match(cleaned) or _ALLOWED_CSS_REMOTE_RX.match(cleaned):
        return True
    return False


def _format_sample_items(items: list[str], limit: int = 5) -> str:
    shown = ", ".join(items[:limit])
    if len(items) > limit:
        shown += f" (+{len(items) - limit} more)"
    return shown


class _QADOMScanner(HTMLParser):
    """Single-pass DOM & security scanner tracking tag nesting while ignoring HTML comments and raw blocks."""

    def __init__(
        self,
        *,
        allowed_inline_scripts: frozenset[str] = frozenset(),
        allow_external_images: bool = False,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self._allowed_inline_scripts = allowed_inline_scripts
        self._allow_external_images = allow_external_images
        self._open_stack: list[tuple[str, bool, str]] = []
        self._prose_buf: list[str] = []
        self._active_script: dict[str, object] | None = None
        self._style_buf: list[str] = []
        self.has_head_open = False
        self.has_head_close = False
        self.has_body_open = False
        self.has_body_close = False
        self.b64_count = 0
        self.unembedded_imgs = 0
        self.unembedded_img_srcs: list[str] = []
        self._seen_unembedded_imgs: set[str] = set()
        self.external_img_srcs: list[str] = []
        self._seen_ext_imgs: set[str] = set()
        self.missing_alt_imgs = 0
        self.table_count = 0
        self.wrapped_table_count = 0
        self.has_latex = False
        self.has_mathjax_in_head = False
        self.allowed_inline_script_raw_bodies: list[str] = []
        self.seen_ids: set[str] = set()
        self.anchor_refs: list[str] = []
        self.disallowed_scripts: list[str] = []
        self._seen_scripts: set[str] = set()
        self.disallowed_tags: list[str] = []
        self._seen_tags: set[str] = set()
        self.disallowed_event_handlers: list[str] = []
        self._seen_handlers: set[str] = set()
        self.dangerous_uris: list[str] = []
        self._seen_uris: set[str] = set()
        self.disallowed_external_resources: list[str] = []
        self._seen_ext_res: set[str] = set()

    @staticmethod
    def _add_issue(bucket: list[str], seen: set[str], value: str) -> None:
        if value not in seen:
            seen.add(value)
            bucket.append(value)

    def _in_tags(self, tag_set: frozenset[str]) -> bool:
        return any(t in tag_set for t, _, _ in self._open_stack)

    def _current_raw_tag(self) -> str | None:
        for t, _, _ in reversed(self._open_stack):
            if t in _RAW_DOM_EXCLUDED_TAGS:
                return t
        return None

    def _flush_prose(self) -> None:
        if not self._prose_buf:
            return
        chunk = "".join(self._prose_buf)
        self._prose_buf.clear()
        if not self.has_latex and (r"\(" in chunk or r"\[" in chunk):
            self.has_latex = True
        if "\\" in chunk:
            for m in _LATEX_HREF_URL_RX.finditer(chunk):
                raw_target = _STRIP_CTRL_WS_RX.sub("", m.group(1) or "")
                if raw_target and not (
                    raw_target.startswith("#") or _SAFE_LINK_SCHEME_RX.match(raw_target)
                ):
                    self._add_issue(
                        self.dangerous_uris,
                        self._seen_uris,
                        f'LaTeX \\href{{{raw_target[:60]}}}',
                    )
            for m in _LATEX_STYLE_RX.finditer(chunk):
                css_payload = m.group(1) or ""
                if css_payload:
                    self._scan_css_text(css_payload, source="LaTeX \\style")
                    if "expression(" in _STRIP_CTRL_WS_RX.sub("", css_payload).lower():
                        self._add_issue(
                            self.disallowed_external_resources,
                            self._seen_ext_res,
                            "LaTeX \\style expression(...)",
                        )

    def _close_implicit_p(self) -> None:
        for idx in range(len(self._open_stack) - 1, -1, -1):
            t, _, _ = self._open_stack[idx]
            if t == "p":
                del self._open_stack[idx:]
                return
            if t in _P_SCOPE_BOUNDARIES:
                return

    def _pop_open_tag(self, target_tag: str) -> None:
        for idx in range(len(self._open_stack) - 1, -1, -1):
            if self._open_stack[idx][0] == target_tag:
                del self._open_stack[idx:]
                return

    def _scan_css_text(self, css_text: str, source: str) -> None:
        stripped = _decode_css_escapes(_CSS_COMMENT_RX.sub("", css_text))
        for m in _CSS_URL_RX.finditer(stripped):
            raw_url = next((g for g in m.groups() if g is not None), "")
            if raw_url and not _is_allowed_css_url(raw_url):
                self._add_issue(
                    self.disallowed_external_resources,
                    self._seen_ext_res,
                    f"{source} url({raw_url.strip()[:100]})",
                )
        for im in _CSS_IMAGE_SET_RX.finditer(stripped):
            body = im.group(1) or ""
            for qm in _CSS_QUOTED_STR_RX.finditer(body):
                cand_url = qm.group(1) if qm.group(1) is not None else (qm.group(2) or "")
                if cand_url and not _is_allowed_css_url(cand_url):
                    self._add_issue(
                        self.disallowed_external_resources,
                        self._seen_ext_res,
                        f"{source} image-set({cand_url.strip()[:100]})",
                    )

    def _finalize_style_block(self) -> None:
        if not self._style_buf:
            return
        self._scan_css_text("".join(self._style_buf), source="<style>")
        self._style_buf.clear()

    def _finalize_active_script(self) -> None:
        if self._active_script is None:
            return
        info = self._active_script
        self._active_script = None
        in_head = bool(info["in_head"])
        src_val = info["src"]
        body_chunks = info["body"]
        assert isinstance(body_chunks, list)
        raw_body = "".join(body_chunks)
        body_norm = _normalize_script_body(raw_body)

        if src_val is not None:
            cleaned_src = str(src_val).strip()
            if in_head and not body_norm and _ALLOWED_MATHJAX_SRC_RX.match(cleaned_src):
                self.has_mathjax_in_head = True
                return
            desc = f'<script src="{cleaned_src[:100]}">' if cleaned_src else '<script src="">'
            self._add_issue(self.disallowed_scripts, self._seen_scripts, desc)
            return

        if body_norm and body_norm in self._allowed_inline_scripts:
            self.allowed_inline_script_raw_bodies.append(raw_body)
            return

        snippet = (body_norm[:40] + "...") if len(body_norm) > 40 else (body_norm or "<empty>")
        self._add_issue(self.disallowed_scripts, self._seen_scripts, f"<script>{snippet}</script>")

    def _process_start_tag(self, tag: str, attrs: list[tuple[str, str | None]], self_closing: bool) -> None:
        self._flush_prose()
        t = tag.lower()
        if self._in_tags(_RAW_DOM_EXCLUDED_TAGS):
            return

        if t in _P_AUTO_CLOSE_TRIGGERS:
            self._close_implicit_p()

        if t in _FORBIDDEN_HTML_TAGS:
            self._add_issue(self.disallowed_tags, self._seen_tags, f"<{t}>")

        if t == "head":
            self.has_head_open = True
        elif t == "body":
            self.has_body_open = True
        elif t == "script":
            in_head = any(t_name == "head" for t_name, _, _ in self._open_stack)
            script_srcs = ["" if v is None else v for k, v in attrs if (k or "").lower() == "src"]
            if self_closing:
                first_src = script_srcs[0].strip()[:80] if script_srcs else ""
                desc = f'<script src="{first_src}"/>' if script_srcs else "<script/>"
                self._add_issue(self.disallowed_scripts, self._seen_scripts, desc)
            elif len(script_srcs) > 1:
                self._add_issue(self.disallowed_scripts, self._seen_scripts, "<script (duplicate src)>")
                self._active_script = {"in_head": False, "src": script_srcs[0], "body": []}
            else:
                script_src = script_srcs[0] if script_srcs else None
                self._active_script = {"in_head": in_head, "src": script_src, "body": []}
        elif t == "style" and not self_closing:
            self._style_buf.clear()
        elif t == "img":
            has_alt = False
            has_nonempty_src = False
            in_lightbox = any(
                t_name == "div" and eid in _LIGHTBOX_IDS
                for t_name, _, eid in self._open_stack
            )
            for k, v in attrs:
                kl = (k or "").lower()
                if kl == "alt":
                    has_alt = True
                elif kl == "src" and v is not None:
                    src_val = v.strip()
                    if not src_val:
                        continue
                    has_nonempty_src = True
                    norm_uri = _STRIP_CTRL_WS_RX.sub("", src_val)
                    if _DATA_IMG_RX.match(norm_uri):
                        self.b64_count += 1
                    elif (
                        norm_uri.startswith(("//", "\\\\"))
                        or (_URI_SCHEME_RX.match(norm_uri) and not _EXTERNAL_URL_RX.match(norm_uri))
                    ):
                        pass  # Caught by URI allowlist security check below
                    elif _EXTERNAL_URL_RX.match(norm_uri):
                        if not self._allow_external_images:
                            self._add_issue(self.external_img_srcs, self._seen_ext_imgs, src_val[:120])
                    else:
                        self.unembedded_imgs += 1
                        self._add_issue(self.unembedded_img_srcs, self._seen_unembedded_imgs, src_val[:120])
            if not has_nonempty_src and not in_lightbox:
                self.unembedded_imgs += 1
                self._add_issue(self.unembedded_img_srcs, self._seen_unembedded_imgs, "<empty src>")
            if not has_alt:
                self.missing_alt_imgs += 1
        elif t == "table":
            self.table_count += 1
            if any(is_w for _, is_w, _ in self._open_stack):
                self.wrapped_table_count += 1

        is_wrapper = False
        elem_id = ""
        meta_http_equiv = ""
        link_rels: set[str] = set()
        for k, v in attrs:
            kl = (k or "").lower()
            if kl == "rel" and t == "link" and v:
                link_rels.update(tok for tok in v.lower().split() if tok)

        for k, v in attrs:
            kl = (k or "").lower()
            val_str = "" if v is None else v
            if _EVENT_HANDLER_ATTR_RX.match(kl) or kl in ("srcdoc", "ping"):
                self._add_issue(self.disallowed_event_handlers, self._seen_handlers, f"<{t} {kl}>")
            if kl == "srcset" and val_str.strip():
                self._add_issue(
                    self.disallowed_external_resources,
                    self._seen_ext_res,
                    f'<{t} srcset="{val_str.strip()[:100]}">',
                )
            if kl in ("id", "name") and val_str.strip().lower() == "mathjax":
                self._add_issue(
                    self.disallowed_tags,
                    self._seen_tags,
                    f'<{t} {kl}="MathJax"> (DOM clobbering)',
                )
            if kl == "id" and val_str:
                id_val = val_str.strip()
                if id_val:
                    elem_id = id_val.lower()
                    self.seen_ids.add(id_val)
            elif kl == "class" and val_str and t != "table":
                if "table-wrapper" in val_str.lower().split():
                    is_wrapper = True
            elif kl == "http-equiv" and t == "meta" and val_str:
                meta_http_equiv = val_str.strip().lower()
            elif kl == "style" and val_str:
                self._scan_css_text(val_str, source=f"<{t} style>")

            if kl in _URI_ATTRS and val_str:
                norm_uri = _STRIP_CTRL_WS_RX.sub("", val_str)
                if norm_uri:
                    # Strict URI allowlist by element/attribute role
                    if norm_uri.startswith(("//", "\\\\")):
                        self._add_issue(
                            self.dangerous_uris,
                            self._seen_uris,
                            f'<{t} {kl}="{norm_uri[:60]}">',
                        )
                    elif t in ("a", "area") and kl == "href":
                        if _URI_SCHEME_RX.match(norm_uri) and not _SAFE_LINK_SCHEME_RX.match(norm_uri):
                            self._add_issue(
                                self.dangerous_uris,
                                self._seen_uris,
                                f'<{t} {kl}="{norm_uri[:60]}">',
                            )
                    elif t == "link" and kl == "href":
                        if _URI_SCHEME_RX.match(norm_uri) and not _ALLOWED_CSS_REMOTE_RX.match(norm_uri):
                            if _DANGEROUS_URI_SCHEME_RX.match(norm_uri) or norm_uri.lower().startswith("data:"):
                                self._add_issue(
                                    self.dangerous_uris,
                                    self._seen_uris,
                                    f'<link href="{norm_uri[:60]}">',
                                )
                            else:
                                self._add_issue(
                                    self.disallowed_external_resources,
                                    self._seen_ext_res,
                                    f'<link href="{val_str.strip()[:100]}">',
                                )
                        elif not _ALLOWED_CSS_REMOTE_RX.match(norm_uri) or (link_rels and not (link_rels <= _ALLOWED_LINK_RELS)):
                            self._add_issue(
                                self.disallowed_external_resources,
                                self._seen_ext_res,
                                f'<link href="{val_str.strip()[:100]}">',
                            )
                    elif t == "img" and kl == "src":
                        if _URI_SCHEME_RX.match(norm_uri):
                            if _DATA_IMG_RX.match(norm_uri) or _EXTERNAL_URL_RX.match(norm_uri):
                                pass  # Handled cleanly in `t == "img"` block above
                            else:
                                self._add_issue(
                                    self.dangerous_uris,
                                    self._seen_uris,
                                    f'<img src="{norm_uri[:60]}">',
                                )
                    elif t == "script" and kl == "src":
                        if _URI_SCHEME_RX.match(norm_uri) and not _ALLOWED_MATHJAX_SRC_RX.match(norm_uri):
                            if not _EXTERNAL_URL_RX.match(norm_uri):
                                self._add_issue(
                                    self.dangerous_uris,
                                    self._seen_uris,
                                    f'<script src="{norm_uri[:60]}">',
                                )
                    else:
                        # All remaining URI attributes (SVG <use>/<image>/<feImage>, <audio>/<video>/<source>,
                        # background/poster/data/action/formaction): allow only internal #fragment references.
                        if not norm_uri.startswith("#"):
                            if _EXTERNAL_URL_RX.match(norm_uri) and (
                                (t in _SVG_EXTERNAL_HREF_TAGS and kl in ("href", "xlink:href"))
                                or (t in _MEDIA_SRC_TAGS and kl == "src")
                                or kl in ("background", "poster")
                            ):
                                self._add_issue(
                                    self.disallowed_external_resources,
                                    self._seen_ext_res,
                                    f'<{t} {kl}="{val_str.strip()[:100]}">',
                                )
                            elif _URI_SCHEME_RX.match(norm_uri):
                                self._add_issue(
                                    self.dangerous_uris,
                                    self._seen_uris,
                                    f'<{t} {kl}="{norm_uri[:60]}">',
                                )
                            else:
                                self._add_issue(
                                    self.disallowed_external_resources,
                                    self._seen_ext_res,
                                    f'<{t} {kl}="{val_str.strip()[:100]}">',
                                )
                if kl == "href":
                    href_val = val_str.strip()
                    if href_val.startswith("#") and len(href_val) > 1:
                        self.anchor_refs.append(href_val[1:])

        if t == "meta" and meta_http_equiv in _FORBIDDEN_META_HTTP_EQUIV:
            self._add_issue(self.disallowed_tags, self._seen_tags, f'<meta http-equiv="{meta_http_equiv}">')

        if not self_closing and t not in _HTML_VOID_TAGS:
            self._open_stack.append((t, is_wrapper, elem_id))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._process_start_tag(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._process_start_tag(tag, attrs, self_closing=True)

    def handle_endtag(self, tag: str) -> None:
        self._flush_prose()
        t = tag.lower()
        raw_tag = self._current_raw_tag()
        if raw_tag is not None:
            if t != raw_tag:
                return
            if raw_tag == "script":
                self._finalize_active_script()
            elif raw_tag == "style":
                self._finalize_style_block()
            self._pop_open_tag(t)
            return
        if t == "head":
            self.has_head_close = True
        elif t == "body":
            self.has_body_close = True
        self._pop_open_tag(t)

    def handle_data(self, data: str) -> None:
        if self._active_script is not None:
            body_chunks = self._active_script["body"]
            assert isinstance(body_chunks, list)
            body_chunks.append(data)
            return
        if self._current_raw_tag() == "style":
            self._style_buf.append(data)
            return
        if self._in_tags(_LATEX_IGNORED_TAGS):
            return
        self._prose_buf.append(data)

    def handle_comment(self, data: str) -> None:
        self._flush_prose()

    def close(self) -> None:
        self._flush_prose()
        self._finalize_active_script()
        self._finalize_style_block()
        super().close()


def run_html_qa_check(
    html_text: str,
    skip_table_wrapper_check: bool = False,
    *,
    allowed_inline_scripts: frozenset[str] | None = None,
    shell_path: Path | None = None,
    allow_external_images: bool = False,
) -> _QADOMScanner:
    """Validate structure, security policy, Base64 images, alt tags, .table-wrapper nesting, MathJax, and anchors."""
    if allowed_inline_scripts is None:
        allowed_scripts = (
            frozenset()
            if skip_table_wrapper_check
            else _extract_trusted_shell_scripts(shell_path=shell_path)
        )
    else:
        allowed_scripts = allowed_inline_scripts

    scanner = _QADOMScanner(
        allowed_inline_scripts=allowed_scripts,
        allow_external_images=allow_external_images,
    )
    scanner.feed(html_text)
    scanner.close()

    issues: list[str] = []
    if not (
        scanner.has_head_open
        and scanner.has_head_close
        and scanner.has_body_open
        and scanner.has_body_close
    ):
        issues.append("HTML must contain complete <head>...</head> and <body>...</body> sections.")

    if scanner.disallowed_scripts:
        issues.append(
            f"Disallowed <script> tag(s) (only trusted MathJax CDN in <head> is permitted): "
            f"{_format_sample_items(scanner.disallowed_scripts)}"
        )
    if scanner.disallowed_tags:
        issues.append(f"Disallowed HTML tag(s): {_format_sample_items(scanner.disallowed_tags)}")
    if scanner.disallowed_event_handlers:
        issues.append(
            f"Disallowed inline event handler attribute(s): {_format_sample_items(scanner.disallowed_event_handlers)}"
        )
    if scanner.dangerous_uris:
        issues.append(f"Disallowed dangerous URI(s): {_format_sample_items(scanner.dangerous_uris)}")
    if scanner.external_img_srcs:
        issues.append(
            f"Disallowed external <img> URL(s) (images must be local Base64 assets): "
            f"{_format_sample_items(scanner.external_img_srcs)}"
        )
    if scanner.disallowed_external_resources:
        issues.append(
            f"Disallowed external resource reference(s): "
            f"{_format_sample_items(scanner.disallowed_external_resources)}"
        )

    if scanner.unembedded_imgs > 0:
        detail = f": {_format_sample_items(scanner.unembedded_img_srcs)}" if scanner.unembedded_img_srcs else ""
        issues.append(f"Found {scanner.unembedded_imgs} un-embedded local <img> src link(s){detail}.")
    if scanner.missing_alt_imgs > 0:
        issues.append(f"Found {scanner.missing_alt_imgs} <img> tag(s) missing alt attribute.")

    unwrapped_tables = scanner.table_count - scanner.wrapped_table_count
    if not skip_table_wrapper_check and unwrapped_tables > 0:
        issues.append(
            f"Found {unwrapped_tables} <table> element(s) not wrapped inside a .table-wrapper container."
        )

    if scanner.has_latex and not scanner.has_mathjax_in_head:
        issues.append("Detected LaTeX math delimiters without MathJax <script> in <head>.")

    broken_anchors: list[str] = []
    seen_broken: set[str] = set()
    for anchor in scanner.anchor_refs:
        if anchor not in scanner.seen_ids and anchor not in seen_broken:
            seen_broken.add(anchor)
            broken_anchors.append(f"#{anchor}")
    if broken_anchors:
        issues.append(f"Broken internal anchor(s): {', '.join(broken_anchors)}")

    if issues:
        raise ValueError("HTML Auto-QA FAILED:\n - " + "\n - ".join(issues))

    table_status = (
        f"Tables: {scanner.table_count} (wrapper optional)"
        if skip_table_wrapper_check
        else f"Tables wrapped: {scanner.wrapped_table_count}/{scanner.table_count}"
    )
    print(f"[QA PASS] Base64 images: {scanner.b64_count} | {table_status} | LaTeX/MathJax OK | Broken anchors: 0")
    return scanner


def _prepare_sanitized_output_path(raw_path_str: str, label: str) -> Path:
    """Reject path-level attacks (UNC, non-FS, NTFS ADS, symlinks) while auto-sanitizing unsafe filenames."""
    raw = raw_path_str.strip()
    if re.match(r"^[A-Za-z0-9_.-]+::", raw) and not raw.lower().startswith("filesystem::"):
        raise ValueError(f"Refusing non-filesystem path for {label}: {raw}")
    if not raw.lower().startswith(("file://", "http://", "https://")) and re.match(r"^[A-Za-z]{2,}:", raw):
        raise ValueError(f"Refusing non-filesystem path for {label}: {raw}")
    assert_local_no_unc_path(raw, label)

    parent_str, leaf_str = os.path.split(raw)
    abs_parent = Path(os.path.abspath(parent_str)) if parent_str else Path(os.path.abspath("."))
    cand = abs_parent / leaf_str
    sanitized, changed = sanitize_output_filename(cand)
    if changed:
        print(f"Sanitized unsafe output filename -> {sanitized}")
    dest = assert_safe_output_path(sanitized, label=label, is_directory=False)
    assert dest is not None
    return dest


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
    *,
    _qa_verified: bool = False,
    shell_path: Path | None = None,
) -> Path | None:
    """Convert HTML to printable PDF via hardened headless Edge/Chrome after security Auto-QA."""
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
    html_sz = abs_html.stat().st_size
    if html_sz > MAX_INPUT_HTML_BYTES:
        raise ValueError(f"Refusing oversized HTML input ({html_sz:,} bytes > {MAX_INPUT_HTML_BYTES:,} byte limit): {abs_html}")

    if not _qa_verified:
        html_text = abs_html.read_text(encoding="utf-8-sig")
        trusted_scripts = _extract_trusted_shell_scripts(shell_path=shell_path)
        run_html_qa_check(
            html_text,
            skip_table_wrapper_check=True,
            allowed_inline_scripts=trusted_scripts,
            shell_path=shell_path,
        )

    raw_pdf = str(out_pdf_path or "").strip()
    dest_pdf = _prepare_sanitized_output_path(
        raw_pdf if raw_pdf else str(abs_html.with_suffix(".pdf")),
        label="-OutPdfPath",
    )

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
            "--disable-extensions",
            "--disable-sync",
            "--no-first-run",
            "--disable-default-apps",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-translate",
            f"--host-resolver-rules={_HEADLESS_ALLOWED_HOSTS_RULE}",
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
    quality: int = 95,
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
    html_sz = abs_html.stat().st_size
    if html_sz > MAX_INPUT_HTML_BYTES:
        raise ValueError(f"Refusing oversized HTML input ({html_sz:,} bytes > {MAX_INPUT_HTML_BYTES:,} byte limit): {abs_html}")
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

    updated, _ = _sub_outside_ignored(content, IMG_TAG_RX, _replace_img_tag)

    shell_injected: list[str] = []
    if not preserve_layout:
        updated, shell_injected = inject_reader_shell(updated, shell_path=shell_path)

    updated = updated.replace("\r\n", "\n").replace("\r", "\n")
    qa_scanner = run_html_qa_check(updated, skip_table_wrapper_check=preserve_layout, shell_path=shell_path)
    updated = inject_csp_meta(
        updated,
        has_mathjax=qa_scanner.has_mathjax_in_head,
        inline_script_raw_bodies=qa_scanner.allowed_inline_script_raw_bodies,
    )

    has_explicit_out_html = bool(out_html_path and out_html_path.strip())
    if has_explicit_out_html:
        dest = _prepare_sanitized_output_path(out_html_path, label="-OutHtmlPath")
    else:
        dest = assert_safe_output_path(abs_html, label="-OutHtmlPath", is_directory=False)
        assert dest is not None

    has_custom_out_pdf = bool(out_pdf_path and out_pdf_path.strip())
    want_pdf = also_pdf or has_custom_out_pdf
    pdf_protected: Path | None = None
    if want_pdf:
        if has_custom_out_pdf:
            pdf_protected = _prepare_sanitized_output_path(out_pdf_path, label="-OutPdfPath")
        else:
            pdf_protected = assert_safe_output_path(dest.with_suffix(".pdf"), label="-OutPdfPath", is_directory=False)

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
    dest.write_text(updated, encoding="utf-8", newline="\n")
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
        exported_pdf = html_to_pdf(
            dest,
            out_pdf_path=pdf_protected,
            clean_dir="",
            timeout_seconds=timeout_seconds,
            _qa_verified=True,
            shell_path=shell_path,
        )

    if clean_dir and clean_dir.strip():
        protected = [dest] + ([exported_pdf] if exported_pdf is not None else [pdf_protected] if pdf_protected else [])
        safe_clean_dir(clean_dir, protected_paths=protected)

    return dest, exported_pdf
