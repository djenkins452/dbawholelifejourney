# ==============================================================================
# File: apps/life/services/email_body_cleaner.py
# Description: Phase 6B.5 — Deterministic email body cleaning for receipt docs
# Created: 2026-03-17
# ==============================================================================
"""
clean_email_body — Strip HTML, decode entities, normalize whitespace.

Used by _create_receipt_documents() before storing body in Document.raw_text.
Deterministic, no LLM. Practical, not a full email parser.
"""

import html
import re

# --- Pre-compiled patterns ---

# Script/style blocks (greedy match)
_SCRIPT_STYLE_RE = re.compile(
    r'<(script|style)[^>]*>.*?</\1>', re.IGNORECASE | re.DOTALL,
)

# HTML comments
_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)

# All HTML tags
_TAG_RE = re.compile(r'<[^>]+>')

# Footer line pattern — matches individual lines that are footer noise.
# Uses re.MULTILINE so ^ and $ anchor to line boundaries, NOT re.DOTALL
# which would cause .* to consume across lines and eat receipt content.
_FOOTER_LINE_RE = re.compile(
    r'^(?:'
    r'[-_=]{3,}'                              # separator lines
    r'|.*unsubscribe.*'                       # unsubscribe links
    r'|.*manage\s+(?:your\s+)?(?:preferences|subscriptions|notifications).*'
    r'|.*view\s+(?:this\s+)?(?:email\s+)?in\s+(?:your\s+)?browser.*'
    r'|.*this\s+(?:email|message)\s+was\s+sent\s+(?:to|by).*'
    r'|.*you\s+(?:are\s+)?receiv(?:ed|ing)\s+this.*'
    r'|.*if\s+you\s+(?:no\s+longer|don\'t)\s+(?:wish|want).*'
    r'|.*(?:do\s+not\s+reply|no-?reply).*'
    r'|.*©\s*\d{4}.*'                         # copyright lines
    r'|.*all\s+rights\s+reserved.*'
    r'|.*privacy\s+policy.*'
    r'|.*terms\s+(?:of\s+)?(?:service|use).*'
    r')$',
    re.IGNORECASE | re.MULTILINE,
)

# Excessive whitespace
_MULTI_NEWLINE_RE = re.compile(r'\n{3,}')
_MULTI_SPACE_RE = re.compile(r'[ \t]{2,}')

# URL-only lines (tracking links, pixel urls)
_URL_LINE_RE = re.compile(r'^\s*https?://\S+\s*$', re.MULTILINE)


def clean_email_body(raw_body, max_length=2000):
    """
    Clean an email body for receipt Document storage.

    Steps:
        1. Remove script/style blocks
        2. Remove HTML comments
        3. Strip all HTML tags
        4. Decode HTML entities
        5. Remove tracking URL lines
        6. Trim footer/signature noise
        7. Normalize whitespace
        8. Truncate to max_length

    Args:
        raw_body: raw email body string (may contain HTML)
        max_length: max chars to return

    Returns:
        str: cleaned text, truncated to max_length
    """
    if not raw_body:
        return ''

    text = raw_body

    # 1. Remove script/style blocks
    text = _SCRIPT_STYLE_RE.sub('', text)

    # 2. Remove HTML comments
    text = _COMMENT_RE.sub('', text)

    # 3. Strip HTML tags (replace block tags with newlines for readability)
    text = re.sub(r'<(?:br|p|div|tr|li|h[1-6])[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = _TAG_RE.sub(' ', text)

    # 4. Decode HTML entities
    text = html.unescape(text)

    # 5. Remove URL-only lines (tracking pixels, unsubscribe links)
    text = _URL_LINE_RE.sub('', text)

    # 6. Trim footer/signature noise (line-by-line, never cross-line)
    text = _FOOTER_LINE_RE.sub('', text)

    # 7. Normalize whitespace
    text = _MULTI_SPACE_RE.sub(' ', text)
    lines = [line.strip() for line in text.split('\n')]
    lines = [line for line in lines if line]  # remove blank lines
    text = '\n'.join(lines)
    text = _MULTI_NEWLINE_RE.sub('\n\n', text)
    text = text.strip()

    # 8. Truncate
    if len(text) > max_length:
        text = text[:max_length]

    return text
