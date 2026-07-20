"""Journal structured-import adapter — the reference implementation.

docs/WLJ_STRUCTURED_IMPORT_ARCHITECTURE.md — turns an uploaded journal document into many
faithful ``JournalEntry`` rows via the generic Structured Import engine.

DETERMINISTIC DATE TRUTH (the non-negotiable rule). Dates are NEVER taken from the model.
When a source document is present, WLJ deterministically parses the EXPLICIT date HEADERS
from the document's own extracted text — that is the only authority for a journal's date,
time, boundary, and skipped state. The model may recognize "this is a journal to import,"
but it may not tell WLJ what the dates are. If WLJ cannot confidently recognize an explicit
date header, it reports UNCERTAINTY rather than inventing a date. (Root cause of the
2026-07-20 defect: a model-normalized ISO date was trusted verbatim, so a fabricated
"2023-10-10" that appears NOWHERE in the source became an entry. Eliminated here.)

Faithfulness contract:
  • entry_date/entry_time = read from the document's explicit header; never inferred
  • title = a consistent presentation of date (+ time) — WLJ composes it deterministically
  • body  = the ORIGINAL text between headers — NEVER rewritten/summarized
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

# 3-letter month prefix → month number (the header regex captures the 3-letter prefix; a
# trailing "[a-z]*" absorbs "tember"/"t"/"ust" etc., so "Sept"/"September"/"Aug"/"August" all map).
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
           "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

# An EXPLICIT journal date header at the start of a line. Tolerant of the real quirks seen in
# exported documents: an optional list number ("1."), an optional weekday, "Sept"/abbreviations,
# 2- or 4-digit years, and a time SMUSHED onto the year ("202210:00am"). The `rest` of the line
# is captured and separately validated to be header-like (a time / "(skipped)" / empty) — so a
# prose sentence that merely begins with a date is NOT mistaken for a header.
_HEADER_RE = re.compile(
    r'''^[ \t]*(?:\d{1,3}[.)]\s*)?
        (?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+)?
        (?P<month>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+
        (?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s*
        (?P<year>\d{4}|\d{2})
        (?P<rest>[^\n]*)$''',
    re.IGNORECASE | re.MULTILINE | re.VERBOSE)

_TIME_TOKEN_RE = re.compile(r'(\d{1,2}:\d{2}\s*[ap]\.?m\.?|\d{1,2}\s*[ap]\.?m\.?|\d{1,2}:\d{2})',
                            re.IGNORECASE)
_SKIP_RE = re.compile(r'\(?\s*skip\w*\)?', re.IGNORECASE)

_DATE_FALLBACK_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%B %d, %y", "%b %d, %y",
                          "%m/%d/%Y", "%m/%d/%y")
_TIME_FORMATS = ("%I:%M %p", "%I:%M%p", "%H:%M", "%I %p", "%I%p")


def _year(raw):
    """4-digit as-is; a 2-digit journal year is 2000+yy (imports are recent). Never inferred
    from context — only from the digits the header actually shows."""
    y = int(raw)
    return y if y >= 100 else 2000 + y


def _time_from_text(s):
    """Parse the first clock time appearing in ``s`` → a ``time``, or None."""
    if not s:
        return None
    m = _TIME_TOKEN_RE.search(s)
    return _parse_time(m.group(1)) if m else None


def _header_rest_is_clean(rest):
    """A real header line carries only the date plus (optionally) a time and/or a skipped
    marker — nothing else. If prose remains after removing those, the line is a body sentence
    that merely starts with a date, NOT a header. This keeps 'April 7, 2022 was a good day'
    from being read as a boundary."""
    r = (rest or "").strip()
    r = _TIME_TOKEN_RE.sub("", r)
    r = _SKIP_RE.sub("", r)
    r = re.sub(r'[\s\-–—:.,()]+', "", r)
    return len(r) == 0


def parse_journal_document(text):
    """DETERMINISTICALLY segment a journal document's extracted text into dated entries using
    ONLY its explicit date headers. Returns (entries, had_headers) where each entry is
    {entry_date, entry_time, body, skipped} with dates read straight from the source. A header
    whose date is not a real calendar date is dropped as uncertain (never guessed)."""
    text = text or ""
    headers = []
    for m in _HEADER_RE.finditer(text):
        if not _header_rest_is_clean(m.group("rest")):
            continue  # a prose line that happens to start with a date — not a boundary
        mon = _MONTHS.get(m.group("month").lower()[:3])
        try:
            d = _dt.date(_year(m.group("year")), mon, int(m.group("day")))
        except (ValueError, TypeError):
            continue  # not a real date (e.g. "Feb 30") → uncertain, never invented
        headers.append({
            "date": d,
            "time": _time_from_text(m.group("rest")),
            "skipped": bool(_SKIP_RE.search(m.group("rest") or "")),
            "start": m.start(), "end": m.end(),
        })

    entries = []
    for i, h in enumerate(headers):
        body_start = h["end"]
        body_end = headers[i + 1]["start"] if i + 1 < len(headers) else len(text)
        body = text[body_start:body_end].strip()
        # If the body opens with a stray time-only line (time not smushed onto the header),
        # absorb it into the header's time and drop it from the body.
        if h["time"] is None:
            first_line = body.split("\n", 1)[0].strip()
            if first_line and _TIME_TOKEN_RE.fullmatch(first_line.replace(" ", " ").strip()):
                h["time"] = _parse_time(first_line)
                body = body.split("\n", 1)[1].strip() if "\n" in body else ""
        entries.append({"entry_date": h["date"], "entry_time": h["time"],
                        "skipped": h["skipped"], "body": body})
    return entries, bool(headers)


def _parse_date(raw):
    """Model-fallback ONLY (no source document): parse a model-proposed date string. ISO first,
    a few human formats as fallback. Returns a ``date`` or None. Never used when a source
    document is present — then dates come solely from parse_journal_document."""
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
    """Parse a clock time ('10:00 AM', '7:00am', '13:00', '9:38pm'). Returns a ``time`` or None."""
    if raw in (None, ""):
        return None
    s = re.sub(r"\s+", " ", str(raw).strip().upper()).replace(".", "")
    for fmt in _TIME_FORMATS:
        try:
            return _dt.datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def _time_from_title(title):
    """Extract a clock time embedded in a title ('...2023 9:00pm', '...– 7:50 PM'), or None —
    so a legacy entry whose time lives in the TITLE (entry_time=None) still dedups against a
    new entry whose time is in the field. Normalizes AM/PM casing/spacing via _parse_time."""
    return _time_from_text(title)


def _norm_body(text):
    """Normalize body text for duplicate comparison: collapse whitespace, lowercase, drop
    punctuation/Unicode variants — so two imports that extracted the same entry with minor
    whitespace/formatting differences compare equal. Prefix-bounded (tolerates trailing
    extraction drift)."""
    s = re.sub(r"\s+", " ", (text or "")).strip().lower()
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    return s[:400]


def _compose_title(d, t):
    """Deterministic, consistent title: 'Saturday, September 10, 2022 – 10:00 AM'."""
    title = d.strftime("%A, %B ") + str(d.day) + d.strftime(", %Y")
    if t is not None:
        title += " – " + t.strftime("%I:%M %p").lstrip("0")
    return title


def _plain_to_html(text):
    """Escape and paragraph-preserve the ORIGINAL body — formatting preservation, never a rewrite."""
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

    def validate(self, raw_records, source_text=None):
        """When a source document is present, dates come ONLY from its explicit headers
        (deterministic truth). Otherwise (typed-inline / no extractable text) fall back to the
        model-proposed records — the single path where WLJ has nothing to ground against."""
        if source_text and source_text.strip():
            return self._validate_from_source(source_text)
        return self._validate_from_model(raw_records)

    # ── Deterministic path: parse the document's own headers (never trust model dates) ──
    def _validate_from_source(self, source_text):
        entries, had_headers = parse_journal_document(source_text)
        valid, skipped = [], []
        if not had_headers:
            # We were handed a document but could not recognize a single explicit date
            # header — report UNCERTAINTY; never invent dates or a boundary.
            skipped.append({"label": "Journal document", "reason": "uncertain_boundaries"})
            return valid, skipped
        for e in entries:
            d, t = e["entry_date"], e["entry_time"]
            label = _compose_title(d, t)
            if e["skipped"]:
                skipped.append({"label": _compose_title(d, None),
                                "reason": "marked_skipped", "date_iso": d.isoformat()})
                continue
            body_html = _plain_to_html(e["body"])
            if not body_html:
                skipped.append({"label": label, "reason": "no_content",
                                "date_iso": d.isoformat()})
                continue
            valid.append(self._record(d, t, body_html, e["body"]))
        return valid, skipped

    # ── Fallback path: no source document to ground against (typed inline / image w/o text) ──
    def _validate_from_model(self, raw_records):
        valid, skipped = [], []
        for rec in raw_records or []:
            if not isinstance(rec, dict):
                continue
            d = _parse_date(rec.get("entry_date"))
            if d is None:
                skipped.append({"label": str(rec.get("entry_date") or "Undated entry"),
                                "reason": "invalid_date"})
                continue
            t = _parse_time(rec.get("entry_time"))
            label = _compose_title(d, t)
            if rec.get("skipped") or rec.get("skip") or rec.get("is_skipped"):
                skipped.append({"label": _compose_title(d, None),
                                "reason": "marked_skipped", "date_iso": d.isoformat()})
                continue
            body_html = _plain_to_html(rec.get("body"))
            if not body_html:
                skipped.append({"label": label, "reason": "no_content",
                                "date_iso": d.isoformat()})
                continue
            valid.append(self._record(d, t, body_html, rec.get("body") or ""))
        return valid, skipped

    @staticmethod
    def _record(d, t, body_html, body_plain=""):
        label = _compose_title(d, t)
        return {"label": label, "title": label, "entry_date": d, "entry_time": t,
                "date_iso": d.isoformat(), "has_time": t is not None,
                "body_html": body_html, "body_plain": body_plain}

    def dedupe_exists(self, user, record):
        """A record duplicates an existing entry when it is the SAME journal entry regardless
        of TIMESTAMP FORMATTING or which import created it. Two entries on the same date at the
        same clock time are the same entry — even if one import stored the time in `entry_time`
        ('21:00') and an older one embedded it in the TITLE ('9:00pm') with entry_time=None, and
        even if titles differ ('– 9:00 PM' vs '9:00pm'). Time is resolved from the field OR the
        title and normalized; timeless entries fall back to a normalized-body match. (Root cause
        of the 2026-07-20 dupes: dedup keyed on the formatted title + entry_time, so a legacy
        'manual' entry with the time in its title was never matched.)"""
        from apps.journal.models import JournalEntry
        d = record["entry_date"]
        rec_t = record["entry_time"]
        rec_body = _norm_body(record.get("body_plain"))
        for e in JournalEntry.objects.filter(
                user=user, status="active", entry_date=d
        ).only("id", "entry_time", "title", "body_plain"):
            ex_t = e.entry_time or _time_from_title(e.title)
            if rec_t is not None and ex_t is not None:
                if rec_t == ex_t:
                    return True          # same date + same clock time = same entry
                continue                 # both timed but different times → distinct
            # No time to compare on at least one side → identity is the normalized body.
            if rec_body and rec_body == _norm_body(e.body_plain):
                return True
        return False

    def create_one(self, user, record):
        from apps.core.models import UserOwnedModel
        from apps.journal.models import JournalEntry
        return JournalEntry.objects.create(
            user=user,
            title=record["title"],
            body=record["body_html"],
            entry_date=record["entry_date"],
            entry_time=record["entry_time"],
            created_via=UserOwnedModel.CREATED_VIA_IMPORT,
        )


def find_journal_duplicates(user):
    """One-time REPAIR helper (read-only): identify existing duplicate journal entries using the
    SAME normalized identity as import dedup — same date + same resolved clock time (from the
    field OR the title), or same date + same normalized body. Robust to timestamp formatting and
    which import created each. Returns duplicate GROUPS, each RECOMMENDING which record to retain
    (never deletes — the caller decides):

        [{ "identity", "entry_date", "recommend_keep_id", "reason",
           "entries": [{id, title, entry_time, created_via, word_count, created_at}] }]
    """
    from collections import defaultdict

    from apps.journal.models import JournalEntry
    groups = defaultdict(list)
    for e in JournalEntry.objects.filter(user=user, status="active").only(
            "id", "entry_date", "entry_time", "title", "body_plain", "word_count",
            "created_via", "created_at"):
        t = e.entry_time or _time_from_title(e.title)
        key = (("t", str(e.entry_date), t.strftime("%H:%M")) if t is not None
               else ("b", str(e.entry_date), _norm_body(e.body_plain)))
        groups[key].append(e)

    out = []
    for key, entries in groups.items():
        if len(entries) < 2 or not key[2]:  # need ≥2, and a real body/time (not empty)
            continue
        # Keeper: prefer a real entry_time (structured), then the fullest body, then newest.
        keep = sorted(entries, key=lambda e: (e.entry_time is not None, e.word_count, e.id),
                      reverse=True)[0]
        out.append({
            "identity": ("date+time" if key[0] == "t" else "date+body"),
            "entry_date": key[1],
            "recommend_keep_id": keep.id,
            "reason": ("has a structured entry_time and the fullest body"
                       if keep.entry_time is not None else "the fullest body"),
            "entries": [{
                "id": e.id, "title": e.title, "entry_time": str(e.entry_time),
                "created_via": e.created_via, "word_count": e.word_count,
                "created_at": e.created_at.isoformat(),
            } for e in sorted(entries, key=lambda e: e.id)],
        })
    return sorted(out, key=lambda g: g["entry_date"])


register_import_adapter(JournalImportAdapter())
register_import_renderer(
    "journal_import",
    lead="I read your journal {source}.",
    noun="entries",
    kind="record",
)
