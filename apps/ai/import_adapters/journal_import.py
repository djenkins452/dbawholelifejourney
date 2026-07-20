"""Journal structured-import adapter — the reference implementation.

docs/WLJ_STRUCTURED_IMPORT_ARCHITECTURE.md — turns a model-recognized batch of journal
records (e.g. a historical journal document) into many faithful ``JournalEntry`` rows via
the generic Structured Import engine. THIN by design: it only maps/validates one record,
creates one entry through the model's safe write, and answers a dedup question. The engine
owns idempotency, preview, confirmation, provenance, and audit.

Faithfulness contract (the whole point of this domain):
  • entry_date = the original date; entry_time = the original time when present, else null
  • title     = a consistent presentation of date (+ time) — WLJ composes it deterministically
  • body      = the ORIGINAL body, escaped and paragraph-preserved — NEVER rewritten/summarized
  • created_via = 'import'; explicitly-skipped days are surfaced, never created
"""
import datetime as _dt
import html as _html
import logging
import re

from django.utils.dateparse import parse_date

from apps.ai.import_confirmation import register_import_renderer
from apps.ai.structured_import import StructuredImportAdapter, register_import_adapter

logger = logging.getLogger(__name__)

_DATE_FALLBACK_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%B %d, %y", "%b %d, %y",
                          "%m/%d/%Y", "%m/%d/%y")
_TIME_FORMATS = ("%I:%M %p", "%I:%M%p", "%H:%M", "%I %p", "%I%p")


def _parse_date(raw):
    """ISO first (the model is asked to normalize to YYYY-MM-DD); a few human formats as a
    defensive fallback. Returns a ``date`` or None. WLJ validates; it never guesses a year."""
    if not raw:
        return None
    s = str(raw).strip()
    d = parse_date(s)
    if d is not None:
        return d
    for fmt in _DATE_FALLBACK_FORMATS:
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_time(raw):
    """Parse a clock time ('10:00 AM', '7:00am', '13:00', '9:38pm'). Returns a ``time`` or
    None (no time recorded — a legitimate state, never an error)."""
    if raw in (None, ""):
        return None
    s = re.sub(r"\s+", " ", str(raw).strip().upper())  # normalize input; %p is case-insensitive
    for fmt in _TIME_FORMATS:
        try:
            return _dt.datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def _compose_title(d, t):
    """Deterministic, consistent title from date (+ optional time):
    'Saturday, September 10, 2022 – 10:00 AM' / 'Tuesday, August 30, 2022'."""
    title = d.strftime("%A, %B ") + str(d.day) + d.strftime(", %Y")  # no zero-padded day
    if t is not None:
        title += " – " + t.strftime("%I:%M %p").lstrip("0")
    return title


def _plain_to_html(text):
    """Escape and paragraph-preserve the ORIGINAL body — formatting preservation, never a
    rewrite. Blank-line-separated blocks → <p>; single newlines within a block → <br>.
    RichTextMixin re-sanitizes on save; this only structures the user's exact words."""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return ""
    blocks = re.split(r"\n\s*\n", raw)
    paras = []
    for block in blocks:
        esc = _html.escape(block.strip())
        if esc:
            paras.append("<p>" + esc.replace("\n", "<br>") + "</p>")
    return "".join(paras)


class JournalImportAdapter(StructuredImportAdapter):
    domain = "journal"
    intent = "import_journal_entries"
    renderer = "journal_import"
    records_key = "entries"

    def validate(self, raw_records):
        valid, skipped = [], []
        for rec in raw_records:
            if not isinstance(rec, dict):
                continue
            d = _parse_date(rec.get("entry_date"))
            if d is None:
                # Can't place it in time → surfaced, never silently dropped.
                skipped.append({"label": str(rec.get("entry_date") or "Undated entry"),
                                "reason": "invalid_date"})
                continue
            t = _parse_time(rec.get("entry_time"))
            label = _compose_title(d, t)
            # A day the source explicitly marks skipped is surfaced, never created.
            if rec.get("skipped") or rec.get("skip") or rec.get("is_skipped"):
                skipped.append({"label": _compose_title(d, None),
                                "reason": "marked_skipped", "date_iso": d.isoformat()})
                continue
            body_html = _plain_to_html(rec.get("body"))
            if not body_html:
                skipped.append({"label": label, "reason": "no_content",
                                "date_iso": d.isoformat()})
                continue
            valid.append({
                "label": label,
                "title": label,
                "entry_date": d,
                "entry_time": t,
                "date_iso": d.isoformat(),
                "has_time": t is not None,
                "body_html": body_html,
            })
        return valid, skipped

    def dedupe_exists(self, user, record):
        """A record already imported if this user has an active entry with the SAME date,
        time, and title. Occurrence-scoped: two real entries on the same day at different
        times are distinct; re-running the same document is a duplicate."""
        from apps.journal.models import JournalEntry
        return JournalEntry.objects.filter(
            user=user, status="active",
            entry_date=record["entry_date"],
            entry_time=record["entry_time"],
            title=record["title"],
        ).exists()

    def create_one(self, user, record):
        from apps.core.models import UserOwnedModel
        from apps.journal.models import JournalEntry
        return JournalEntry.objects.create(
            user=user,
            title=record["title"],
            body=record["body_html"],          # RichTextMixin sanitizes + derives body_plain
            entry_date=record["entry_date"],
            entry_time=record["entry_time"],
            created_via=UserOwnedModel.CREATED_VIA_IMPORT,
        )


register_import_adapter(JournalImportAdapter())
register_import_renderer(
    "journal_import",
    lead="I read your journal {source}.",
    noun="entries",
    kind="record",
)
