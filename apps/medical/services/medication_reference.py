"""
MEDICATION REFERENCE RESOLUTION (M1) — background-only identity + label retrieval.

Design of record: `docs/WLJ_MEDICATION_INSTRUCTION_TRUTH_INVESTIGATION.md` Part B.

WHY THIS EXISTS
    After correctly retrieving the user's own medication record, the Chief of Staff
    had nowhere to get the PRODUCT's approved instructions, so it improvised them.
    This module fetches that authoritative reference truth deterministically, with
    provenance, and stores it as an impersonal `MedicationProductLabel`.

THE THREE RULES THAT GOVERN EVERY LINE HERE
    1. IDENTITY IS THE SAFETY GATE. "First search result" semantics are forbidden.
       Proven necessary, not assumed: DailyMed's top NAME match for "Ozempic" is an
       SPL titled `OZEMPIC (ORAL SEMAGLUTIDE) TABLET RYBELSUS ...` — an oral tablet,
       a different product and route from the Ozempic injection. Resolution therefore
       runs through RxNorm identity (`rxcui`) and NEVER through a title match.
    2. AMBIGUITY FAILS CLOSED. Every gate must pass. A partial result is recorded as
       ambiguous/unsupported with a reason and NO label attached. Refusing is correct
       behaviour, not a defect.
    3. NEVER ON THE REQUEST PATH. Every function here performs outbound HTTP and is
       called ONLY from a Celery task. The CoS truth surface reads the database.

M1 SCOPE: brand-resolvable products only (RxNorm TTY == 'BN'). Multi-source generics
are recorded `unsupported` — `openfda.generic_name:"IBUPROFEN"` returns 1,185 distinct
SPLs, which cannot be deterministically narrowed from a name. NDC-level resolution for
generics is M2 and is deliberately NOT built here.
"""
import hashlib
import json
import logging
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

RXNAV = "https://rxnav.nlm.nih.gov/REST"
DAILYMED = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
OPENFDA_LABEL = "https://api.fda.gov/drug/label.json"
DAILYMED_HUMAN_URL = "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}"

# M1 supports exactly this RxNorm term type. BN == Brand Name: a single labeler of
# record, so the approved labelling is deterministically identifiable. IN/PIN
# (ingredient) means a multi-source generic — explicitly out of scope.
SUPPORTED_TTY = ("BN",)

_TIMEOUT = 20


class ResolutionOutcome:
    """Result of one resolution attempt. Carries WHY, so a refusal is auditable."""

    def __init__(self, state, note="", payload=None):
        self.state = state              # resolved | ambiguous | unsupported | no_label
        self.note = note
        self.payload = payload or {}

    def __repr__(self):
        return f"<ResolutionOutcome {self.state}: {self.note}>"


def _get_json(url):
    """One bounded GET. Returns None on any failure — a resolver that cannot reach its
    source must fail closed, never fall back to a guess."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WLJ/1.0"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("medication_reference: fetch failed %s (%r)", url, exc)
        return None


# --- gate 1: identity ------------------------------------------------------------
def resolve_identity(name):
    """Free-text medication name -> (rxcui, tty). Identity ONLY; says nothing about
    whether a label exists (proven distinct: 'fish oil' resolves to RXCUI 4419 and has
    no drug label at all)."""
    q = (name or "").strip()
    if not q:
        return ResolutionOutcome("ambiguous", "empty medication name")

    data = _get_json(f"{RXNAV}/rxcui.json?name={urllib.parse.quote(q)}&search=1")
    ids = ((data or {}).get("idGroup") or {}).get("rxnormId") or []
    if not ids:
        return ResolutionOutcome("unsupported", f"no RxNorm concept for {q!r}")
    if len(ids) > 1:
        # More than one concept for one name is exactly the ambiguity we refuse.
        return ResolutionOutcome(
            "ambiguous", f"{q!r} matched {len(ids)} RxNorm concepts")

    rxcui = ids[0]
    prop = _get_json(f"{RXNAV}/rxcui/{rxcui}/property.json?propName=TTY")
    ttys = [c.get("propValue") for c in
            ((prop or {}).get("propConceptGroup") or {}).get("propConcept") or []]
    tty = ttys[0] if ttys else ""
    if tty not in SUPPORTED_TTY:
        return ResolutionOutcome(
            "unsupported",
            f"{q!r} resolves to RxNorm {tty or 'unknown'} (not a brand product); "
            "multi-source generic identity is out of scope for this milestone")
    return ResolutionOutcome("resolved", "", {"rxcui": rxcui, "tty": tty})


# --- gate 2: the label document --------------------------------------------------
def select_label_document(rxcui):
    """RxNorm concept -> exactly ONE DailyMed SPL, or a closed failure.

    Selection is deterministic and auditable: among the SPLs DailyMed indexes FOR THAT
    RXCUI (not for a name), take the highest `spl_version` — the labeler of record
    maintains the actively-revised label, while repackager SPLs sit at low versions.
    If two DISTINCT labelers tie at that version, the choice is not deterministic and
    we fail closed rather than pick one.
    """
    data = _get_json(f"{DAILYMED}/spls.json?rxcui={urllib.parse.quote(str(rxcui))}"
                     f"&pagesize=50")
    rows = (data or {}).get("data") or []
    if not rows:
        return ResolutionOutcome("no_label", f"DailyMed indexes no SPL for rxcui {rxcui}")

    def _ver(r):
        try:
            return int(r.get("spl_version") or 0)
        except (TypeError, ValueError):
            return 0

    top = max(_ver(r) for r in rows)
    winners = [r for r in rows if _ver(r) == top]
    labelers = {(_labeler_of(r) or "").strip().lower() for r in winners}
    if len(labelers) > 1:
        return ResolutionOutcome(
            "ambiguous",
            f"{len(winners)} SPLs from {len(labelers)} labelers tie at version {top}")
    return ResolutionOutcome("resolved", "", {"spl": winners[0]})


def _labeler_of(row):
    """DailyMed puts the labeler in the SPL title's trailing [BRACKETS]."""
    title = row.get("title") or ""
    if "[" in title and "]" in title:
        return title[title.rfind("[") + 1:title.rfind("]")]
    return ""


# --- gate 3: the verbatim content ------------------------------------------------
def fetch_dosage_and_administration(setid):
    """The ONE fact class M1 carries, retrieved for THIS setid and returned VERBATIM.

    WLJ never paraphrases, summarizes or condenses this text (Constitution I.4 — the
    model owns interpretation). Retrieved from the parsed index of the same SPL
    document DailyMed identifies; `content_source` records that distinction so the
    identity authority and the text retrieval are never conflated.
    """
    q = urllib.parse.quote(f'set_id:"{setid}"')
    data = _get_json(f"{OPENFDA_LABEL}?search={q}&limit=1")
    results = (data or {}).get("results") or []
    if not results:
        return ResolutionOutcome("no_label", f"no parsed label content for setid {setid}")
    row = results[0]
    text = (row.get("dosage_and_administration") or [""])[0] or ""
    if not text.strip():
        return ResolutionOutcome("no_label",
                                 f"label {setid} carries no dosage_and_administration")
    return ResolutionOutcome("resolved", "", {
        "text": text,
        "version": str(row.get("version") or ""),
        "effective_time": str(row.get("effective_time") or ""),
        "openfda": row.get("openfda") or {},
    })


# --- the pipeline ----------------------------------------------------------------
def resolve_medication_label(name):
    """Run every gate for one medication name. Returns a `ResolutionOutcome`; only
    `state == 'resolved'` carries a payload safe to persist."""
    ident = resolve_identity(name)
    if ident.state != "resolved":
        return ident

    doc = select_label_document(ident.payload["rxcui"])
    if doc.state != "resolved":
        return ResolutionOutcome(doc.state, doc.note)

    spl = doc.payload["spl"]
    setid = spl.get("setid") or ""
    content = fetch_dosage_and_administration(setid)
    if content.state != "resolved":
        return ResolutionOutcome(content.state, content.note)

    of = content.payload.get("openfda") or {}
    return ResolutionOutcome("resolved", "", {
        "spl_setid": setid,
        "rxcui": ident.payload["rxcui"],
        "rxcui_tty": ident.payload["tty"],
        "brand_name": (of.get("brand_name") or [""])[0],
        "generic_name": (of.get("generic_name") or [""])[0],
        "labeler": _labeler_of(spl),
        "title": spl.get("title") or "",
        "dosage_and_administration": content.payload["text"],
        "spl_version": str(spl.get("spl_version") or content.payload.get("version") or ""),
        "published_date": spl.get("published_date") or "",
        "effective_time": content.payload.get("effective_time") or "",
        "source_url": DAILYMED_HUMAN_URL.format(setid=setid),
    })


def persist(outcome, name):
    """Write a resolved outcome to the canonical impersonal record. Returns the
    `MedicationProductLabel` or None. NEVER writes label text for a non-resolved
    outcome — a refusal must leave no attachable label behind."""
    from django.utils import timezone

    from apps.medical.models import MedicationProductLabel
    if outcome.state != "resolved":
        return None
    p = outcome.payload
    text = p["dosage_and_administration"]
    obj, _ = MedicationProductLabel.objects.update_or_create(
        spl_setid=p["spl_setid"],
        defaults={
            "rxcui": p["rxcui"], "rxcui_tty": p["rxcui_tty"],
            "brand_name": p["brand_name"], "generic_name": p["generic_name"],
            "labeler": p["labeler"], "title": p["title"][:500],
            "dosage_and_administration": text,
            "source": "dailymed", "source_url": p["source_url"],
            "content_source": "openfda_spl_index",
            "spl_version": p["spl_version"], "effective_time": p["effective_time"],
            "published_date": p["published_date"],
            "retrieved_at": timezone.now(),
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "resolution_state": MedicationProductLabel.RESOLUTION_RESOLVED,
            "resolution_note": "",
        })
    return obj


def resolve_and_link_intake(intake):
    """Resolve ONE `health.Intake` and record the outcome on it — including refusals,
    so an unsupported generic is a recorded, auditable state rather than a silent gap.
    Background only."""
    from django.utils import timezone

    outcome = resolve_medication_label(intake.name)
    label = persist(outcome, intake.name)
    intake.reference_identity_confidence = (
        "exact" if outcome.state == "resolved" else outcome.state)
    intake.reference_resolved_at = timezone.now()
    if label is not None:
        intake.reference_rxcui = label.rxcui
        intake.reference_spl_setid = label.spl_setid
    else:
        intake.reference_rxcui = ""
        intake.reference_spl_setid = ""
    intake.save(update_fields=["reference_rxcui", "reference_spl_setid",
                               "reference_identity_confidence",
                               "reference_resolved_at"])
    logger.info("medication_reference: %r -> %s (%s)",
                intake.name, outcome.state, outcome.note or "ok")
    return outcome
