"""
WLJ Rich Text — the single platform abstraction for narrative writing fields.

One editor, one storage strategy. Free-form fields across WLJ (journal bodies,
reflections, notes, …) store **sanitized HTML** as the canonical source of
truth, produced by the shared TipTap-based `WLJRichTextWidget`
(`apps/core/widgets.py`). From that HTML we derive a **plain-text shadow** that
keeps everything that predates rich text working unchanged: full-text search,
preview snippets, word counts, reports, and exports all read the shadow.

Design rules:
  * The HTML field is canonical; the plain-text shadow is ALWAYS derived and is
    never edited directly.
  * HTML is sanitized server-side on every save with an allow-list (nh3). We
    NEVER trust client HTML — the same rules apply whether the content came from
    the editor, an API, or a data migration.
  * The allow-list matches exactly what the WLJ editor can emit. Alignment is a
    `data-text-align` attribute (never inline `style`, which nh3 cannot filter
    at the CSS-property level).
  * Models opt in via `RichTextMixin` + a `RICH_TEXT_FIELDS` map. There is no
    per-module editor or storage logic — this module owns it.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import nh3
from django.db import models

# --------------------------------------------------------------------------- #
# Sanitization allow-list — MUST match what static/js/wlj-rich-text.js emits.  #
# --------------------------------------------------------------------------- #

RICH_TEXT_TAGS = {
    # block / structure
    "p", "br", "hr", "blockquote", "div", "span",
    # headings (H1–H3 only, per the editor)
    "h1", "h2", "h3",
    # inline marks
    "strong", "b", "em", "i", "u", "s", "strike", "code",
    # lists (incl. task lists)
    "ul", "ol", "li", "label", "input",
    # links & images
    "a", "img",
    # simple tables
    "table", "thead", "tbody", "tr", "td", "th",
}

RICH_TEXT_ATTRIBUTES = {
    "a": {"href", "target", "title"},
    "img": {"src", "alt", "title", "width"},
    "input": {"type", "checked", "disabled"},
    # task-list markers emitted by TipTap TaskList/TaskItem
    "ul": {"data-type"},
    "li": {"data-type", "data-checked"},
    # alignment is a safe data attribute, never inline style
    "p": {"data-text-align"},
    "h1": {"data-text-align"},
    "h2": {"data-text-align"},
    "h3": {"data-text-align"},
    # simple-table cell spans
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
    # Canonical person mention token: <span data-mention data-person-id="123">@Name</span>.
    # Narrow by design — only these two data-attributes. `data-person-id` is validated as
    # an integer AND checked for user ownership server-side during mention reconciliation
    # (apps/people/services/mentions.py); the sanitizer only guarantees the shape survives.
    # `class` is deliberately NOT allowed — the chip is styled via the [data-mention]
    # attribute selector, so no arbitrary class can ride in.
    "span": {"data-mention", "data-person-id"},
}

RICH_TEXT_URL_SCHEMES = {"http", "https", "mailto"}

# Links always get safe rel; nh3 manages the rel attribute when this is set.
_LINK_REL = "noopener noreferrer nofollow"


def sanitize_rich_html(html: str) -> str:
    """Return an XSS-safe HTML string containing only allow-listed markup.

    Idempotent and safe to run on any input (editor output, API payloads, or
    migration data). Returns "" for falsy input.
    """
    if not html:
        return ""
    return nh3.clean(
        html,
        tags=RICH_TEXT_TAGS,
        attributes=RICH_TEXT_ATTRIBUTES,
        url_schemes=RICH_TEXT_URL_SCHEMES,
        link_rel=_LINK_REL,
        strip_comments=True,
    )


# --------------------------------------------------------------------------- #
# HTML -> plain text (the searchable / countable / exportable shadow)          #
# --------------------------------------------------------------------------- #

# Block-level tags whose boundaries should become whitespace so words on
# adjacent blocks don't fuse (e.g. "<p>a</p><p>b</p>" -> "a b", not "ab").
_BLOCK_TAGS = {
    "p", "br", "hr", "div", "li", "blockquote",
    "h1", "h2", "h3", "tr", "table", "ul", "ol",
}


class _PlainTextExtractor(HTMLParser):
    """Collect visible text, inserting newlines at block boundaries."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "hr"):
            self._parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in ("br", "hr"):
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data):
        self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def rich_text_to_plaintext(html: str) -> str:
    """Derive a clean, human-readable plain-text shadow from stored HTML.

    Preserves block boundaries as whitespace and collapses runs of blank
    space so word counts and previews behave like the old plain-text fields.
    """
    if not html:
        return ""
    parser = _PlainTextExtractor()
    parser.feed(html)
    text = parser.get_text()
    # Collapse spaces/tabs but keep meaningful line breaks; trim blank lines.
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def looks_like_html(value: str) -> bool:
    """Heuristic: does this value already contain HTML tags?

    Used by data migrations to decide whether legacy plain text needs wrapping.
    """
    if not value:
        return False
    return bool(re.search(r"<[a-zA-Z][^>]*>", value))


def plaintext_to_html(value: str) -> str:
    """Convert a plain-text value into safe editor-compatible HTML.

    ALWAYS treats the input as literal plain text: every character is HTML-escaped
    (so a user who literally typed ``<b>`` keeps that text, never gets a bold tag),
    each blank-line-separated block becomes a ``<p>``, and single newlines become
    ``<br>``. This matches how legacy fields were shown (Django's ``|linebreaks``
    escapes), so migrating them is lossless. For values that are already HTML, call
    ``sanitize_rich_html`` instead.
    """
    if not value:
        return ""
    from django.utils.html import escape

    blocks = re.split(r"\n\s*\n", value.replace("\r\n", "\n").replace("\r", "\n"))
    html_blocks = []
    for block in blocks:
        block = block.strip("\n")
        if not block.strip():
            continue
        html_blocks.append("<p>" + escape(block).replace("\n", "<br>") + "</p>")
    return "".join(html_blocks) if html_blocks else ""


# --------------------------------------------------------------------------- #
# Reusable model mixin                                                          #
# --------------------------------------------------------------------------- #


def backfill_rich_text(model, field_pairs, batch_size=500):
    """Convert legacy plain-text field(s) to HTML + derive shadows, in a migration.

    ``field_pairs`` is an iterable of ``(html_field, plain_field)``. Legacy values
    are treated as plain text (escaped + wrapped — lossless) and each shadow is
    derived from the resulting HTML. Uses ``bulk_update`` (no signals/side effects),
    safe to call from a ``RunPython`` with a historical model.
    """
    field_pairs = list(field_pairs)
    only_fields = ["id"]
    update_fields = []
    for html_field, plain_field in field_pairs:
        only_fields += [html_field, plain_field]
        update_fields += [html_field, plain_field]

    batch = []
    for obj in model.objects.all().only(*only_fields).iterator():
        for html_field, plain_field in field_pairs:
            html = plaintext_to_html(getattr(obj, html_field, "") or "")
            setattr(obj, html_field, html)
            setattr(obj, plain_field, rich_text_to_plaintext(html))
        batch.append(obj)
        if len(batch) >= batch_size:
            model.objects.bulk_update(batch, update_fields)
            batch = []
    if batch:
        model.objects.bulk_update(batch, update_fields)


def restore_plain_from_shadow(model, field_pairs, batch_size=500):
    """Reverse of ``backfill_rich_text``: set each HTML field back to its shadow."""
    field_pairs = list(field_pairs)
    only_fields = ["id"]
    update_fields = []
    for html_field, plain_field in field_pairs:
        only_fields += [html_field, plain_field]
        update_fields.append(html_field)
    batch = []
    for obj in model.objects.all().only(*only_fields).iterator():
        for html_field, plain_field in field_pairs:
            setattr(obj, html_field, getattr(obj, plain_field, "") or "")
        batch.append(obj)
        if len(batch) >= batch_size:
            model.objects.bulk_update(batch, update_fields)
            batch = []
    if batch:
        model.objects.bulk_update(batch, update_fields)


class RichTextMixin(models.Model):
    """Give a model one or more sanitized-HTML fields with plain-text shadows.

    Declare the field pairs on the model::

        class JournalEntry(RichTextMixin, UserOwnedModel):
            body = models.TextField()
            body_plain = models.TextField(blank=True, default="", editable=False)

            RICH_TEXT_FIELDS = {"body": "body_plain"}

    On every save each HTML field is sanitized in place and its shadow field is
    regenerated from the sanitized HTML. Map an HTML field to ``None`` if it has
    no shadow (rare). All logic lives here — models never duplicate it.
    """

    #: {html_field_name: plain_shadow_field_name_or_None}
    RICH_TEXT_FIELDS: dict[str, str | None] = {}

    class Meta:
        abstract = True

    def sync_rich_text_fields(self) -> None:
        """Sanitize each rich field and (re)derive its plain-text shadow."""
        for html_field, plain_field in self.RICH_TEXT_FIELDS.items():
            raw = getattr(self, html_field, "") or ""
            clean = sanitize_rich_html(raw)
            setattr(self, html_field, clean)
            if plain_field:
                setattr(self, plain_field, rich_text_to_plaintext(clean))

    def rich_text_plain(self, html_field: str) -> str:
        """Return the plain-text shadow for a rich field (deriving if absent)."""
        plain_field = self.RICH_TEXT_FIELDS.get(html_field)
        if plain_field:
            value = getattr(self, plain_field, "") or ""
            if value:
                return value
        return rich_text_to_plaintext(getattr(self, html_field, "") or "")

    def save(self, *args, **kwargs):
        self.sync_rich_text_fields()
        super().save(*args, **kwargs)
