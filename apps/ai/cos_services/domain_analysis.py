# ==============================================================================
# File: apps/ai/cos_services/domain_analysis.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: DomainAnalysisService — the composed ANALYSIS truth surface that
#   makes "investigate before concluding" a GUARANTEE, not a request.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-16
# ==============================================================================
"""
DomainAnalysisService (Model Interface — the investigate-before-concluding guarantee)
=====================================================================================

BEHAVIORAL CONTRACT (permanent, not tied to today's runtime):
    When the user's intent is ANALYSIS of a subject, the Chief of Staff must
    investigate the deterministic truth WLJ holds BEFORE it may conclude that
    evidence is insufficient. The user must NEVER receive "insufficient data"
    while additional relevant deterministic truth still exists inside WLJ.

A prompt directive can only REQUEST that behavior from a non-deterministic model;
it cannot GUARANTEE it (three prompt strengthenings did not hold). So the
investigation is performed DETERMINISTICALLY here:

    get_domain_analysis(user, domain, subject)

composes EVERY relevant retrieval for a subject into ONE evidence bundle —
  * trends across trailing windows (reuses get_domain_history),
  * all-time span + total (reuses get_domain_history, custom range),
  * record-level detail (reuses get_domain_entity, when the subject has entities),
  * a deterministic completeness verdict (`holds_data` / `evidence`).

Because one call returns the WHOLE evidence set, the model can neither under-gather
(there is nothing left to gather) nor truthfully claim "insufficient" while WLJ still
holds the truth (the bundle carries the data and WLJ's own `holds_data` verdict).
WLJ investigates deterministically; the model still REASONS over the bundle.

Design rules honored (identical spine to domain_history / domain_entity):
* REUSE ONLY — no new retrieval logic; composes the canonical Truth Resolution Layer
  surfaces (`history()` / `describe()`) a domain already exposes.
* CATALOG-DRIVEN — every domain that declares `analysis_subjects` participates
  automatically; no per-domain plumbing here.
* NO FABRICATION — unknown domain → `unsupported_domain`; unknown subject →
  `unsupported`; genuinely no data → `empty` (the ONLY honest "insufficient").
* JSON-safe + observable; wrappable by the Model Interface truth envelope unchanged.
"""

import logging
import time
from datetime import date

from apps.ai.cos_services.domain_entity import get_domain_entity
from apps.ai.cos_services.domain_history import get_domain_history
from apps.core.truth.domain import WHOLE_DOMAIN_SUBJECT

logger = logging.getLogger(__name__)

DOMAIN_ANALYSIS_SCHEMA_VERSION = "1.0"

# Trailing / current windows that capture RECENT activity (never a prior-calendar
# period that would falsely read empty for current-month activity). Composed together
# they answer "how am I trending" without the model having to pick a window.
DEFAULT_WINDOWS = ("last_7_days", "this_month", "this_quarter", "this_year")

# Deterministic completeness thresholds (data points / records over all time).
_RICH_THRESHOLD = 3      # >= 3 → enough to read a trend
_EARLIEST = "2000-01-01"  # all-time span lower bound for the wide custom range

# WHOLE-DOMAIN OVERVIEW ("overall") ------------------------------------------------------
# Synonyms the model may pass for a whole-domain roll-up. The canonical token "overall" is
# the one advertised in the capability index (apps.core.truth.domain.WHOLE_DOMAIN_SUBJECT);
# these extra forms make the surface robust to natural phrasing ("overall health",
# "summarize my finances") without a second capability. Matched case-insensitively; any
# subject that simply STARTS WITH "overall" also routes here.
_OVERVIEW_ALIASES = frozenset({
    "overall", "overview", "summary", "everything", "all", "general", "whole", "holistic",
})
# The overview honors the WINDOW THE USER ASKED FOR — every subject is composed against the
# SAME resolved window and NOTHING outside it (so "overall health for the last week" can
# never be influenced by this-month data). When no window is stated the roll-up defaults to
# a single recent horizon: "how am I doing lately" == the last 7 days.
_OVERVIEW_DEFAULT_PERIOD = "last_7_days"


def analysis_capability_index():
    """{domain: (subjects...)} for every registered domain that declares at least one
    analyzable subject. Metric NAMES only — the capability index the model reads to
    know what it can analyze, never the data itself."""
    try:
        from apps.core.truth.catalog import truth_catalog
        cat = truth_catalog()
    except Exception:
        logger.warning("domain_analysis: catalog read failed", exc_info=True)
        return {}
    out = {}
    for domain, supports in (cat or {}).items():
        subjects = tuple(supports.get("analysis", ()) if isinstance(supports, dict) else ())
        if subjects:
            out[domain] = subjects
    return out


def analysis_capable_domains():
    return sorted(analysis_capability_index().keys())


def _today_iso(user):
    try:
        from apps.core.utils import get_user_today
        t = get_user_today(user)
        if t:
            return t.isoformat()
    except Exception:
        pass
    return date.today().isoformat()


def _compact_history(h):
    """A window summary from a get_domain_history envelope — present/absent + aggregates
    + the data span, dropping nothing the model needs to read the trend."""
    status = h.get("status")
    if status != "ready":
        return {"present": False, "status": status, "period": h.get("period"),
                "reason": h.get("reason")}
    pts = h.get("points") or []
    return {
        "present": True, "period": h.get("period"), "unit": h.get("unit"),
        "total": h.get("total"), "average": h.get("average"),
        "count": h.get("count"),
        "first_point": (pts[0].get("date") if pts else None),
        "last_point": (pts[-1].get("date") if pts else None),
        "points": pts,
    }


def _compact_entities(e, *, limit=10):
    """Record detail from a get_domain_entity envelope — the recent complete records
    (identity + contents), bounded so the bundle stays composed, not a data dump."""
    if e.get("status") != "ready":
        return {"present": False, "status": e.get("status"), "count": 0}
    ents = e.get("entities") or []
    return {"present": True, "count": e.get("count") or len(ents),
            "records": ents[:limit]}


def _is_overview_subject(subject_norm, domain_norm):
    """True when the subject denotes the WHOLE domain rather than one metric — an empty
    subject, 'overall' (or anything starting with it, e.g. 'overall health'), a
    summary/overview synonym, or the domain name itself."""
    if not subject_norm:
        return True
    if subject_norm in _OVERVIEW_ALIASES or subject_norm.startswith("overall"):
        return True
    if subject_norm in (domain_norm, f"overall {domain_norm}", f"overall_{domain_norm}",
                        f"{domain_norm} overall", f"{domain_norm}_overall"):
        return True
    return False


def _resolve_overview_window(user, period):
    """Resolve the roll-up's window ONCE via the ONE shared temporal authority so EVERY
    subject is composed against the exact SAME (start, end) — never a per-metric or
    per-window range. Returns (Period, requested_unresolved: bool). A stated-but-
    unparseable period never dead-ends the summary: it falls back to the default recent
    window and flags it so the model can say which window it actually answered."""
    from apps.core.truth.periods import resolve_date_expression
    try:
        from apps.core.utils import get_user_today
        today = get_user_today(user) or date.today()
    except Exception:
        today = date.today()
    if period:
        p = resolve_date_expression(period, today)
        if p is not None:
            return p, False
        logger.warning("domain_overview: unresolvable period %r → default %s",
                       period, _OVERVIEW_DEFAULT_PERIOD)
    return resolve_date_expression(_OVERVIEW_DEFAULT_PERIOD, today), bool(period)


def _overview_subject(h):
    """Compact per-subject projection for the roll-up over the ONE requested window —
    present/absent + headline aggregates + the deterministic within-window CHANGE
    (direction / delta / pct: what improved vs got worse). NO raw points — the model
    reasons over the summary, not a data dump. `present:false` is HONEST missing data for
    the window (distinct from a negative reading), which the model must not read as a
    decline."""
    if h.get("status") != "ready":
        # Distinguish genuine no-data-in-window ("empty") from an actual read error.
        return {"present": False, "status": h.get("status")}
    return {"present": True, "unit": h.get("unit"), "total": h.get("total"),
            "average": h.get("average"), "count": h.get("count"),
            # First-class deterministic trend within the window (None with < 2 points) —
            # carries first/last VALUES + direction: the exact truth behind "what improved
            # and what got worse". The window itself is at the envelope root (`window`).
            "change": h.get("change")}


def _domain_overview(user, domain, subjects, t0, uid, period=None):
    """Compose EVERY analyzable subject of `domain` into ONE whole-domain evidence bundle —
    the "overall" roll-up (the whole-domain analogue of a single-subject analysis) — over
    the WINDOW THE USER ASKED FOR.

    Pure COMPOSITION: reuses each subject's existing history surface; adds NO retrieval
    logic. The window is resolved ONCE and every metric is read against that identical
    (start, end) as a custom range, so the roll-up can never mix horizons — a "last week"
    summary is composed only from last-week data. Aliases are deduped by history_metric so
    a metric is composed once. Carries the SAME deterministic `holds_data` verdict as a
    single-subject analysis — so the reasoner can never truthfully say 'insufficient' while
    WLJ still holds truth for any subject in the window.
    """
    window, requested_unresolved = _resolve_overview_window(user, period)
    start_iso, end_iso = window.start.isoformat(), window.end.isoformat()

    seen_metrics = set()
    composed = {}
    present_count = 0
    for name, mapping in subjects.items():
        mapping = mapping or {}
        metric = mapping.get("history_metric") or name
        if metric in seen_metrics:          # dedup aliases (bp/blood_pressure → one metric)
            continue
        seen_metrics.add(metric)
        try:
            # ONE window for every metric — custom range from the single resolved Period.
            entry = _overview_subject(get_domain_history(
                user, domain, metric, period="custom", start=start_iso, end=end_iso))
        except Exception:
            logger.warning("domain_overview: history failed user=%s domain=%s metric=%s "
                           "window=%s..%s", uid, domain, metric, start_iso, end_iso,
                           exc_info=True)
            entry = {"present": False, "status": "error"}
        if entry.get("present"):
            present_count += 1
        entry["metric"] = metric
        composed[name] = entry

    ms = (time.monotonic() - t0) * 1000
    logger.info("DOMAIN_OVERVIEW served user=%s domain=%s window=%s(%s..%s) subjects=%s "
                "present=%s ms=%.1f", uid, domain, window.name, start_iso, end_iso,
                len(composed), present_count, ms)

    window_meta = {"name": window.name, "label": window.label,
                   "start": start_iso, "end": end_iso, "days": window.days(),
                   "requested_period": period,
                   "requested_period_unresolved": requested_unresolved}

    if present_count == 0:
        # The ONLY honest "insufficient": WLJ genuinely holds no data for ANY subject in
        # the requested window (NOT a negative finding — an absence for this horizon).
        return _envelope(
            domain, WHOLE_DOMAIN_SUBJECT, "empty",
            holds_data=False, evidence="absent", window=window_meta,
            reason=(f"WLJ holds no {domain} data for this user in {window.label}. This is "
                    f"a genuine absence for that window — say so plainly; it is NOT a "
                    f"decline. Data may exist in a wider window."),
            subjects=composed, subjects_covered=sorted(composed),
        )

    evidence = "rich" if present_count >= _RICH_THRESHOLD else "thin"
    return _envelope(
        domain, WHOLE_DOMAIN_SUBJECT, "ready",
        holds_data=True, evidence=evidence, window=window_meta,
        subjects=composed, subjects_covered=sorted(composed),
        subjects_with_data=present_count,
    )


def _envelope(domain, subject, status, **extra):
    from django.utils import timezone
    base = {
        "status": status,
        "domain": domain,
        "subject": subject,
        "schema_version": DOMAIN_ANALYSIS_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "granularity": "analysis",
        "scope": ("The COMPLETE deterministic evidence WLJ holds for analyzing this "
                  "subject — trends across trailing windows, all-time span and count, "
                  "and recent record detail — composed in ONE retrieval. This IS the "
                  "investigation; reason over it. `holds_data` is WLJ's deterministic "
                  "verdict on whether relevant truth exists: when it is true you have "
                  "the evidence and must not say 'insufficient'; only `status: empty` "
                  "(holds_data false) is a genuine absence of WLJ truth."),
    }
    base.update(extra)
    return base


def get_domain_analysis(user, domain, subject, period=None):
    """
    Return the COMPOSED analysis evidence bundle for `domain`.`subject` — the whole
    deterministic investigation in one call. Delegates to the domain's existing
    history()/describe() surfaces; adds no retrieval logic.

    `period` (natural expression the user said — "last week", "past 7 days", "this month")
    applies to the whole-domain `overall` roll-up ONLY: it composes every subject against
    that ONE resolved window and nothing outside it. Ignored for a single-subject analysis,
    which intentionally investigates across standard trailing windows.

    Returns a JSON-safe envelope. `status` ∈:
        "ready"              — WLJ holds relevant truth; the bundle carries it
                               (`holds_data: true`, `evidence: rich|thin`).
        "empty"              — WLJ genuinely holds NO truth for this subject
                               (`holds_data: false`, `evidence: absent`) — the only
                               honest "insufficient".
        "unsupported_domain" — unknown domain.
        "unsupported"        — subject not analyzable for this domain.
        "error"              — read failed (logged with exc_info).
    """
    t0 = time.monotonic()
    uid = getattr(user, "id", "?")
    domain_norm = (domain or "").strip().lower()
    subject_norm = (subject or "").strip().lower()

    try:
        from apps.core.truth.domain import get_domain_truth, registered_domains
    except Exception as exc:
        logger.warning("domain_analysis: truth layer unavailable", exc_info=True)
        return _envelope(domain_norm, subject_norm, "error",
                         reason="Truth layer unavailable; see server logs.")

    if domain_norm not in registered_domains():
        return _envelope(domain_norm, subject_norm, "unsupported_domain",
                         reason="Unknown domain; not in the Truth Resolution Layer.",
                         analysis_capable_domains=analysis_capable_domains())

    try:
        truth = get_domain_truth(user, domain_norm)
    except Exception:
        logger.warning("domain_analysis: get_domain_truth failed user=%s domain=%s",
                       uid, domain_norm, exc_info=True)
        return _envelope(domain_norm, subject_norm, "error",
                         reason="Domain truth read failed; see server logs.")

    subjects = dict(getattr(truth, "analysis_subjects", {}) or {})
    if subject_norm not in subjects:
        # WHOLE-DOMAIN OVERVIEW: a request for the whole domain ("overall", "overall
        # health", "summarize my finances") composes EVERY subject into one roll-up,
        # instead of dead-ending in `unsupported`. Only for multi-subject domains — where
        # a single-subject domain's "overall" IS that one subject. This is the surface the
        # capability index advertises as the synthetic "overall" subject.
        if len(subjects) >= 2 and _is_overview_subject(subject_norm, domain_norm):
            return _domain_overview(user, domain_norm, subjects, t0, uid, period=period)
        return _envelope(
            domain_norm, subject_norm, "unsupported",
            reason=f"'{subject_norm}' is not an analyzable subject for '{domain_norm}'.",
            analyzable_subjects=sorted(subjects),
        )

    mapping = subjects[subject_norm] or {}
    metric = mapping.get("history_metric") or subject_norm
    entity_type = mapping.get("entity_type")
    windows = tuple(mapping.get("windows") or DEFAULT_WINDOWS)

    try:
        # 1. Trends across trailing windows (reuse the History surface).
        history = {}
        for w in windows:
            history[w] = _compact_history(
                get_domain_history(user, domain_norm, metric, period=w))

        # 2. All-time span + total (reuse History, one wide custom range).
        at = _compact_history(get_domain_history(
            user, domain_norm, metric, period="custom",
            start=_EARLIEST, end=_today_iso(user)))
        total = at.get("total") or 0
        all_time = {"present": at.get("present", False), "total": total,
                    "count": at.get("count"), "unit": at.get("unit"),
                    "span": {"start": at.get("first_point"),
                             "end": at.get("last_point")}}

        # 3. Record-level detail (reuse the Entity surface) when the subject has one.
        records = None
        record_count = 0
        if entity_type:
            records = _compact_entities(
                get_domain_entity(user, domain_norm, entity_type=entity_type))
            record_count = records.get("count") or 0
    except Exception:
        logger.warning("domain_analysis: composition failed user=%s domain=%s subject=%s",
                       uid, domain_norm, subject_norm, exc_info=True)
        return _envelope(domain_norm, subject_norm, "error",
                         reason="Analysis composition failed; see server logs.")

    # 4. Deterministic completeness verdict — the guarantee's anchor.
    window_present = any(w.get("present") for w in history.values())
    holds_data = bool(total) or record_count > 0 or window_present
    ms = (time.monotonic() - t0) * 1000
    logger.info("DOMAIN_ANALYSIS served user=%s domain=%s subject=%s holds_data=%s "
                "total=%s records=%s ms=%.1f", uid, domain_norm, subject_norm,
                holds_data, total, record_count, ms)

    if not holds_data:
        # The ONLY honest "insufficient": WLJ genuinely holds no such truth.
        return _envelope(
            domain_norm, subject_norm, "empty",
            holds_data=False, evidence="absent",
            reason=(f"WLJ holds no {subject_norm} data for this user across any window "
                    f"or record. This is a genuine absence — say so plainly and, if "
                    f"useful, how it would come to be recorded."),
            history=history, all_time=all_time, records=records,
        )

    evidence = "rich" if (total >= _RICH_THRESHOLD or record_count >= _RICH_THRESHOLD) \
        else "thin"
    return _envelope(
        domain_norm, subject_norm, "ready",
        holds_data=True, evidence=evidence,
        metric=metric, entity_type=entity_type,
        history=history, all_time=all_time, records=records,
    )
