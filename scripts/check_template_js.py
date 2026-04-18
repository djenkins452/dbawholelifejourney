#!/usr/bin/env python3
"""
JavaScript syntax validator for WLJ — templates + static files.

Covers two classes of silent-JS-failure that Django itself cannot see:

1. **Inline scripts in Django templates** (`templates/**/*.html`). Extracts
   every `<script>` body, strips Django template tags (`{% %}` and `{{ }}`)
   while preserving line numbers, then runs `node --check` on each body.

2. **Standalone JS files** (`static/**/*.js`). Runs `node --check` directly.

Both feed a single unified report with per-category counts and hard-fail
on any error.

Motivation
----------
2026-04-06 — commit 39c7d54e (find-replace rename across templates)
silently corrupted a single JS string literal inside
`templates/scan/scan_page.html`. The invalid JS killed the entire IIFE
wrapping the scan page, so camera/barcode food logging was dead for 11
days with no server error, no visible client error, and no test failure.

Django's `manage.py check` cannot catch this — it treats `<script>`
content as opaque text. Standalone `.js` files in `static/` have the
same gap: they're served verbatim by `staticfiles`, so a typo produces
a browser-side SyntaxError that only an end-user would notice.

This script closes both gaps.

Scope
-----
- Checks: JavaScript **syntax correctness** only.
- Does NOT check: linting rules, style, variable values, runtime
  behavior, or third-party vendor files under configurable skip
  patterns.
- Does NOT execute any JavaScript — only `node --check`.

Usage
-----
    python3 scripts/check_template_js.py                    # scan all
    python3 scripts/check_template_js.py path/to/file.html  # scan one
    python3 scripts/check_template_js.py a.html static/b.js # mixed

Exit codes
----------
- 0 if all scripts pass
- 1 if any script has a syntax error
- 2 if `node` is missing or the scanner itself failed
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

# Inline <script> open tag + body + closing </script>. Non-greedy body.
# Simple regex is adequate — real templates are well-formed enough and we
# don't want a heavy HTML parser for a linting tool.
SCRIPT_BLOCK_RE = re.compile(
    r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>",
    re.IGNORECASE | re.DOTALL,
)

# Django tags. We replace instead of deleting so that line numbers inside
# the script body stay aligned with the original template (one source
# line in the template = one line in the cleaned script).
DJANGO_BLOCK_RE = re.compile(r"\{%.*?%\}", re.DOTALL)
DJANGO_VAR_RE = re.compile(r"\{\{.*?\}\}", re.DOTALL)

# Matches `{% else %}...{% endif %}` or `{% elif ... %}...{% endif %}`.
# Non-greedy + repeated application handles nested ifs innermost-first.
# We drop these branches because static JS validation would otherwise see
# BOTH branches as concatenated code, producing false positives on
# patterns like `x = {% if %}{{ a }}{% else %}fallback{% endif %};`.
ELSE_OR_ELIF_BLOCK_RE = re.compile(
    r"\{%\s*(?:else|elif\b[^%]*)\s*%\}.*?\{%\s*endif\s*%\}",
    re.DOTALL,
)

# Lines that are pure attribute noise we skip when reporting.
SRC_ATTR_RE = re.compile(r"""\bsrc\s*=\s*["'][^"']+["']""", re.IGNORECASE)

# `node --check` error format — first line of stderr is `/tmp/xxx.js:LINE`.
NODE_ERROR_LOCATION_RE = re.compile(r":(\d+)\b")

# ---------------------------------------------------------------------------
# Skip rules
# ---------------------------------------------------------------------------

# Path fragments that mark third-party bundles we should NOT validate.
# These are generally minified and/or target older/newer JS than our
# installed Node can parse, and we don't own their source anyway.
#
# Check is substring-based on the POSIX-style path. Keep this list short
# — if it grows, prefer a `.jscheckignore` file instead.
VENDOR_SKIP_FRAGMENTS = (
    "/vendor/",
    "/vendors/",
    "/node_modules/",
    "/dist/",
    ".min.js",
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ScriptBlock:
    """One inline <script> block extracted from a template."""

    template_path: Path
    # 1-based line number in the original template where the script body
    # starts (the line immediately after the opening <script ...> tag).
    start_line: int
    body: str
    has_src: bool

    def cleaned_for_node(self) -> str:
        return _strip_django_tags(self.body)


@dataclass
class ValidationError:
    """One syntax error, reportable in `source_path:line` form."""

    source_path: Path
    source_line: int
    node_message: str
    # "template" (inline <script>) or "static" (standalone .js). Used for
    # the per-category count in the final report.
    kind: str


# ---------------------------------------------------------------------------
# Django tag stripping (templates only)
# ---------------------------------------------------------------------------


def _blank_preserving_newlines(match: re.Match) -> str:
    """Replace match with whitespace of identical line shape."""
    text = match.group(0)
    return "".join("\n" if ch == "\n" else " " for ch in text)


def _strip_django_tags(source: str) -> str:
    """
    Replace Django template tags with JS-safe placeholders while
    preserving line count (so Node's line numbers map back to the
    template).

    Three passes:

    1. Drop `{% else %}...{% endif %}` and `{% elif ... %}...{% endif %}`
       branches. Keeping both branches of a conditional would make Node
       see code like `let x = null null;` and flag a false positive.
       Repeated application handles nested ifs (innermost first).

    2. Blank the remaining `{% ... %}` tags themselves.

    3. Replace `{{ ... }}` with `(0)` — a valid JS expression that
       survives being adjacent to other `(0)`s (e.g. `(0)(0)` parses as
       a call-expression, which is syntactically valid — runtime errors
       don't matter, only syntax).

    All passes preserve newlines so Node error line numbers map back
    to the template 1:1.
    """
    # Phase 1: drop alternate branches. Repeat until stable.
    prev = None
    current = source
    while prev != current:
        prev = current
        current = ELSE_OR_ELIF_BLOCK_RE.sub(_blank_preserving_newlines, current)

    # Phase 2: blank remaining Django block tags.
    current = DJANGO_BLOCK_RE.sub(_blank_preserving_newlines, current)

    # Phase 3: replace `{{ ... }}` with a syntactically safe token.
    def _var_to_safe_expr(match: re.Match) -> str:
        text = match.group(0)
        placeholder = "(0)"
        if "\n" in text:
            lines = text.split("\n")
            head = placeholder + " " * max(0, len(lines[0]) - len(placeholder))
            tail = ["\n" + " " * len(line) for line in lines[1:]]
            return head + "".join(tail)
        width = len(text)
        if width >= len(placeholder):
            return placeholder + " " * (width - len(placeholder))
        return " " * width

    current = DJANGO_VAR_RE.sub(_var_to_safe_expr, current)
    return current


# ---------------------------------------------------------------------------
# Extraction — templates
# ---------------------------------------------------------------------------


def _line_of_offset(source: str, offset: int) -> int:
    """1-based line number of `offset` in `source`."""
    return source.count("\n", 0, offset) + 1


def extract_script_blocks(template_path: Path) -> List[ScriptBlock]:
    """Return every inline script block found in the template file."""
    try:
        source = template_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    blocks: List[ScriptBlock] = []
    for match in SCRIPT_BLOCK_RE.finditer(source):
        attrs = match.group("attrs") or ""
        body = match.group("body") or ""
        has_src = bool(SRC_ATTR_RE.search(attrs))

        if has_src and not body.strip():
            # External script with no inline body — nothing to validate.
            continue
        if not body.strip():
            # Empty inline script — valid JS, skip.
            continue

        body_offset = match.start("body")
        start_line = _line_of_offset(source, body_offset)

        blocks.append(
            ScriptBlock(
                template_path=template_path,
                start_line=start_line,
                body=body,
                has_src=has_src,
            )
        )
    return blocks


# ---------------------------------------------------------------------------
# Validation — shared node runner
# ---------------------------------------------------------------------------


def _ensure_node_available() -> Optional[str]:
    return shutil.which("node")


def _run_node_check(node_bin: str, js_path: Path):
    """Run `node --check PATH` and return (returncode, stderr_text)."""
    try:
        result = subprocess.run(
            [node_bin, "--check", str(js_path)],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return 124, f"node --check timed out (>15s) on {js_path}"
    return result.returncode, result.stderr or result.stdout or ""


def _parse_node_error_line(stderr: str) -> int:
    """Extract the relative line number from Node's stderr. Default 1."""
    for line in stderr.splitlines():
        m = NODE_ERROR_LOCATION_RE.search(line)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    return 1


# ---------------------------------------------------------------------------
# Validation — templates
# ---------------------------------------------------------------------------


def validate_block(
    block: ScriptBlock, node_bin: str
) -> Optional[ValidationError]:
    """Validate a single inline <script> body. Returns error or None."""
    cleaned = block.cleaned_for_node()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(cleaned)
        tmp_path = Path(tmp.name)

    try:
        rc, stderr = _run_node_check(node_bin, tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if rc == 0:
        return None

    relative_line = _parse_node_error_line(stderr)
    # Remap: body line 1 == template line block.start_line.
    template_line = block.start_line + relative_line - 1
    cleaned_stderr = stderr.replace(str(tmp_path), "<inline-script>")
    return ValidationError(
        source_path=block.template_path,
        source_line=template_line,
        node_message=cleaned_stderr.strip(),
        kind="template",
    )


def validate_template_file(
    path: Path, node_bin: str
) -> List[ValidationError]:
    errors: List[ValidationError] = []
    for block in extract_script_blocks(path):
        err = validate_block(block, node_bin)
        if err is not None:
            errors.append(err)
    return errors


# ---------------------------------------------------------------------------
# Validation — static .js files
# ---------------------------------------------------------------------------


def validate_static_js_file(
    path: Path, node_bin: str
) -> List[ValidationError]:
    """Run `node --check` directly on a standalone .js file."""
    rc, stderr = _run_node_check(node_bin, path)
    if rc == 0:
        return []
    relative_line = _parse_node_error_line(stderr)
    # Node reports absolute paths — replace with the relative path we
    # passed in so the report is readable.
    cleaned_stderr = stderr.replace(str(path), str(path))
    return [
        ValidationError(
            source_path=path,
            source_line=relative_line,
            node_message=cleaned_stderr.strip(),
            kind="static",
        )
    ]


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def _is_skipped_vendor(path: Path) -> bool:
    posix = path.as_posix()
    return any(frag in posix for frag in VENDOR_SKIP_FRAGMENTS)


def _iter_files_for_root(root: Path) -> Iterable[Path]:
    """
    Walk a directory yielding validation candidates:
    - `.html` under any `templates/` subtree
    - `.js` under any `static/` subtree
    Vendor/minified paths are skipped.
    """
    # Templates
    for path in root.rglob("*.html"):
        # skip backup files like `home.html.bak3`
        if ".bak" in path.name:
            continue
        yield path
    # Static JS
    for path in root.rglob("*.js"):
        if _is_skipped_vendor(path):
            continue
        yield path


def iter_candidate_files(roots: Iterable[Path]) -> Iterable[Path]:
    """
    Expand CLI inputs into individual files to validate.

    - A file path is yielded as-is (after vendor skip for .js).
    - A directory is walked for .html and .js files.
    """
    for root in roots:
        if root.is_file():
            if root.suffix == ".html":
                if ".bak" in root.name:
                    continue
                yield root
            elif root.suffix == ".js":
                if not _is_skipped_vendor(root):
                    yield root
            continue
        if not root.is_dir():
            continue
        for path in _iter_files_for_root(root):
            yield path


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def _classify(path: Path) -> str:
    """Return 'template' or 'static' based on file extension."""
    return "template" if path.suffix == ".html" else "static"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories. Defaults to ./templates/ and ./static/",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only print on failure.",
    )
    args = parser.parse_args(argv)

    node_bin = _ensure_node_available()
    if not node_bin:
        sys.stderr.write(
            "ERROR: `node` is not installed or not on PATH.\n"
            "Install Node.js (https://nodejs.org/) or skip this check.\n"
        )
        return 2

    if args.paths:
        roots = [Path(p) for p in args.paths]
    else:
        roots = [Path("templates"), Path("static")]
        roots = [r for r in roots if r.exists()]
        if not roots:
            if not args.quiet:
                sys.stdout.write("No default roots found (templates/, static/).\n")
            return 0

    # Expand and classify.
    candidates = list(iter_candidate_files(roots))
    templates = [p for p in candidates if _classify(p) == "template"]
    static_js = [p for p in candidates if _classify(p) == "static"]

    # Validate.
    template_errors: List[ValidationError] = []
    static_errors: List[ValidationError] = []

    template_script_count = 0
    for path in templates:
        blocks = extract_script_blocks(path)
        template_script_count += len(blocks)
        for block in blocks:
            err = validate_block(block, node_bin)
            if err is not None:
                template_errors.append(err)

    for path in static_js:
        static_errors.extend(validate_static_js_file(path, node_bin))

    all_errors = template_errors + static_errors

    if all_errors:
        sys.stderr.write(
            "\n"
            + "=" * 72
            + "\n"
            + "  JS validation FAILED\n"
            + "=" * 72
            + "\n"
        )
        for err in all_errors:
            try:
                rel = err.source_path.relative_to(Path.cwd())
            except ValueError:
                rel = err.source_path
            label = "[template]" if err.kind == "template" else "[static]  "
            sys.stderr.write(f"\n{label} {rel}:{err.source_line}\n")
            for line in err.node_message.splitlines():
                sys.stderr.write(f"  {line}\n")
        sys.stderr.write(
            "\n"
            + "=" * 72
            + "\n"
            + f"  Template JS errors : {len(template_errors)}\n"
            + f"  Static JS errors   : {len(static_errors)}\n"
            + f"  Total errors       : {len(all_errors)}\n"
            + f"  Scanned            : {len(templates)} templates "
            + f"({template_script_count} inline scripts), "
            + f"{len(static_js)} static .js files\n"
            + "=" * 72
            + "\n"
        )
        return 1

    if not args.quiet:
        sys.stdout.write(
            f"OK — {len(templates)} templates ({template_script_count} inline scripts), "
            f"{len(static_js)} static .js files, 0 errors.\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
