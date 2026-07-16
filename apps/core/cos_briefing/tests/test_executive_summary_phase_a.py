"""Executive Briefing Phase A trust fix tests.

Covers three discrete changes shipped together in this PR:

  A1 — Execution-phase-grounded headline (redesigned 2026-07-16). The headline
       is grounded in the deterministic DAY EXECUTION PHASE
       (build_execution_state["execution_phase"]) — never inferred from the clock
       or the weekly trend. Fixes the "Slow start" fabrication at 4:56 AM before
       the day had begun. (Superseded the old clock×trend headline matrix.)

  A2 — Dedupe by title in `_collect_needs_attention`. Insight rows
       with identical titles but different dedupe_keys (e.g. two
       "Overtraining Risk" rows on consecutive days) are collapsed to
       the most-recent occurrence in the presentation layer. DB rows
       are untouched.

  A3 — Calorie synthesis. Multiple "Calories under target by N%" rows
       collapse into one executive-level signal:
       "Calories have averaged ~30% below target recently. This may
       be contributing to elevated recovery strain."

Phase B (risk-aware action reconciliation, recoverability flags) is
explicitly NOT in this PR.
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_insights.models import Insight
from apps.core.cos_briefing.executive_summary import (
    _collect_needs_attention,
    _derive_headline,
    _fallback_headline,
    _headline_for_phase,
)
from apps.users.models import TermsAcceptance


User = get_user_model()


def _make_user(email="exec-briefing-trust@test.com"):
    u = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=u,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _at(hour: int):
    """Build a tz-aware datetime at the given hour (today) for headline
    tests. The actual date doesn't matter — only the .hour attribute."""
    base = timezone.now()
    return base.replace(hour=hour, minute=0, second=0, microsecond=0)


def _make_insight(user, *, title, severity="warning",
                  insight_type="generic", module="health",
                  created_offset_minutes=0, dedupe_key=None):
    """Create an Insight row with controlled created_at ordering."""
    from apps.core.ai_insights.models import build_dedupe_key
    if dedupe_key is None:
        dedupe_key = build_dedupe_key(
            user.id, insight_type, "w-start", "w-end", [str(created_offset_minutes)],
        )
    row = Insight.objects.create(
        user=user, module=module, insight_type=insight_type,
        severity=severity, title=title, message=f"msg: {title}",
        confidence_score=0.9, explain_why="test", evidence={},
        status="new", dedupe_key=dedupe_key,
    )
    # Allow controlled created_at so dedupe-by-title can be tested with a
    # known "most recent" winner.
    if created_offset_minutes:
        Insight.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(minutes=created_offset_minutes),
        )
        row.refresh_from_db()
    return row


# ── A1: execution-phase-grounded headline ─────────────────────────
#
# The headline no longer keys on a clock×weekly-trend matrix. It is grounded in
# the deterministic DAY EXECUTION PHASE (build_execution_state["execution_phase"]).
# It may only describe today's execution from that fact — never from the clock or
# the weekly trend. (Incident 2026-07-16: "Slow start" at 4:56 AM before the day
# had begun.)

# Words that assert a within-day trajectory — forbidden unless execution truth proves it.
_FABRICATION_PHRASES = (
    "slow start", "behind this morning", "reset your trajectory",
    "resets the trajectory", "you're falling behind", "falling behind",
    "you're behind", "time to recover",
)


def _phase_state(phase, **facts):
    """Minimal exec_state carrying an ``execution_phase`` facts dict."""
    pf = {
        "phase": phase,
        "overdue_count": facts.get("overdue_count", 0),
        "first_commitment": facts.get("first_commitment"),
        "minutes_until_first_commitment": facts.get("minutes_until_first_commitment"),
    }
    return {"execution_phase": pf}


class BeforeFirstCommitmentHeadlineTests(TestCase):
    """The reported 4:56 AM case: before the first commitment, the headline states
    the day is beginning — it never fabricates a 'slow start' / trajectory claim."""

    def test_before_first_says_day_is_beginning_with_minutes(self):
        state = _phase_state(
            "before_first_commitment",
            first_commitment={"title": "Prayer Time", "time": "5:30 AM",
                              "minutes_until": 34},
            minutes_until_first_commitment=34,
        )
        text = _derive_headline("slipping", [], [], state, focus_now=None)
        self.assertIn("just beginning", text.lower())
        self.assertIn("34 minute", text.lower())
        self.assertIn("Prayer Time", text)

    def test_before_first_never_fabricates_trajectory(self):
        """Even when the weekly trend passed in is 'slipping', the before-first
        headline must contain none of the fabricated within-day trajectory words."""
        state = _phase_state(
            "before_first_commitment",
            first_commitment={"title": "Prayer Time", "time": "5:30 AM",
                              "minutes_until": 34},
            minutes_until_first_commitment=34,
        )
        for trend in ("slipping", "at_risk", "improving", "steady", "unknown"):
            text = _derive_headline(trend, [], [], state, focus_now=None).lower()
            for bad in _FABRICATION_PHRASES:
                self.assertNotIn(
                    bad, text, f"trend={trend} leaked fabricated phrase {bad!r}: {text!r}",
                )

    def test_clean_slate_when_no_first_commitment(self):
        state = _phase_state("before_first_commitment")
        text = _derive_headline("unknown", [], [], state, focus_now=None)
        self.assertIn("clean slate", text.lower())

    def test_far_off_first_commitment_uses_clock_time_not_minutes(self):
        state = _phase_state(
            "before_first_commitment",
            first_commitment={"title": "Team standup", "time": "9:00 AM",
                              "minutes_until": 214},
            minutes_until_first_commitment=214,
        )
        text = _derive_headline("unknown", [], [], state, focus_now=None)
        self.assertIn("9:00 AM", text)
        self.assertNotIn("214", text)


class ExecutionPhaseHeadlineTests(TestCase):
    """Each phase produces its own grounded, non-shaming opener."""

    def test_behind_states_overdue_and_recovery_path(self):
        state = _phase_state("behind", overdue_count=2)
        text = _derive_headline("steady", [], [], state, focus_now=None).lower()
        self.assertIn("drifted", text)
        self.assertIn("2 commitments are past due", text)
        self.assertIn("back on track", text)

    def test_behind_singular_grammar(self):
        state = _phase_state("behind", overdue_count=1)
        text = _derive_headline("steady", [], [], state, focus_now=None).lower()
        self.assertIn("one commitment is past due", text)

    def test_underway(self):
        text = _derive_headline("steady", [], [], _phase_state("underway"), None)
        self.assertIn("underway", text.lower())

    def test_ahead(self):
        text = _derive_headline("improving", [], [], _phase_state("ahead"), None)
        self.assertIn("ahead of schedule", text.lower())

    def test_winding_down(self):
        text = _derive_headline("steady", [], [], _phase_state("winding_down"), None)
        self.assertIn("winding down", text.lower())

    def test_day_complete(self):
        text = _derive_headline("improving", [], [], _phase_state("day_complete"), None)
        self.assertIn("complete", text.lower())

    def test_headline_for_phase_returns_none_for_unknown(self):
        self.assertIsNone(_headline_for_phase("unknown", {}, None))


class FallbackHeadlineTests(TestCase):
    """When execution truth is unavailable, the fallback is trend-scoped and never
    asserts a within-day trajectory."""

    def test_no_execution_phase_uses_fallback(self):
        # exec_state without an execution_phase key → degraded fallback.
        text = _derive_headline("improving", [], [], {}, focus_now=None)
        self.assertEqual(text, _fallback_headline("improving"))

    def test_fallback_never_fabricates_today(self):
        for trend in ("improving", "steady", "unknown"):
            text = _fallback_headline(trend).lower()
            for bad in _FABRICATION_PHRASES:
                self.assertNotIn(bad, text)


# ── A2: dedupe by title ────────────────────────────────────────────

class DedupeByTitleTests(TestCase):
    """Same-title Insight rows (different dedupe_keys) collapse to the
    most-recent row in the presentation layer. DB is untouched."""

    def setUp(self):
        self.user = _make_user("dedup@test.com")

    def test_two_overtraining_risk_rows_collapse_to_one(self):
        # Day 1 (older) — different dedupe_key than Day 2.
        _make_insight(
            self.user, title="Overtraining Risk",
            insight_type="overtraining_risk",
            created_offset_minutes=60 * 24,  # 1 day ago
            dedupe_key="ovr-day1",
        )
        # Day 2 (newer) — winner.
        _make_insight(
            self.user, title="Overtraining Risk",
            insight_type="overtraining_risk",
            created_offset_minutes=10,
            dedupe_key="ovr-day2",
        )
        out = _collect_needs_attention(self.user)
        overtraining_rows = [r for r in out if r["title"] == "Overtraining Risk"]
        self.assertEqual(
            len(overtraining_rows), 1,
            f"two identical-title rows must collapse to one. got: {out}",
        )

    def test_distinct_titles_remain_separate(self):
        _make_insight(
            self.user, title="Overtraining Risk",
            insight_type="overtraining_risk",
        )
        _make_insight(
            self.user, title="Poor sleep",
            insight_type="sleep_low_avg",
        )
        out = _collect_needs_attention(self.user)
        titles = [r["title"] for r in out]
        self.assertIn("Overtraining Risk", titles)
        self.assertIn("Poor sleep", titles)

    def test_db_rows_untouched_after_render_dedupe(self):
        _make_insight(
            self.user, title="Overtraining Risk",
            insight_type="overtraining_risk",
            dedupe_key="ovr-1",
        )
        _make_insight(
            self.user, title="Overtraining Risk",
            insight_type="overtraining_risk",
            dedupe_key="ovr-2",
        )
        _collect_needs_attention(self.user)
        # The presentation collapse must not delete or dismiss rows.
        self.assertEqual(
            Insight.objects.filter(
                user=self.user, title="Overtraining Risk", status="new",
            ).count(),
            2,
            "render-time dedupe must NOT mutate the DB",
        )


# ── A3: calorie synthesis ─────────────────────────────────────────

class CalorieSynthesisTests(TestCase):
    """Three calorie alerts ("by 30%" / "by 27%" / "by 35%") collapse
    to one executive-level message."""

    def setUp(self):
        self.user = _make_user("calsyn@test.com")

    def test_three_calorie_rows_collapse_to_one(self):
        # Day 1 (oldest)
        _make_insight(
            self.user, title="Calories under target by 35%",
            insight_type="nutrition_calorie_trend",
            created_offset_minutes=60 * 24 * 2,
            dedupe_key="cal-d-3",
        )
        # Day 2 (middle)
        _make_insight(
            self.user, title="Calories under target by 27%",
            insight_type="nutrition_calorie_trend",
            created_offset_minutes=60 * 24,
            dedupe_key="cal-d-2",
        )
        # Day 3 (most recent — winner)
        _make_insight(
            self.user, title="Calories under target by 30%",
            insight_type="nutrition_calorie_trend",
            created_offset_minutes=10,
            dedupe_key="cal-d-1",
        )
        out = _collect_needs_attention(self.user)
        calorie_rows = [
            r for r in out
            if "calorie" in (r.get("title", "") or "").lower()
        ]
        self.assertEqual(
            len(calorie_rows), 1,
            f"three calorie alerts must collapse to one synthesised row. "
            f"got: {out}",
        )
        syn = calorie_rows[0]
        # General consolidation: subject + range + average + span — not the
        # per-day snapshots, and not a metric-specific special case.
        self.assertTrue(syn["title"].lower().startswith("calories under target"))
        self.assertIn("27", syn["title"])   # low of range
        self.assertIn("35", syn["title"])   # high of range
        self.assertIn("avg", syn["title"].lower())   # average captured (in the title)
        # The customer-facing MESSAGE is natural language ONLY — no raw stats, and NEVER
        # the internal aggregation artifact ("Consolidated from N readings into one concern").
        msg = (syn["message"] or "").lower()
        self.assertIn("across the last", msg)
        self.assertNotIn("consolidated from", msg)
        self.assertNotIn("average", msg)
        # No single raw daily title leaks into the executive row.
        self.assertNotIn("by 30%", syn["title"])

    def test_single_calorie_row_passes_through(self):
        _make_insight(
            self.user, title="Calories under target by 30%",
            insight_type="nutrition_calorie_trend",
            dedupe_key="cal-only",
        )
        out = _collect_needs_attention(self.user)
        calorie_rows = [
            r for r in out
            if "calorie" in (r.get("title", "") or "").lower()
        ]
        self.assertEqual(len(calorie_rows), 1)
        # A single row must NOT be rewritten — preserves the original
        # title so the user still sees their precise measurement.
        self.assertEqual(
            calorie_rows[0]["title"], "Calories under target by 30%",
        )

    def test_calorie_synthesis_preserves_other_insights(self):
        _make_insight(
            self.user, title="Overtraining Risk",
            insight_type="overtraining_risk",
        )
        _make_insight(
            self.user, title="Calories under target by 30%",
            insight_type="nutrition_calorie_trend",
            dedupe_key="cal-x",
        )
        _make_insight(
            self.user, title="Calories under target by 27%",
            insight_type="nutrition_calorie_trend",
            dedupe_key="cal-y",
        )
        out = _collect_needs_attention(self.user)
        titles = [r["title"] for r in out]
        self.assertIn("Overtraining Risk", titles)
        # Two calorie rows consolidated into ONE "Calories under target — …" row.
        cal = [t for t in titles if t.lower().startswith("calories under target")]
        self.assertEqual(len(cal), 1)
        # No raw daily calorie title leaked through.
        self.assertNotIn("Calories under target by 30%", titles)
        self.assertNotIn("Calories under target by 27%", titles)


# ── A3 (general): the reported protein case ───────────────────────

class ProteinConsolidationTests(TestCase):
    """Four "Protein intake N% of target" rows across four days collapse to ONE
    executive item (range + average + span) — the reported dashboard bug."""

    def setUp(self):
        self.user = _make_user("protein@test.com")

    def test_four_protein_rows_collapse_to_one_executive_item(self):
        for pct, off in [(80, 10), (72, 60 * 24), (55, 60 * 24 * 2), (53, 60 * 24 * 3)]:
            _make_insight(
                self.user, title=f"Protein intake {pct}% of target",
                insight_type="protein_intake", module="health",
                created_offset_minutes=off, dedupe_key=f"protein-{pct}",
            )
        out = _collect_needs_attention(self.user)
        protein = [r for r in out if "protein" in (r.get("title", "") or "").lower()]
        self.assertEqual(len(protein), 1, f"four protein rows must collapse. got: {out}")
        title = protein[0]["title"]
        self.assertIn("Protein intake", title)
        self.assertIn("below target", title.lower())  # derived direction
        self.assertIn("53", title)                     # range low
        self.assertIn("80", title)                     # range high
        self.assertIn("65", title)                     # average
        # No raw per-day protein bullet survives.
        for pct in (53, 55, 72, 80):
            self.assertNotIn(f"Protein intake {pct}% of target", [r["title"] for r in out])

    def test_distinct_subjects_are_not_merged(self):
        _make_insight(self.user, title="Protein intake 55% of target",
                      insight_type="protein_intake", dedupe_key="p1")
        _make_insight(self.user, title="Protein intake 72% of target",
                      insight_type="protein_intake", dedupe_key="p2")
        _make_insight(self.user, title="Sleep 62% of target",
                      insight_type="sleep_low", dedupe_key="s1")
        out = _collect_needs_attention(self.user)
        titles = " | ".join(r["title"] for r in out)
        # Protein consolidated; the lone Sleep row is untouched (different subject).
        self.assertIn("Protein intake", titles)
        self.assertIn("Sleep 62% of target", titles)


# ── Combined sanity ───────────────────────────────────────────────

class EndToEndShapeContractTests(TestCase):
    """The Phase A changes are render-only. The returned shape of
    `_collect_needs_attention` must remain the same dict per item."""

    def setUp(self):
        self.user = _make_user("shape@test.com")

    def test_returned_items_carry_expected_keys(self):
        _make_insight(self.user, title="Overtraining Risk",
                      insight_type="overtraining_risk")
        out = _collect_needs_attention(self.user)
        self.assertGreaterEqual(len(out), 1)
        row = out[0]
        for key in ("title", "message", "module", "severity",
                    "insight_type"):
            self.assertIn(key, row)
