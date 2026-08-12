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
from datetime import date, timedelta

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
# never be influenced by this-month data).
_OVERVIEW_DEFAULT_PERIOD = "last_7_days"   # only for an EXPLICIT-but-unresolvable period

# DOMAIN-NATURAL DEFAULT HORIZON — when the user names NO period, a Chief of Staff answers over
# the horizon a reasonable person means by the question, not a fixed technical default. Money is
# thought of monthly; relationships are seasonal; a single week is too short to judge almost
# anything. Values are DAYS. The 7-day floor was an internal default, never a customer-natural
# one. (Explicit user periods — "last week", "this year" — are always honored exactly; these
# defaults apply ONLY when the user states no period.)
_DOMAIN_DEFAULT_DAYS = {
    "finance": 30,          # ~ the current month
    "health": 30,
    "relationships": 90,    # not meaningfully judged over a week
    "medical": 90,
    "goals": 30,
    "faith": 30,
    "habits": 30,
    "nutrition": 14,
    "journal": 30,
    "legacy": 365,
}
_GENERAL_DEFAULT_DAYS = 30  # the natural floor for "how am I doing?" when the domain has no map

# AUTO-WIDEN — if the natural window holds no trend activity, widen to the most recent horizon
# that does (deterministic, most-recent-first, bounded). "Answer the question a reasonable
# person believes they asked" — never report "no data" for a week when there is a month of it.
_WIDEN_LADDER_DAYS = (90, 365, 3650)


def _window_label(days):
    if days >= 3650:
        return "your full history"
    if days >= 365 and days % 365 == 0:
        y = days // 365
        return f"the last {y} year" + ("s" if y > 1 else "")
    return f"the last {days} days"


def _window_of_days(days, today):
    """A custom Period covering the trailing `days` ending today (inclusive)."""
    from apps.core.truth.periods import Period
    return Period(f"last_{days}_days", today - timedelta(days=days - 1), today,
                  _window_label(days))


def _user_today(user):
    try:
        from apps.core.utils import get_user_today
        return get_user_today(user) or date.today()
    except Exception:
        return date.today()


def _compose_trends(user, domain, trend_subjects, window, uid):
    """Compose every trend facet against ONE window. Returns (composed, present_count)."""
    start_iso, end_iso = window.start.isoformat(), window.end.isoformat()
    seen_metrics, composed, present_count = set(), {}, 0
    for name, mapping in trend_subjects.items():
        mapping = mapping or {}
        metric = mapping.get("history_metric") or name
        if metric in seen_metrics:              # dedup aliases (bp/blood_pressure → one metric)
            continue
        seen_metrics.add(metric)
        try:
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
    return composed, present_count


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


def _overview_trend_subjects(truth):
    """The TREND facets the assessment bundle composes: the domain's declared
    `analysis_subjects` (when it has >= 2), else a fallback derived from its composed
    `history_metrics` (each metric is a facet) when it has >= 2 — so a domain's trend
    coverage tracks its COMPOSED history truth, with no separate registration. Fewer than 2
    either way → no trend facets (the bundle may still stand on current STATE)."""
    subs = dict(getattr(truth, "analysis_subjects", {}) or {})
    if len(subs) >= 2:
        return subs
    hist = tuple(getattr(truth, "history_metrics", ()) or ())
    if len(hist) >= 2:
        return {m: {"history_metric": m} for m in hist}
    return {}


def _overview_state(user, domain):
    """Current STATE facets — 'where things stand NOW' — via the ONE canonical composed-state
    read (get_domain_state: a single cached SAE snapshot). REUSE, not re-derivation; adds no
    retrieval logic. Returns a clean facts dict (internal `_`-prefixed keys stripped), or {}
    when there is no warm state. This is the half of the assessment that answers 'what is my
    position' (net worth, spending, overdue count…), complementing the trend half ('what is
    changing')."""
    try:
        from apps.ai.cos_services.domain_state import get_domain_state
        env = get_domain_state(user, domain)
    except Exception:
        logger.warning("domain_overview: state read failed domain=%s", domain, exc_info=True)
        return {}
    if not isinstance(env, dict) or env.get("status") != "ready":
        return {}
    st = env.get("state")
    if not isinstance(st, dict):
        return {}
    return {k: v for k, v in st.items() if not str(k).startswith("_")}


def _state_is_present(state):
    """A composed STATE counts as a real assessment signal ONLY when it carries actual
    position facts. An empty state, an explicit 'disabled' marker (finance returns
    {'enabled': False} when the user has no finance set up), or a state carrying only that flag
    is NOT a signal. Without this, a disabled/empty state was truthy (`bool({'enabled': False})`
    is True) and the overview reported `holds_data=True` over ZERO data — telling the model it
    had evidence it did not have (Blocker #8, a fabrication trap the holds_data contract exists
    to prevent). Applies to every non-health domain."""
    if not isinstance(state, dict) or not state:
        return False
    if state.get("enabled") is False:
        return False
    return any(k != "enabled" for k in state)


def _assessment_capable(truth):
    """A domain earns a whole-domain executive assessment when WLJ composes >= 2 assessment
    facets for it — >= 2 TREND facets (analysis_subjects / history_metrics) OR >= 2 current
    STATE metrics. Coverage is a property of composed truth; there is no per-domain
    registration and no Health special-case. Mirrors the `overall` advertisement in
    apps.core.truth.domain.DomainTruth.supports()."""
    if len(_overview_trend_subjects(truth)) >= 2:
        return True
    return len(tuple(getattr(truth, "current_metrics", ()) or ())) >= 2


def _domain_overview(user, domain, truth, t0, uid, period=None):
    """Compose ONE whole-domain executive-assessment evidence bundle — the deterministic
    material a Chief of Staff reviews before answering "how are my <domain>?". It is NOT a
    verdict (WLJ never says "healthy"/"slipping"); it is the composed TRUTH the model forms
    the verdict from. Two complementary halves, composed from EXISTING surfaces only (no new
    retrieval, no reasoning):

      • STATE   — where things stand now (`get_domain_state`, one cached read).
      • TRENDS  — what is changing, per facet, over the ONE window the user asked for
                  (`get_domain_history` with the within-window `change`: improved vs got
                  worse). The window is resolved ONCE and every facet reads that identical
                  (start, end), so the bundle can never mix horizons.

    `holds_data` is true when WLJ holds EITHER a current state OR any trend for the window —
    the reasoner must then reason over it, never say "insufficient". Only a genuine absence
    of both is `empty`. A facet `present:false` is HONEST missing-data-for-the-window, never
    a decline.
    """
    trend_subjects = _overview_trend_subjects(truth)

    # --- WINDOW (the horizon a reasonable person means) ----------------------------------
    # An EXPLICIT user period ("last week", "this year") is honored exactly — no smart default,
    # no widen. When the user names NO period, use the DOMAIN-NATURAL default, then AUTO-WIDEN
    # to the most recent horizon that actually holds trend activity, so "how am I doing?" is
    # answered over the period the question implies — never a fixed 7-day technical default.
    explicit = bool(period)
    widened = False
    if explicit:
        window, requested_unresolved = _resolve_overview_window(user, period)
        composed, present_count = _compose_trends(user, domain, trend_subjects, window, uid)
    else:
        requested_unresolved = False
        today = _user_today(user)
        default_days = _DOMAIN_DEFAULT_DAYS.get(domain, _GENERAL_DEFAULT_DAYS)
        ladder = (default_days,) + tuple(d for d in _WIDEN_LADDER_DAYS if d > default_days)
        window = _window_of_days(ladder[0], today)
        composed, present_count = _compose_trends(user, domain, trend_subjects, window, uid)
        # Widen only when the natural window is barren of trend activity AND there are facets
        # to find — stop at the first wider window that holds data.
        if trend_subjects:
            for days in ladder[1:]:
                if present_count > 0:
                    break
                cand = _window_of_days(days, today)
                composed, present_count = _compose_trends(
                    user, domain, trend_subjects, cand, uid)
                window, widened = cand, True

    start_iso, end_iso = window.start.isoformat(), window.end.isoformat()

    # --- STATE (where things stand now) --------------------------------------------------
    state = _overview_state(user, domain)

    # HEALTH (proving-ground for the concept principle): the flat 115-key state MIXES facts
    # with WLJ's OWN reasoning — a per-category scorecard, a written narrative + advice, a
    # named verdict ("RECOMPOSITION"), status judgments. Handed a scorecard, the model
    # returns a report. So for health, replace it with the deterministic FACTS organized by
    # concept (body composition, glucose, cardiovascular, sleep & recovery, activity,
    # hydration, respiratory), reasoning stripped. WLJ organizes perception; the model does
    # all prioritization, meaning, and advice. Net REMOVAL of WLJ reasoning — not addition.
    concepts = None
    if domain == "health" and isinstance(state, dict) and state:
        try:
            from apps.health.services.health_concept_view import build_health_concept_view
            concepts = build_health_concept_view(state).get("concepts") or None
        except Exception:
            logger.warning("domain_overview: health concept view failed", exc_info=True)

    has_state = bool(concepts) if domain == "health" else _state_is_present(state)
    signals = present_count + (1 if has_state else 0)
    ms = (time.monotonic() - t0) * 1000
    logger.info("DOMAIN_OVERVIEW served user=%s domain=%s window=%s(%s..%s) trends=%s "
                "present=%s state=%s concepts=%s ms=%.1f", uid, domain, window.name,
                start_iso, end_iso, len(composed), present_count, bool(state),
                len(concepts) if concepts else 0, ms)

    window_meta = {"name": window.name, "label": window.label,
                   "start": start_iso, "end": end_iso, "days": window.days(),
                   "requested_period": period,
                   "requested_period_unresolved": requested_unresolved,
                   "auto_selected": (not explicit), "widened": widened,
                   # The model MUST tell the user which period it assessed — always when WLJ
                   # chose the horizon, and especially when it widened past the natural default.
                   "state_the_period": (
                       f"You assessed {window.label}. State this period to the user"
                       + (" (you widened past the recent window because it had no activity)"
                          if widened else "") + ".")}

    if signals == 0:
        # The ONLY honest "insufficient": WLJ holds NEITHER a current state NOR any trend.
        return _envelope(
            domain, WHOLE_DOMAIN_SUBJECT, "empty",
            holds_data=False, evidence="absent", window=window_meta,
            reason=(f"WLJ holds no {domain} state or trend for this user in {window.label}. "
                    f"This is a genuine absence — say so plainly; it is NOT a decline."),
            state=state or None, subjects=composed, subjects_covered=sorted(composed),
        )

    evidence = "rich" if signals >= _RICH_THRESHOLD else "thin"

    # HEALTH: the model receives ONE concept-organized set of deterministic facts. No flat
    # state dump, no per-category scorecard, no verdict, no advice — it decides what matters,
    # what it means, and what to do, from the organized facts.
    if domain == "health" and concepts:
        return _envelope(
            domain, WHOLE_DOMAIN_SUBJECT, "ready",
            holds_data=True, evidence=evidence, window=window_meta,
            # `concepts` = the deterministic facts organized the way a health expert perceives
            # them (members carry value + measured change), WLJ's own scorecard/verdict/
            # narrative/advice REMOVED. `subjects` = the per-facet windowed trends (also facts)
            # for the requested window. No flat 115-key state, no reasoning. The model does all
            # prioritization, meaning, and advice.
            concepts=concepts,
            subjects=composed, subjects_covered=sorted(composed),
            subjects_with_data=present_count,
            note=("Deterministic facts only. WLJ has made NO judgment here — no ranking, no "
                  "verdict, no status, no advice."),
        )

    return _envelope(
        domain, WHOLE_DOMAIN_SUBJECT, "ready",
        holds_data=True, evidence=evidence, window=window_meta,
        # STATE = where things stand now; `subjects` (trends) = what is changing. The model
        # forms ONE overall assessment from BOTH, then names the biggest positive, the
        # biggest concern, and the single highest-leverage action (evidence supports the
        # conclusion — it is not the conclusion).
        state=state or None,
        subjects=composed, subjects_covered=sorted(composed),
        subjects_with_data=present_count,
        has_state=has_state,
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
                  "subject — trends across trailing windows, the all-time span with its "
                  "coherent lifetime CHANGE (`all_time.change` + `all_time.start`/`.end`, "
                  "each a reading WITH its own date), and recent record detail — composed "
                  "in ONE retrieval. For a TOTAL question ('how much have I lost/gained "
                  "since I started') use `all_time.change` (first→last value + delta) and "
                  "`all_time.start`/`.end`; NEVER pair a trailing window's value with the "
                  "all-time start date. This is the COMPLETE evidence to CONSIDER — it is "
                  "NOT a checklist to recite: reason over ALL of it, then PRESENT ONLY the "
                  "one or two things that best answer the user and let the rest go unsaid "
                  "(`subjects_covered`/`subjects` is what was CONSIDERED, never what you must "
                  "say). `holds_data` is WLJ's deterministic verdict on whether relevant "
                  "truth exists: when it is true you have the evidence and must not say "
                  "'insufficient'; only `status: empty` (holds_data false) is a genuine "
                  "absence of WLJ truth."),
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
        # CUSTOMER-SAFE by construction (Blocker #5): the model narrates this `reason`. It must
        # NEVER carry internal routing language ("unsupported domain", "not in the Truth
        # Resolution Layer") — that leaked to the user as "the life domain isn't supported."
        # And it must NEVER tell the model to hand the scoping back to the user (Blocker #6):
        # "give me an overall assessment of my whole life" answered with "which area?" is not a
        # Chief of Staff. Guide the model to ANSWER — directly and from the truth it already has.
        if _is_overview_subject(subject_norm, domain_norm):
            # WHOLE-LIFE / cross-domain request (e.g. "assess my whole life", "overall status").
            reason = ("This is a whole-life / cross-domain request. GIVE A REAL ASSESSMENT NOW: "
                      "lead with the single most important thing for the user right now (see "
                      "current_action) and synthesize briefly across the areas you can see "
                      "(analysis_capable_domains — e.g. health, finances, relationships, goals, "
                      "habits). Do NOT tell the user that anything is missing or cannot be "
                      "assessed, and do NOT ask them to narrow their request, pick a domain, or "
                      "choose an area — answer the whole-life question directly; you may offer to "
                      "go deeper on one area afterward.")
        else:
            # A specific subject under a name that isn't a tracked area.
            reason = ("That is not one of the areas WLJ tracks. Answer the user's underlying "
                      "question from the areas it does track (analysis_capable_domains — e.g. "
                      "health, finances, relationships, goals, habits), leading with what "
                      "matters most (current_action). Do NOT tell the user that anything is "
                      "missing or cannot be assessed, and do NOT ask them to narrow their "
                      "request — give your best answer directly.")
        return _envelope(domain_norm, subject_norm, "unsupported_domain",
                         reason=reason,
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
        # WHOLE-DOMAIN EXECUTIVE ASSESSMENT: a request for the whole domain ("overall",
        # "overall health", "summarize my finances") composes the domain's STATE + TRENDS
        # into one bundle the model reasons an assessment from, instead of dead-ending in
        # `unsupported`. Available whenever WLJ composes >= 2 assessment facets for the
        # domain (>= 2 trend facets OR >= 2 current-state metrics) — coverage tracks
        # composed truth, never a per-domain registration.
        if _is_overview_subject(subject_norm, domain_norm) and _assessment_capable(truth):
            return _domain_overview(user, domain_norm, truth, t0, uid, period=period)
        # MODEL-DIRECTED RETRIEVAL PERSISTENCE (2026-08-12): an insufficient/absent ANALYSIS
        # must never read as "no truth exists". When the analysis surface cannot answer, point
        # the model to the domain's OTHER retrievable surfaces (its own registered entity/history
        # capabilities) so it can DRILL rather than stop. This is the analysis surface reporting
        # its own limits + the domain's alternatives — NOT a per-domain router and NOT a fallback
        # CALL (WLJ never calls get_entity here; it only tells the model what else is retrievable,
        # and the model decides). Generic: derived from the domain's registered capabilities.
        et = tuple(getattr(truth, "entity_types", ()) or ())
        hm = tuple(getattr(truth, "history_metrics", ()) or ())
        alts = []
        if et:
            alts.append(f"its records with get_entity(domain='{domain_norm}') "
                        f"(types: {', '.join(sorted(et))})")
        if hm:
            alts.append(f"its history with get_history(domain='{domain_norm}', "
                        f"metric one of: {', '.join(sorted(hm))})")
        drill = ((" This analysis surface does not cover it, but the domain's deterministic "
                  "truth IS retrievable — inspect " + " or ".join(alts) + ", then reason from "
                  "those records. Do NOT conclude the truth is unavailable from a thin analysis.")
                 if alts else "")
        return _envelope(
            domain_norm, subject_norm, "unsupported",
            # CUSTOMER-SAFE by construction (Blocker #5, same class): never narrate that a
            # measure "is not analyzable" — guide the model to what WLJ DOES track / expose.
            reason=(f"WLJ tracks these assessable measures for '{domain_norm}': "
                    f"{', '.join(sorted(subjects)) or '(none)'}."
                    + drill +
                    " Do NOT tell the user that this measure cannot be analyzed — simply work "
                    "from what's available."),
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

        # 2. All-time span + LIFETIME CHANGE (reuse History, one wide custom range).
        # The lifetime change is composed as ONE coherent fact: the earliest reading
        # (date WITH its value) → the latest reading (date WITH its value) → the
        # deterministic delta/direction (the series' own `change`). A "how much have I
        # lost/gained in TOTAL" question is therefore answered from a SINGLE source, so it
        # can never be assembled by pairing a trailing window's baseline (e.g. this_year's
        # 309.4) with the all-time start date (Aug 2 2024) — the false-pairing class that
        # produced "you went from 309.4 lb since August 2, 2024".
        at_raw = get_domain_history(
            user, domain_norm, metric, period="custom",
            start=_EARLIEST, end=_today_iso(user))
        at = _compact_history(at_raw)
        total = at.get("total") or 0
        at_points = at_raw.get("points") or []
        all_time = {
            "present": at.get("present", False), "total": total,
            "count": at.get("count"), "unit": at.get("unit"),
            "span": {"start": at.get("first_point"), "end": at.get("last_point")},
            # Coherent endpoints — the earliest/latest reading WITH its own date, never a
            # date from one source and a value from another.
            "start": ({"date": at_points[0].get("date"),
                       "value": at_points[0].get("value")} if at_points else None),
            "end": ({"date": at_points[-1].get("date"),
                     "value": at_points[-1].get("value")} if at_points else None),
            # THE total-change fact: first→last value, delta, and direction (rising/falling)
            # across the whole record. Use THIS for "total lost/gained since I started".
            "change": at_raw.get("change"),
        }

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
