"""
Executive Summary Composer — Beth's exec briefing as deterministic data.

This is the canonical source of "what's going well / what needs attention /
biggest risk / focus right now / trajectory" — built from existing engines:

    SAE state                  → driver verdicts per domain
    Insights (severity=positive)→ "going well"
    Insights (severity=warning)→ "needs attention"
    Insights (severity=critical)→ "biggest risk" (tied with risk selector)
    Predictions                → trajectory hints
    GuidanceItem (priority 1-2)→ "recommended focus"
    Selectors                  → focus_now / biggest_risk / fix_priority

Architecture rules honored:
  - LLM-last: zero LLM here. Output is structured data; any narration layer
    (dashboard renderer, Beth) reads this dict and styles it.
  - State-first: only the read-allowlisted models (Insight, Prediction,
    GuidanceItem) and SAE-backed selectors are touched. No domain ORM
    aggregates.
  - No duplicate truth: domain verdicts come from per-module SAE state;
    drivers reference existing fields; the selectors here are the same ones
    Beth's locked-facts use.
  - Snapshot-safe: read-only reads against cached state + indexed rows.

Returned shape (stable; treat as a soft public contract — keep additive):

    {
        "trajectory": "improving" | "steady" | "slipping" | "mixed" | "unknown",
        "going_well":      [ {title, module, evidence}, ... ],
        "needs_attention": [ {title, module, severity, evidence}, ... ],
        "biggest_risk":    {title, message, module, source} | None,
        "biggest_opportunity": {title, message, module, source} | None,
        "focus_now":       {title, reason, time_display, source} | None,
        "follow_on":       [ {title, time_display}, ... ],
        "recommendations": [ {title, message, priority, module}, ... ],
        "as_of":           ISO datetime,
        "engine_versions": {"sae": int, "pie": int, "prie": int, "pge": int},
    }

Empty / no-data cases collapse gracefully — callers always receive every key
with a sane default. No exceptions are raised on the request path.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


# ── Knobs ──────────────────────────────────────────────────────────────
# Keep small — the dashboard surface is "executive", not exhaustive.
MAX_GOING_WELL = 5
MAX_NEEDS_ATTENTION = 5
MAX_RECOMMENDATIONS = 3


# ── Time bands ─────────────────────────────────────────────────────────
# Phase A trust fix (2026-06-06): the executive briefing was emitting
# "let's protect the rest of the day" at 8 AM — psychologically wrong
# because the day is still highly recoverable. Headlines now branch on
# a small fixed band so morning emphasises *reset/momentum* and evening
# emphasises *close strong*.
#
# Bands are intentionally rough — five bands cover the common day
# shapes without producing a different message every hour:
#
#   early_morning : 04–10  (fresh, fully recoverable, motivational reset)
#   morning       : 10–12  (still ahead of midday; gentle catch-up)
#   midday        : 12–17  (afternoon protection mode)
#   evening       : 17–21  (close strong; pick the highest-impact item)
#   late_evening  : 21–04  (don't shame; brief, generous, tomorrow framing)
def _time_band(user_now) -> str:
    """Return one of: early_morning, morning, midday, evening, late_evening.

    ``user_now`` is a timezone-aware datetime in the USER's local time
    (composer passes ``get_user_now(user)``). When None is passed the
    function returns "midday" — a neutral default that keeps existing
    behaviour for any caller that hasn't been updated yet.
    """
    if user_now is None:
        return "midday"
    hour = user_now.hour
    if 4 <= hour < 10:
        return "early_morning"
    if 10 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "midday"
    if 17 <= hour < 21:
        return "evening"
    return "late_evening"


# ── Headline matrix ────────────────────────────────────────────────────
# Per overall_state × time_band copy. Kept as a pure data table so
# wording can be tuned without re-reading the surrounding logic.
#
# WLJ philosophy reminders baked into the wording:
#   - missed ≠ failed (morning bias: recoverable, reset, momentum)
#   - protect ≠ shame (midday bias: prioritize, hold the line)
#   - close strong ≠ catch-everything (evening bias: highest-impact)
#
# Special branches (recovery_mode / specific overdue counts / specific
# at_risk counts) are handled inside _derive_headline() and fall back
# to this matrix when no special branch matches.
_HEADLINE_MATRIX: dict[str, dict[str, str]] = {
    "at_risk": {
        "early_morning":
            "You're behind this morning, but the day is fully recoverable. "
            "A strong reset now rebuilds momentum.",
        "morning":
            "Behind early — but the day is still in front of you. "
            "One focused action restarts the rhythm.",
        "midday":
            "Several priorities slipped this morning — reprioritize and "
            "protect the afternoon.",
        "evening":
            "Day's been bumpy — close strong with the highest-impact item.",
        "late_evening":
            "Tough day. Pick the one thing that protects tomorrow and "
            "call it done.",
    },
    "slipping": {
        "early_morning":
            "Slow start, but the day is wide open. A small win in the "
            "next hour resets the trajectory.",
        "morning":
            "Drift this morning — one focused action gets you back on "
            "rhythm before the day fills up.",
        "midday":
            "A few things are slipping — pick one to address this "
            "afternoon and the trajectory turns.",
        "evening":
            "Drift this week — one decisive action tonight or first thing "
            "tomorrow resets the rhythm.",
        "late_evening":
            "Drift detected — name one priority for tomorrow morning and "
            "let the rest go for tonight.",
    },
    "improving": {
        "early_morning":
            "Strong morning shape — protect what's working and keep the "
            "rhythm consistent.",
        "morning":
            "Trending up — keep the rhythm consistent through midday.",
        "midday":
            "Trending up — protect the afternoon and you ride this "
            "into tomorrow.",
        "evening":
            "Strong day. Close it out and bank the momentum for tomorrow.",
        "late_evening":
            "Solid trajectory. Rest well — momentum like this compounds.",
    },
    "mixed": {
        "early_morning":
            "Mixed signals heading in — keep the wins, address the drift "
            "before noon and the day balances.",
        "morning":
            "Mixed signals — keep what's working and address the drift "
            "with one focused action.",
        "midday":
            "Mixed signals this week — real wins, real drift. Keep the "
            "wins; address the drift.",
        "evening":
            "Wins and drift in the same day. Close with the wins and "
            "name what you'll address tomorrow.",
        "late_evening":
            "Mixed day — count the wins, name one drift to address "
            "tomorrow, rest.",
    },
    "steady": {
        "early_morning":
            "Steady shape this morning — hold the line and keep the "
            "rhythm.",
        "morning":
            "Steady — hold the line and keep the rhythm through "
            "midday.",
        "midday":
            "Steady today. Hold the line and keep the rhythm.",
        "evening":
            "Steady day. Close it out and reset for tomorrow.",
        "late_evening":
            "Steady. Rest well.",
    },
    "unknown": {
        "early_morning":
            "Light data so far — log a few things this morning and the "
            "briefing fills in.",
        "morning":
            "Light data so far — log a few things and the briefing fills "
            "in.",
        "midday":
            "Light data so far — log a few things and the briefing fills "
            "in.",
        "evening":
            "Light data so far — log today's key items and the briefing "
            "fills in.",
        "late_evening":
            "Light data so far — a quick log tonight or in the morning "
            "fills the briefing in.",
    },
}
MAX_FOLLOW_ON = 5            # how many "coming up" hints next to focus_now
INSIGHT_WINDOW_DAYS = 7      # only fresh insights count toward the briefing


def build_executive_summary(user, execution_contract=None) -> dict[str, Any]:
    """Compose the executive briefing from canonical sources.

    Read-only. Safe on the request path.

    Args:
        user: User instance.
        execution_contract: Optional pre-fetched dict from
            ``build_today_execution(user)``. Passed by the v3 dashboard
            composer so the executive summary + rhythm + gauges share
            ONE truth fetch per request (Phase 2 dedup). Threaded into
            ``build_execution_state`` via ``_collect_focus_now``. When
            omitted (any other caller) the function fetches its own.
    """
    try:
        going_well = _collect_going_well(user)
    except Exception:
        logger.warning("exec_summary: going_well failed", exc_info=True)
        going_well = []

    try:
        needs_attention = _collect_needs_attention(user)
    except Exception:
        logger.warning("exec_summary: needs_attention failed", exc_info=True)
        needs_attention = []

    try:
        focus_now, follow_on, exec_state = _collect_focus_now(
            user, execution_contract=execution_contract,
        )
    except Exception:
        logger.warning("exec_summary: focus_now failed", exc_info=True)
        focus_now, follow_on, exec_state = None, [], None

    try:
        biggest_risk = _collect_biggest_risk(user, needs_attention, exec_state)
    except Exception:
        logger.warning("exec_summary: biggest_risk failed", exc_info=True)
        biggest_risk = None

    try:
        biggest_opportunity = _collect_biggest_opportunity(user)
    except Exception:
        logger.warning("exec_summary: biggest_opportunity failed", exc_info=True)
        biggest_opportunity = None

    try:
        recommendations = _collect_recommendations(user)
    except Exception:
        logger.warning("exec_summary: recommendations failed", exc_info=True)
        recommendations = []

    # Coherence gate: current execution pressure (overdue / at-risk items
    # right now) IS a current-state concern. Surface it into needs_attention
    # so the briefing can never say "All clear" while real items are behind.
    needs_attention = _augment_attention_with_execution(needs_attention, exec_state)

    # ── Orchestration layer ──────────────────────────────────────────────
    # ONE dominant-state selection. Both the badge (trajectory) and the
    # headline derive from this single verdict, so they can never contradict
    # ("STEADY" badge + "you're slipping" headline). Lower-priority slots
    # (opportunity, recommendations) render beneath this state but may not
    # override it.
    overall_state = _derive_overall_state(
        going_well, needs_attention, biggest_risk, exec_state,
    )
    trajectory = overall_state
    # Phase A trust fix — pass user_now so the headline matrix can
    # branch on time-of-day. Fail-soft: if the lookup fails for any
    # reason, _derive_headline falls back to its default "midday" band.
    try:
        from apps.core.utils import get_user_now
        _user_now = get_user_now(user)
    except Exception:
        _user_now = None
    headline = _derive_headline(
        overall_state, going_well, needs_attention, exec_state, focus_now,
        user_now=_user_now,
    )

    return {
        "trajectory": trajectory,
        "headline": headline,
        "going_well": going_well,
        "needs_attention": needs_attention,
        "biggest_risk": biggest_risk,
        "biggest_opportunity": biggest_opportunity,
        "focus_now": focus_now,
        "follow_on": follow_on,
        "recommendations": recommendations,
        "as_of": timezone.now().isoformat(),
    }


# ── Going Well ─────────────────────────────────────────────────────────


def _collect_going_well(user) -> list[dict[str, Any]]:
    """Recent positive Insights, newest first."""
    from apps.core.ai_insights.models import Insight

    cutoff = timezone.now() - timedelta(days=INSIGHT_WINDOW_DAYS)
    qs = (
        Insight.objects.filter(
            user=user,
            severity="positive",
            status__in=("new", "read"),
            created_at__gte=cutoff,
        )
        .order_by("-created_at")[:MAX_GOING_WELL]
    )
    return [
        {
            "title": i.title,
            "message": i.message,
            "module": i.module,
            "insight_type": i.insight_type,
        }
        for i in qs
    ]


# ── Needs Attention ────────────────────────────────────────────────────


def _collect_needs_attention(user) -> list[dict[str, Any]]:
    """Recent warning / critical Insights, severity-weighted then newest.

    Phase A trust fix:

      * **Dedup by title** (Change A2). The Insight store dedupes by
        ``dedupe_key`` only — which encodes a rolling time window, so
        the same condition (e.g. "Overtraining Risk") can produce two
        rows on consecutive days. Presentation layer collapses by
        title, keeping the most recent row per title.

      * **Calorie synthesis** (Change A3). When the user has multiple
        "Calories under/over target by N%" rows, collapse them to a
        single executive-level sentence so the briefing reads as one
        synthesised concern rather than three noisy daily snapshots.

    DB rows are untouched; this is a render-time consolidation only.
    """
    from apps.core.ai_insights.models import Insight

    cutoff = timezone.now() - timedelta(days=INSIGHT_WINDOW_DAYS)
    qs = Insight.objects.filter(
        user=user,
        severity__in=("warning", "critical"),
        status__in=("new", "read"),
        created_at__gte=cutoff,
    ).order_by("-created_at")

    # Critical first, warning second; preserve created_at order inside each.
    critical = [i for i in qs if i.severity == "critical"]
    warning = [i for i in qs if i.severity == "warning"]
    ordered = critical + warning

    # ── Change A2: dedupe by title (most recent wins). ──
    # The query is already ordered by -created_at within each severity
    # bucket, so the first occurrence of each title is the freshest.
    seen_titles: set[str] = set()
    deduped = []
    for i in ordered:
        title_key = (i.title or "").strip().lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        deduped.append(i)

    # ── Change A3: synthesise repeated calorie alerts. ──
    # After dedupe-by-title there can still be multiple rows like
    # "Calories under target by 27%" / "by 30%" / "by 35%" because
    # the percentage is baked into the title. Collapse them to ONE
    # executive-level sentence rooted in the most recent reading.
    deduped = _synthesize_calorie_alerts(deduped)

    ordered_view = deduped[:MAX_NEEDS_ATTENTION]

    return [
        {
            "title": i.title,
            "message": i.message,
            "module": i.module,
            "severity": i.severity,
            "insight_type": i.insight_type,
        }
        for i in ordered_view
    ]


def _synthesize_calorie_alerts(insights: list) -> list:
    """Collapse repeated "Calories under/over target by N%" rows into
    one executive-level signal.

    Strategy: find all calorie-trend rows (matched by ``insight_type``
    or a title prefix); pick the most recent as the representative;
    overwrite its message with a one-line synthesis. The other calorie
    rows are dropped from the returned list. All non-calorie insights
    pass through untouched.

    This is purely presentational — the underlying Insight rows are
    not modified.
    """
    if not insights:
        return insights

    def _is_calorie_alert(insight) -> bool:
        itype = (getattr(insight, "insight_type", "") or "").lower()
        title = (getattr(insight, "title", "") or "").lower()
        # Match both the canonical insight_type produced by
        # NutritionCalorieTrendRule and any title-shaped variant.
        return (
            "calorie" in itype
            or "nutrition_calorie" in itype
            or title.startswith("calories ")
        )

    calorie_rows = [i for i in insights if _is_calorie_alert(i)]
    other_rows = [i for i in insights if not _is_calorie_alert(i)]

    if len(calorie_rows) <= 1:
        # Nothing to synthesise — original ordering preserved.
        return insights

    # `insights` came in -created_at order within each severity bucket,
    # so the first calorie row is the most recent.
    representative = calorie_rows[0]

    # Best-effort: lift the percentage from the most recent title,
    # which is the user's freshest measured value.
    import re
    m = re.search(r"(\d{1,3})\s*%", representative.title or "")
    pct_text = f"~{m.group(1)}%" if m else "consistently below target"
    direction = "below"
    if (representative.title or "").lower().startswith("calories over"):
        direction = "above"

    # Replace the title + message in a lightweight clone so we don't
    # mutate the cached/queried Insight row.
    class _Synthesised:
        pass
    syn = _Synthesised()
    syn.title = "Calorie trend"
    syn.message = (
        f"Calories have averaged {pct_text} {direction} target recently. "
        f"This may be contributing to elevated recovery strain."
    )
    syn.module = getattr(representative, "module", "health")
    syn.severity = getattr(representative, "severity", "warning")
    syn.insight_type = getattr(representative, "insight_type", "")

    # Slot the synthesised row where the representative used to be so
    # severity ordering is preserved.
    rep_index = insights.index(representative)
    rebuilt = []
    inserted = False
    for i in insights:
        if i in calorie_rows:
            if not inserted and i is representative:
                rebuilt.append(syn)
                inserted = True
            # All other calorie rows are dropped.
            continue
        rebuilt.append(i)
    # In the unlikely edge case representative wasn't matched in the
    # loop above (e.g., if `insights` is reordered later), append the
    # synthesised row at the beginning.
    if not inserted:
        rebuilt.insert(0, syn)
    return rebuilt


def _augment_attention_with_execution(needs_attention, exec_state):
    """Coherence gate for the "Needs Attention" column.

    The column reads only warning/critical Insights, so it can be empty
    while items are overdue or at-risk RIGHT NOW — which would render the
    contradictory "All clear." beside a "you're slipping" headline. When
    insights are empty but current execution pressure exists, surface ONE
    summarizing concern row so "All clear" can never coexist with real
    behind-the-rhythm work.

    These are CURRENT-state concerns (overdue today / at risk this block),
    not future-risk predictions. If insights already populated the column we
    leave it untouched — no duplication.
    """
    if needs_attention:
        return needs_attention
    _, overdue_count, at_risk_count = _execution_pressure(exec_state)
    if overdue_count > 0:
        overdue = exec_state.get("overdue_actions") or []
        if overdue_count == 1:
            title = f"{overdue[0].get('title')} is past its scheduled time"
        else:
            title = f"{overdue_count} items past their scheduled time today"
        return [{
            "title": title,
            "message": "Still completable — recover before it stacks up.",
            "module": "execution",
            "severity": "warning",
            "insight_type": "execution_overdue",
        }]
    if at_risk_count >= 1:
        plural = "s" if at_risk_count > 1 else ""
        return [{
            "title": f"{at_risk_count} item{plural} at risk in this block",
            "message": "Small actions now keep the day intact.",
            "module": "execution",
            "severity": "warning",
            "insight_type": "execution_at_risk",
        }]
    return needs_attention


# ── Focus Now (selector reuse) ─────────────────────────────────────────


def _collect_focus_now(user, execution_contract=None):
    """Reuse canonical execution selectors. No re-ranking.

    Returns (focus_dict|None, follow_on_list, exec_state_dict) — state is
    returned so downstream callers (biggest_risk, headline) can read from
    the SAME built state instead of building it twice.

    Optional ``execution_contract`` is forwarded into
    ``build_execution_state`` so a v3-dashboard render can share one
    canonical truth fetch across all consumers (Phase 2 dedup).
    """
    from apps.core.execution.execution_state import build_execution_state
    from apps.core.execution.selectors import get_next_action

    state = build_execution_state(user, execution_contract=execution_contract)
    payload = get_next_action(state) or {}
    primary = payload.get("primary_action")

    focus = None
    if primary:
        primary_key = (primary.get("source_type"), primary.get("source_id"))
        focus = {
            "title": primary.get("title"),
            "module": primary.get("source_type"),
            "time_display": primary.get("time_display"),
            "execution_status": primary.get("execution_status"),
            "task_class": primary.get("task_class"),
            "urgency": primary.get("urgency"),
            "reason": _humanize_focus_reason(
                payload.get("reason"), primary,
            ),
            "protects": _derive_protects(primary, primary_key, state),
            "estimated_minutes": _derive_estimated_minutes(primary),
            # Canonical interaction URLs — same source v2 uses. No new
            # write logic — dashboard_v3 is just another surface into
            # the same operating system.
            "toggle_url": primary.get("toggle_url"),
            "detail_url": primary.get("detail_url"),
            # Deterministic "go do it here" deep-link, resolved from
            # canonical metadata (not display text). See
            # apps.core.execution.action_routing.
            "destination_url": _resolve_destination(primary),
            "source": "selector:next_action",
        }

    # Follow-on hints — soft suggestions only, deduped against primary.
    follow_on_pool = (state.get("next_actions") or []) + (state.get("upcoming_actions") or [])
    seen_keys = {(primary.get("source_type"), primary.get("source_id"))} if primary else set()
    follow_on = []
    for a in follow_on_pool:
        key = (a.get("source_type"), a.get("source_id"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        follow_on.append({
            "title": a.get("title"),
            "time_display": a.get("time_display"),
            "module": a.get("source_type"),
        })
        if len(follow_on) >= MAX_FOLLOW_ON:
            break

    return focus, follow_on, state


def _derive_protects(primary, primary_key, state) -> list[str]:
    """What completing the focus action protects downstream — the next 2-3
    items in the same active block. Pure read of canonical eligible_actions.

    Not a guess. If primary is the morning anchor and there are 2 more
    morning items queued, those are LITERALLY what's at risk if primary
    slips. No new logic — just naming the truth already in state.
    """
    eligible = state.get("eligible_actions") or []
    protects = []
    for a in eligible:
        k = (a.get("source_type"), a.get("source_id"))
        if k == primary_key:
            continue
        # Only count things in the SAME active block — that's what's at
        # risk if the anchor slips.
        if a.get("urgency") in ("overdue", "now", "next"):
            protects.append(a.get("title"))
        if len(protects) >= 3:
            break
    return protects


def _resolve_destination(primary) -> str:
    """Canonical 'where does this action happen?' deep-link for the focus item."""
    try:
        from apps.core.execution.action_routing import resolve_action_destination
        return resolve_action_destination(primary)
    except Exception:
        logger.debug("focus destination resolve failed", exc_info=True)
        return "/life/"


def _derive_estimated_minutes(primary) -> int | None:
    """Pull canonical estimated_minutes for the focus item."""
    if primary.get("source_type") != "task":
        return None
    src_id = primary.get("source_id")
    if not src_id:
        return None
    try:
        from apps.life.models import Task
        t = Task.objects.filter(pk=src_id).only("estimated_duration_minutes").first()
        if t and getattr(t, "estimated_duration_minutes", None):
            return t.estimated_duration_minutes
    except Exception:
        return None
    return None


def _humanize_focus_reason(raw_reason, primary) -> str:
    """Replace selector internals ("current", "primary_pool_overdue_or_now")
    with a clean human sentence.

    The locked-facts API uses short technical reason strings for logging;
    those are not display-grade. If the reason is short, technical, or
    contains underscores / equals signs, we synthesize a clean sentence
    from the item's execution_status + urgency.
    """
    if raw_reason and len(raw_reason) > 20 and "_" not in raw_reason and "=" not in raw_reason:
        return raw_reason

    status = (primary or {}).get("execution_status") or ""
    urgency = (primary or {}).get("urgency") or ""
    if urgency == "overdue":
        return "Past its scheduled time — recover this before it stacks up."
    if status == "AT_RISK":
        return "At risk of being missed in this block."
    if status == "LATE_OPEN":
        return "Originally scheduled earlier — still completable today."
    if urgency == "now":
        return "Scheduled for the current block."
    return "Top priority in your current block."


# ── Biggest Risk ───────────────────────────────────────────────────────


def _collect_biggest_risk(user, needs_attention, exec_state=None):
    """Prefer canonical risk selector. Fall back to top critical insight.

    If ``exec_state`` is provided we reuse it instead of building a second
    one (the focus_now path already built one).
    """
    try:
        from apps.core.execution.selectors import get_biggest_risk

        state = exec_state
        if state is None:
            from apps.core.execution.execution_state import build_execution_state
            state = build_execution_state(user)
        payload = get_biggest_risk(state) or {}
        primary = payload.get("primary_action")
        if primary:
            return {
                "title": primary.get("title"),
                "message": payload.get("reason") or "At risk of being missed.",
                "module": primary.get("source_type"),
                "time_display": primary.get("time_display"),
                "source": "selector:biggest_risk",
            }
    except Exception:
        logger.debug("biggest_risk selector failed; falling back to insights",
                     exc_info=True)

    # Fallback — top critical/warning from needs_attention.
    critical = [n for n in needs_attention if n.get("severity") == "critical"]
    pool = critical or needs_attention
    if pool:
        top = pool[0]
        return {
            "title": top["title"],
            "message": top.get("message", ""),
            "module": top.get("module"),
            "source": "insight",
        }
    return None


# ── Biggest Opportunity ────────────────────────────────────────────────


_RISK_TYPE_KEYWORDS = (
    "risk", "overload", "overdue", "miss", "drop", "decline",
    "burnout", "plateau", "stall", "regress",
)
_RISK_OUTLOOK_KEYWORDS = (
    "at risk", "needs attention", "low", "dropping", "decline",
    "off track", "behind",
)


def _is_risk_prediction(p) -> bool:
    """A prediction is forward-RISK (not an opportunity) when its type slug
    or evidence outlook reads as decline/risk.

    Forward risk must never be mislabeled as "Biggest Opportunity" — that is
    the narrative-mismatch that put "overload risk" under the Opportunity
    heading. Risk predictions are future-oriented and belong nowhere near a
    positive slot; they are simply excluded here.
    """
    slug = (getattr(p, "prediction_type", "") or "").lower()
    if any(k in slug for k in _RISK_TYPE_KEYWORDS):
        return True
    ev = getattr(p, "evidence", None) or {}
    outlook = str(ev.get("outlook", "")).lower()
    if any(k in outlook for k in _RISK_OUTLOOK_KEYWORDS):
        return True
    direction = str(ev.get("direction", "")).lower()
    if direction in ("down", "declining", "worsening", "negative"):
        return True
    return False


def _collect_biggest_opportunity(user) -> dict | None:
    """Strongest near-term POSITIVE prediction.

    Forward-risk predictions are filtered out (see ``_is_risk_prediction``)
    so a risk never surfaces under the "Biggest Opportunity" heading. Uses
    ``explanation`` as the visible title (the human-written sentence) and
    falls back to a humanized prediction_type only when no explanation
    exists. Prevents raw type leaks like "Emotional Overload 7D" showing as
    the "Biggest Opportunity" headline.
    """
    from apps.core.ai_predictions.models import Prediction

    pool = (
        Prediction.objects.filter(user=user, status="active")
        .filter(confidence_score__gte=0.6)
        .order_by("-confidence_score", "-created_at")[:10]
    )
    candidate = next((p for p in pool if not _is_risk_prediction(p)), None)
    if not candidate:
        return None

    explanation = (candidate.explanation or "").strip()
    if explanation:
        # First clause becomes the title; the rest is supporting text.
        first_clause = explanation.split(". ")[0].rstrip(".") + "."
        rest = explanation[len(first_clause):].strip()
        title = first_clause
        message = rest or "Trajectory looks favorable."
    else:
        title = _humanize_type(candidate.prediction_type)
        message = "Trajectory looks favorable."

    return {
        "title": title,
        "message": message,
        "module": candidate.module,
        "confidence": round(candidate.confidence_score, 2),
        "source": "prediction",
    }


def _humanize_type(s: str) -> str:
    """Turn a slug like 'weight_30d_trend_down' into a human-readable label."""
    if not s:
        return ""
    words = s.replace("_", " ").split()
    # Capitalize words but preserve numeric/period tokens.
    return " ".join(w if w.isupper() or any(c.isdigit() for c in w) else w.capitalize()
                    for w in words)


# ── Recommendations (PGE) ──────────────────────────────────────────────


def _collect_recommendations(user) -> list[dict[str, Any]]:
    """Top deterministic guidance — small set, priority first."""
    from apps.core.ai_guidance.models import GuidanceItem

    qs = (
        GuidanceItem.objects.filter(user=user, is_active=True)
        .order_by("priority", "-created_at")[:MAX_RECOMMENDATIONS]
    )
    return [
        {
            "title": g.title,
            "message": g.message,
            "priority": g.priority,
            "module": g.module,
            "guidance_type": g.guidance_type,
        }
        for g in qs
    ]


# ── Trajectory ─────────────────────────────────────────────────────────


def _execution_pressure(exec_state):
    """Read CURRENT-state execution pressure from built exec_state.

    Returns (recovery_mode, overdue_count, at_risk_count). These are
    *current* concerns (items overdue today / at risk in this block) — NOT
    future-risk predictions. Used by both the dominant-state selection and
    the headline so they read identical numbers.
    """
    if not exec_state:
        return "", 0, 0
    rs = exec_state.get("recovery_state") or {}
    recovery_mode = (rs.get("mode") or "").upper()
    overdue_count = len(exec_state.get("overdue_actions") or [])
    at_risk_count = len(exec_state.get("at_risk_actions") or [])
    return recovery_mode, overdue_count, at_risk_count


def _derive_overall_state(going_well, needs_attention, biggest_risk, exec_state) -> str:
    """THE dominant-state selection — the single source both the badge and
    the headline derive from. Deterministic, no LLM.

    Folds two signal families into ONE current-state verdict:
      - now-state execution pressure (overdue / at-risk items today)
      - long-window Insight counts (going_well vs needs_attention)

    Execution pressure is *current* and outranks the slower insight trend:
    if real items are overdue right now you are not "steady" no matter how
    the week's insights net out. This is what stops the "STEADY" badge from
    appearing next to a "you're slipping behind" headline.

    Future-oriented risk (overload/burnout predictions) is deliberately NOT
    read here — a forward risk must never override a stable *current* state.

    Returns: improving | steady | slipping | at_risk | mixed | unknown
    """
    recovery_mode, overdue_count, at_risk_count = _execution_pressure(exec_state)

    pos = len(going_well or [])
    neg = len(needs_attention or [])
    has_risk = bool(biggest_risk)

    # Now-state pressure dominates — it is the current reality of the day.
    if recovery_mode in ("RECOVERY", "STABILIZE") or overdue_count >= 3:
        return "at_risk"
    if overdue_count > 0 or at_risk_count >= 2:
        return "slipping"

    # No now-pressure → fall back to the insight-count trend.
    if pos == 0 and neg == 0 and not has_risk:
        return "unknown"
    if pos >= 2 and neg == 0:
        return "improving"
    if pos == 1 and neg == 0:
        return "steady"           # one win is not a trend
    if neg > 0 and pos == 0:
        return "slipping"
    if has_risk and neg >= pos:
        return "slipping"
    if pos >= max(neg, 1) * 2:
        return "improving"
    if pos == neg:
        return "steady"
    return "mixed"


def _derive_headline(
    overall_state, going_well, needs_attention, exec_state, focus_now,
    user_now=None,
) -> str:
    """One-sentence opener, chosen WITHIN the dominant state.

    The headline may pick more specific wording inside a state, but it can
    NEVER select a sentence that contradicts the state. ``overall_state`` is
    the same verdict the badge shows, so badge and headline always agree.

    No free-text generation, no LLM — each branch is a pre-written sentence.

    Phase A trust fix: time-aware wording. ``user_now`` is the user's
    local-time datetime; when omitted, defaults to "midday" framing,
    preserving back-compat for any caller that has not been updated.
    """
    recovery_mode, overdue_count, at_risk_count = _execution_pressure(exec_state)
    neg = len(needs_attention or [])
    band = _time_band(user_now)

    if overall_state == "at_risk":
        # Recovery-mode special branches still take precedence — they
        # encode a different conversation (deliberate recovery state)
        # rather than a generic at-risk render.
        if recovery_mode in ("RECOVERY", "STABILIZE"):
            if focus_now:
                return "Today's drifted — let's recover the next step and rebuild momentum."
            return "Today's behind schedule. Reset with one small action."
        # All other at_risk renders flow through the time-aware matrix.
        return _HEADLINE_MATRIX["at_risk"][band]

    if overall_state == "slipping":
        # Insight-name personalisation is preserved where useful.
        if neg > 0 and band in ("morning", "midday"):
            return (
                f"A few things are slipping — "
                f"{needs_attention[0]['title'].lower()} needs attention first."
            )
        return _HEADLINE_MATRIX["slipping"][band]

    if overall_state == "improving":
        return _HEADLINE_MATRIX["improving"][band]

    if overall_state == "mixed":
        return _HEADLINE_MATRIX["mixed"][band]

    if overall_state == "steady":
        return _HEADLINE_MATRIX["steady"][band]

    # Unknown / no signal.
    return _HEADLINE_MATRIX["unknown"][band]
