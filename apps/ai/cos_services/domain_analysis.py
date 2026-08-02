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
# Two windows keep the roll-up bounded (2 history reads per distinct metric) while still
# surfacing slower-cadence metrics (a monthly weight) that a 7-day-only window would read
# falsely empty. Recent + this-month is the natural "how am I doing lately" pair.
_OVERVIEW_WINDOWS = ("last_7_days", "this_month")


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


def _overview_window(h):
    """Compact per-window projection for the roll-up — present + headline aggregates only
    (NO raw points), so a whole-domain bundle stays composed, not a data dump."""
    if h.get("status") != "ready":
        return {"present": False, "status": h.get("status")}
    pts = h.get("points") or []
    return {"present": True, "unit": h.get("unit"), "total": h.get("total"),
            "average": h.get("average"), "count": h.get("count"),
            "last_point": (pts[-1].get("date") if pts else None)}


def _domain_overview(user, domain, subjects, t0, uid):
    """Compose EVERY analyzable subject of `domain` into ONE whole-domain evidence bundle —
    the "overall" roll-up (the whole-domain analogue of a single-subject analysis).

    Pure COMPOSITION: reuses each subject's existing history surface across a bounded window
    pair; adds NO retrieval logic. Aliases are deduped by history_metric so a metric is
    composed once. Carries the SAME deterministic `holds_data` verdict as a single-subject
    analysis — so the reasoner can never truthfully say 'insufficient' while WLJ still holds
    truth for any subject in the domain.
    """
    seen_metrics = set()
    composed = {}
    present_count = 0
    for name, mapping in subjects.items():
        mapping = mapping or {}
        metric = mapping.get("history_metric") or name
        if metric in seen_metrics:          # dedup aliases (bp/blood_pressure → one metric)
            continue
        seen_metrics.add(metric)
        windows = {}
        present = False
        for w in _OVERVIEW_WINDOWS:
            try:
                ch = _overview_window(get_domain_history(user, domain, metric, period=w))
            except Exception:
                logger.warning("domain_overview: history failed user=%s domain=%s "
                               "metric=%s window=%s", uid, domain, metric, w, exc_info=True)
                ch = {"present": False, "status": "error"}
            windows[w] = ch
            present = present or ch.get("present", False)
        if present:
            present_count += 1
        composed[name] = {"metric": metric, "present": present, "windows": windows}

    ms = (time.monotonic() - t0) * 1000
    logger.info("DOMAIN_OVERVIEW served user=%s domain=%s subjects=%s present=%s ms=%.1f",
                uid, domain, len(composed), present_count, ms)

    if present_count == 0:
        # The ONLY honest "insufficient": WLJ genuinely holds no data for ANY subject.
        return _envelope(
            domain, WHOLE_DOMAIN_SUBJECT, "empty",
            holds_data=False, evidence="absent",
            reason=(f"WLJ holds no {domain} data for this user across any subject in the "
                    f"recent windows. This is a genuine absence — say so plainly."),
            subjects=composed, subjects_covered=sorted(composed),
        )

    evidence = "rich" if present_count >= _RICH_THRESHOLD else "thin"
    return _envelope(
        domain, WHOLE_DOMAIN_SUBJECT, "ready",
        holds_data=True, evidence=evidence,
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


def get_domain_analysis(user, domain, subject):
    """
    Return the COMPOSED analysis evidence bundle for `domain`.`subject` — the whole
    deterministic investigation in one call. Delegates to the domain's existing
    history()/describe() surfaces; adds no retrieval logic.

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
            return _domain_overview(user, domain_norm, subjects, t0, uid)
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
