#!/usr/bin/env python3
"""
Django template JavaScript syntax validator.

Scans Django templates for `<script>` blocks, strips Django template tags
(`{% ... %}` and `{{ ... }}`), and runs `node --check` on each inline
script body to catch JavaScript syntax errors before they reach
production.

Motivation
----------
This exists because of a real production incident: on 2026-04-06 a bulk
find-replace across templates (Medicine → Intake rename) silently
mangled a single JavaScript string literal in `templates/scan/scan_page.html`
into invalid JS. The parse error killed the entire IIFE wrapping the
scan page's scripts, so the camera never started and every button was
dead. The page looked loaded but was non-functional, with no
server-side error and no visible client-side indication. Users were
blocked on food scanning for 11 days before the bug was reported.

Django's own checks cannot catch this — it treats `<script>` content
as opaque text. Nothing else in the stack will parse it either. This
script fills that gap.

Scope
-----
- Checks: inline `<script>...</script>` syntax correctness only.
- Does NOT check: external `<script src="...">` files, linting rules,
  Django variable values, runtime behavior.
- Does NOT execute any JavaScript — only `node --check`.

Usage
-----
    python3 scripts/check_template_js.py                  # scan all
    python3 scripts/check_template_js.py path/to/tpl.html # scan one
    python3 scripts/check_template_js.py --files file1 file2 ...

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

# Match <script> open tags (capturing attributes and their position) and
# the matching closing </script>. Non-greedy body match.
# We intentionally use a simple regex here because we only care about
# `<script>` tags in Django templates, not arbitrary HTML with nested
# commented-out script tags. Real templates are well-formed enough.
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
        """Strip Django tags, preserving line count for error mapping."""
        return _strip_django_tags(self.body)


# ---------------------------------------------------------------------------
# Extraction
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

    2. Blank the remaining `{% ... %}` tags themselves (if/for/endif
       openers, `{% block %}`, custom tags, etc.).

    3. Replace `{{ ... }}` with `(0)` — a valid JS expression that
       survives being adjacent to other `(0)`s (e.g. `(0)(0)` parses
       as a call-expression, which is syntactically valid — runtime
       errors don't matter to us, only syntax).

    All passes preserve newlines so Node error line numbers map back
    to the template 1:1.
    """
    # Phase 1: drop alternate branches. Repeat until stable.
    prev = None
    current = source
    while prev != current:
        prev = current
        current = ELSE_OR_ELIF_BLOCK_RE.sub(_blank_preserving_newlines, current)

    # Phase 2: blank remaining Django block tags (`{% ... %}`).
    current = DJANGO_BLOCK_RE.sub(_blank_preserving_newlines, current)

    # Phase 3: replace `{{ ... }}` with a syntactically safe token.
    # `(0)` is a valid JS expression that composes safely with adjacent
    # copies of itself (`(0)(0)` is a valid call-expression), so
    # consecutive template variables never produce a syntax error.
    def _var_to_safe_expr(match: re.Match) -> str:
        text = match.group(0)
        placeholder = "(0)"
        if "\n" in text:
            # Multi-line variable — preserve newlines exactly and
            # drop the placeholder on the first line if it fits.
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


def _line_of_offset(source: str, offset: int) -> int:
    """1-based line number of `offset` in `source`."""
    # Count newlines up to offset.
    return source.count("\n", 0, offset) + 1


def extract_script_blocks(template_path: Path) -> List[ScriptBlock]:
    """Return every inline script block found in the template file."""
    try:
        source = template_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Binary-ish template? Skip safely.
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

        # Body starts on the line AFTER the opening <script ...> tag,
        # unless the script is all on one line in which case it starts
        # on the same line. We approximate by using the offset of the
        # body match inside the source.
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
# Validation
# ---------------------------------------------------------------------------


@dataclass
class ValidationError:
    template_path: Path
    template_line: int
    node_message: str


def _ensure_node_available() -> Optional[str]:
    """Return path to `node`, or None if missing."""
    return shutil.which("node")


# node --check error format: `/tmp/xxx.js:LINE`
NODE_ERROR_LOCATION_RE = re.compile(r":(\d+)\b")


def validate_block(block: ScriptBlock, node_bin: str) -> Optional[ValidationError]:
    cleaned = block.cleaned_for_node()

    # Write to a temp file. Use a `.mjs` extension? No — default to `.js`
    # because template JS is almost always classic scripts, not ES
    # modules, and we don't want spurious "top-level await" rejections.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(cleaned)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [node_bin, "--check", tmp_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return ValidationError(
            template_path=block.template_path,
            template_line=block.start_line,
            node_message="node --check timed out (>15s)",
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if result.returncode == 0:
        return None

    # Parse Node's error. First line of stderr typically looks like:
    #   /tmp/xxx.js:42
    # Second line shows the offending source, third line a caret, then
    # the error class. We scrape the relative line number and remap it
    # to the template line.
    stderr = result.stderr or result.stdout or ""
    relative_line = 1
    for line in stderr.splitlines():
        m = NODE_ERROR_LOCATION_RE.search(line)
        if m:
            try:
                relative_line = int(m.group(1))
            except ValueError:
                pass
            break

    # Remap: body line 1 == template_path:block.start_line
    template_line = block.start_line + relative_line - 1

    # Clean stderr: strip the tmp path for readability.
    cleaned_stderr = stderr.replace(tmp_path, "<inline-script>")
    return ValidationError(
        template_path=block.template_path,
        template_line=template_line,
        node_message=cleaned_stderr.strip(),
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def iter_template_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_file():
            if root.suffix == ".html":
                yield root
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("*.html"):
            # Skip backup files like `home.html.bak3`
            name = path.name
            if name.endswith(".bak") or ".bak" in name:
                continue
            yield path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to scan. Defaults to ./templates/",
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
        roots = [Path("templates")]

    templates = list(iter_template_files(roots))
    if not templates:
        if not args.quiet:
            sys.stdout.write("No templates found to scan.\n")
        return 0

    errors: List[ValidationError] = []
    scanned = 0
    blocks_total = 0
    for template in templates:
        blocks = extract_script_blocks(template)
        scanned += 1
        blocks_total += len(blocks)
        for block in blocks:
            err = validate_block(block, node_bin)
            if err is not None:
                errors.append(err)

    if errors:
        sys.stderr.write(
            "\n"
            + "=" * 72
            + "\n"
            + f"  Template JS validation FAILED — {len(errors)} error(s)\n"
            + "=" * 72
            + "\n"
        )
        for err in errors:
            rel = err.template_path
            try:
                rel = err.template_path.relative_to(Path.cwd())
            except ValueError:
                pass
            sys.stderr.write(f"\n{rel}:{err.template_line}\n")
            for line in err.node_message.splitlines():
                sys.stderr.write(f"  {line}\n")
        sys.stderr.write(
            "\n"
            + "=" * 72
            + "\n"
            + f"  Scanned {scanned} templates, {blocks_total} inline scripts\n"
            + "=" * 72
            + "\n"
        )
        return 1

    if not args.quiet:
        sys.stdout.write(
            f"OK — {scanned} templates, {blocks_total} inline scripts, 0 errors.\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
