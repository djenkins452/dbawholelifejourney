"""Canonical mention reconciliation — the ONE writer of PersonMention truth.

A consumer (Journal, Tasks, …) hands us the source object + its saved rich-text HTML.
We extract the canonical Person IDs the editor's mention tokens carry and reconcile the
source object's PersonMention rows deterministically: create missing, keep valid, remove
stale, never duplicate. Ownership is enforced here (a token can only ever link a Person
the user owns). A resolved mention also grants People membership (a reference promotes a
Person into the everyday People experience).

HTML is the interaction artifact; PersonMention rows are the truth — never the reverse,
and never two writers.
"""
import re

from django.contrib.contenttypes.models import ContentType

from ..models import Person, PersonMembership, PersonMention
from .membership import grant_membership
from . import resolution

# The sanitized mention markup: <span data-mention data-person-id="123">Heather</span>.
# The `@?` tolerates the legacy "@Heather" form so entries stored before the `@` was
# retired from the rendered journal still parse to the clean surface text.
_MENTION_RE = re.compile(
    r'<span[^>]*data-person-id="(\d+)"[^>]*>@?([^<]*)</span>', re.IGNORECASE
)


def extract_mentions_from_html(html):
    """[(person_id, surface_text)] in document order, de-duplicated by id (first wins)."""
    out, seen = [], set()
    for m in _MENTION_RE.finditer(html or ""):
        pid = int(m.group(1))
        if pid not in seen:
            seen.add(pid)
            out.append((pid, (m.group(2) or "").strip()[:120]))
    return out


def reconcile_object_mentions(
    source_obj, html, user, *, source_type=PersonMention.Source.EXPLICIT_AT_MENTION,
    source_overrides=None,
):
    """Reconcile PersonMention rows for ``source_obj`` from its saved ``html``.

    Deterministic + idempotent: re-saving unchanged HTML changes nothing. Returns an
    auditable summary. Never raises on a bad token — an unknown/foreign id is simply
    dropped (ownership boundary).

    ``source_overrides`` ({person_id: source_type}) records faithful provenance for
    passively-recognized names (e.g. ``exact_name``) so a prose match is never audited as
    an explicit ``@mention``; ids absent from it keep the default ``source_type``."""
    overrides = source_overrides or {}
    ct = ContentType.objects.get_for_model(source_obj.__class__)
    oid = source_obj.pk

    wanted = extract_mentions_from_html(html)
    wanted_ids = [pid for pid, _ in wanted]
    surface_by_id = dict(wanted)

    # Ownership boundary — only Persons the user owns may ever be linked.
    valid_ids = set(
        Person.objects.filter(user=user, pk__in=wanted_ids).values_list("pk", flat=True)
    )

    existing = {
        m.person_id: m
        for m in PersonMention.objects.filter(content_type=ct, object_id=oid)
    }

    created = removed = 0
    for pid, mention in list(existing.items()):        # remove stale (token deleted)
        if pid not in valid_ids:
            mention.delete()
            removed += 1
    for pid in valid_ids:                              # create missing
        if pid not in existing:
            PersonMention.objects.create(
                person_id=pid, content_type=ct, object_id=oid,
                source_type=overrides.get(pid, source_type),
                surface_text=surface_by_id.get(pid, ""),
            )
            created += 1
            person = Person.objects.get(pk=pid)        # a reference promotes to People
            if not PersonMembership.objects.filter(person=person).exists():
                grant_membership(person, PersonMembership.Grant.MENTION, actor="mention")

    return {"linked": len(valid_ids), "created": created, "removed": removed}


def mentions_for(source_obj):
    """Canonical Person mentions on a source object (for read/render surfaces)."""
    ct = ContentType.objects.get_for_model(source_obj.__class__)
    return (PersonMention.objects
            .filter(content_type=ct, object_id=source_obj.pk)
            .select_related("person"))


# ── Passive prose recognition ───────────────────────────────────────────────
# Turn a natural reference ("dinner with Heather") into the SAME mention token an
# explicit @mention produces — but ONLY when the reference deterministically resolves
# to exactly one canonical Person. This is not a second recognition system: it produces
# the identical `<span data-mention data-person-id>` token, reconciled by the same
# `reconcile_object_mentions`, and every identity decision is delegated to the ONE
# canonical resolver (`resolution.resolve`). It NEVER guesses — an ambiguous name (two
# people share it) stays plain text.

# Text inside an existing mention token or a link is protected from re-scanning.
_PROTECT_RE = re.compile(
    r'<span[^>]*\bdata-mention\b[^>]*>.*?</span>|<a\b[^>]*>.*?</a>', re.IGNORECASE | re.DOTALL
)
_TAG_SPLIT_RE = re.compile(r'(<[^>]+>)')


def _person_surfaces(person):
    """The canonical-cased surface strings for a person — first/full/display name plus
    custom recognition phrases. The SAME forms used both to match a name in prose and to
    normalize a chip's capitalization back to how the Person is actually recorded."""
    out = []
    for s in (person.first_name, person.last_name and person.full_name, person.display_name):
        if s and s.strip():
            out.append(s.strip())
    for rp in person.recognition_phrases.all():
        if rp.phrase and rp.phrase.strip():
            out.append(rp.phrase.strip())
    return out


def _member_surfaces(user):
    """Searchable name/phrase surfaces for the user's People MEMBERS (not genealogy).
    Candidate strings only — the resolver makes the identity decision."""
    members = list(Person.objects.filter(user=user, membership__isnull=False))
    member_ids = {p.pk for p in members}
    surfaces = set()
    for p in members:
        for s in _person_surfaces(p):
            surfaces.add(s)
    # Compact/@handle derived forms are for typed lookup, not prose — skip them.
    surfaces = {s for s in surfaces if s and not s.isspace()}
    return member_ids, surfaces


# Match a stored chip so we can rewrite ONLY its visible text, never its attributes:
#   (<span … data-person-id="N" …>)(text)(</span>)
_CHIP_TEXT_RE = re.compile(
    r'(<span[^>]*\bdata-person-id="(\d+)"[^>]*>)([^<]*)(</span>)', re.IGNORECASE
)


def normalize_mention_case(user, html):
    """Normalize each recognized-person chip's visible text to the canonical Person's
    capitalization — WITHOUT changing which words the author used.

    "dinner with heather" / "HEATHER" / "hEaThEr" → "Heather" (the Person's recorded
    first name). It never expands wording ("Heather" is never turned into "Heather
    Jenkins" unless the author wrote the full name), and a chip whose text isn't one of
    the Person's canonical surfaces is left exactly as written. Presentation only — the
    identity (``data-person-id``) is untouched. Applies to BOTH passive and explicit
    chips so they render identically."""
    if not html or "data-mention" not in html.lower():
        return html
    surfaces_by_pid = {}

    def surfaces_for(pid):
        if pid not in surfaces_by_pid:
            p = Person.objects.filter(user=user, pk=pid).first()
            surfaces_by_pid[pid] = _person_surfaces(p) if p else []
        return surfaces_by_pid[pid]

    def _repl(m):
        open_tag, pid_s, text, close = m.group(1), m.group(2), m.group(3), m.group(4)
        norm = text.strip().casefold()
        if not norm:
            return m.group(0)
        for surface in surfaces_for(int(pid_s)):
            if surface.casefold() == norm and surface != text.strip():
                return f"{open_tag}{surface}{close}"   # same words, canonical case
        return m.group(0)

    return _CHIP_TEXT_RE.sub(_repl, html)


def recognize_prose_mentions(user, html):
    """Return (new_html, source_by_pk): wrap deterministically-resolved MEMBER names found
    in the prose into canonical mention tokens. Idempotent — text already inside a mention
    token (or a link) is never re-scanned, so re-saving is stable.

    ``source_by_pk`` maps each newly-recognized person to the resolver's faithful match
    provenance (``exact_name`` / ``confirmed_alias`` / …) for the PersonMention audit — a
    passive match is never recorded as an explicit ``@mention``. A person already carrying
    an explicit token is excluded (their deliberate token is the stronger provenance)."""
    if not html:
        return html, {}
    member_ids, surfaces = _member_surfaces(user)
    if not surfaces:
        return html, {}

    # People the user already @mentioned explicitly keep that (stronger) provenance.
    explicit_ids = {pid for pid, _ in extract_mentions_from_html(html)}

    # Protect existing tokens/links, then build a longest-first, word-boundary matcher.
    protected = []

    def _stash(m):
        protected.append(m.group(0))
        return f"\x00{len(protected) - 1}\x00"

    work = _PROTECT_RE.sub(_stash, html)
    ordered = sorted(surfaces, key=len, reverse=True)
    matcher = re.compile(r"\b(" + "|".join(re.escape(s) for s in ordered) + r")\b", re.IGNORECASE)

    resolved_cache = {}

    def _resolve_member(text):
        key = text.lower()
        if key not in resolved_cache:
            r = resolution.resolve(user, text)
            resolved_cache[key] = (
                (r.person, r.source_type)
                if (r.status == resolution.RESOLVED and r.person
                    and r.person.pk in member_ids)
                else (None, None)
            )
        return resolved_cache[key]

    source_by_pk = {}

    def _scan_text(text):
        out, idx = [], 0
        for m in matcher.finditer(text):
            person, src = _resolve_member(m.group(0))
            if not person:
                continue
            out.append(text[idx:m.start()])
            # The `@` is only an editing gesture; the finished journal shows the author's
            # exact wording (m.group(0)) as a recognized chip, never an injected "@".
            out.append(f'<span data-mention data-person-id="{person.pk}">{m.group(0)}</span>')
            idx = m.end()
            if person.pk not in explicit_ids:
                source_by_pk.setdefault(person.pk, src or resolution.EXACT_NAME)
        out.append(text[idx:])
        return "".join(out)

    # Only rewrite TEXT segments (never a tag). Protected tokens/links are inert
    # placeholders (\x00N\x00, no letters) so the matcher can safely scan around them.
    pieces = _TAG_SPLIT_RE.split(work)
    rebuilt = []
    for piece in pieces:
        if piece.startswith("<") or not piece.strip():
            rebuilt.append(piece)
        else:
            rebuilt.append(_scan_text(piece))
    work = "".join(rebuilt)

    # Restore protected tokens/links.
    work = re.sub(r"\x00(\d+)\x00", lambda m: protected[int(m.group(1))], work)
    return work, source_by_pk
