"""Executive Briefing Phase A trust fix tests.

Covers three discrete changes shipped together in this PR:

  A1 — Time-aware headline matrix. The "let's protect the rest of the
       day" framing was firing at 8 AM. Headlines now branch on a
       small time-band classifier (early_morning / morning / midday /
       evening / late_evening) so the wording reflects the user's
       actual clock position.

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
    _HEADLINE_MATRIX,
    _time_band,
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


# ── A1: time-aware headline ───────────────────────────────────────

class TimeBandClassifierTests(TestCase):
    """The _time_band helper classifies a tz-aware datetime into a
    small fixed band. Boundaries matter — they show up in the headline
    matrix lookup."""

    def test_early_morning_band_4_to_10(self):
        for h in (4, 5, 7, 8, 9):
            self.assertEqual(_time_band(_at(h)), "early_morning")

    def test_morning_band_10_to_12(self):
        for h in (10, 11):
            self.assertEqual(_time_band(_at(h)), "morning")

    def test_midday_band_12_to_17(self):
        for h in (12, 13, 14, 15, 16):
            self.assertEqual(_time_band(_at(h)), "midday")

    def test_evening_band_17_to_21(self):
        for h in (17, 18, 19, 20):
            self.assertEqual(_time_band(_at(h)), "evening")

    def test_late_evening_band_21_to_4(self):
        for h in (21, 22, 23, 0, 1, 2, 3):
            self.assertEqual(_time_band(_at(h)), "late_evening")

    def test_none_falls_back_to_midday(self):
        self.assertEqual(_time_band(None), "midday")


class HeadlineMatrixTests(TestCase):
    """The headline matrix has all 5 bands × 6 states; every cell is
    a non-empty string. Spot-checks per the user-spec verbatim copy."""

    def test_matrix_complete(self):
        expected_bands = {"early_morning", "morning", "midday",
                          "evening", "late_evening"}
        expected_states = {"at_risk", "slipping", "improving",
                           "mixed", "steady", "unknown"}
        self.assertEqual(set(_HEADLINE_MATRIX.keys()), expected_states)
        for state, by_band in _HEADLINE_MATRIX.items():
            self.assertEqual(
                set(by_band.keys()), expected_bands,
                f"state {state} missing band coverage: "
                f"{set(by_band.keys())}",
            )
            for band, text in by_band.items():
                self.assertTrue(
                    text and isinstance(text, str),
                    f"empty headline at {state}/{band}",
                )

    def test_at_risk_morning_uses_recoverable_framing(self):
        """The headline production bug: 8 AM should NOT say 'protect
        the rest of the day'. Must lean toward recoverable/reset/
        momentum vocabulary."""
        text = _HEADLINE_MATRIX["at_risk"]["early_morning"].lower()
        self.assertTrue(
            any(k in text for k in ("recover", "reset", "momentum",
                                     "rebuild")),
            f"early_morning at_risk wording must reinforce "
            f"recover/reset/momentum: {text}",
        )
        self.assertNotIn(
            "protect the rest of the day", text,
            "early_morning at_risk must NOT use protect-the-day "
            "damage-control framing",
        )


class DeriveHeadlineTimeAwarenessTests(TestCase):
    """End-to-end: _derive_headline picks the correct cell from the
    matrix given an overall_state + user_now."""

    def _at_risk_state(self):
        """Minimal exec_state shape that triggers the at_risk path
        without entering RECOVERY mode."""
        return {
            "recovery_mode": None,
            "overdue_actions": [
                {"title": "a"}, {"title": "b"}, {"title": "c"},
                {"title": "d"},
            ],
            "at_risk_actions": [],
        }

    def test_at_risk_at_eight_am_uses_morning_framing(self):
        """The headline production trust break — 8:07 AM with overdue
        items must NOT render the 'protect the rest of the day' line."""
        text = _derive_headline(
            overall_state="at_risk",
            going_well=[],
            needs_attention=[],
            exec_state=self._at_risk_state(),
            focus_now={"title": "x"},
            user_now=_at(8),
        )
        self.assertNotIn("protect the rest of the day", text)
        text_lower = text.lower()
        self.assertTrue(
            any(k in text_lower for k in ("recover", "reset",
                                           "momentum", "rebuild")),
            f"morning at_risk wording must reinforce recovery, got: {text}",
        )

    def test_at_risk_at_two_pm_uses_midday_framing(self):
        text = _derive_headline(
            overall_state="at_risk",
            going_well=[],
            needs_attention=[],
            exec_state=self._at_risk_state(),
            focus_now={"title": "x"},
            user_now=_at(14),
        )
        self.assertEqual(text, _HEADLINE_MATRIX["at_risk"]["midday"])

    def test_at_risk_at_seven_pm_uses_evening_framing(self):
        text = _derive_headline(
            overall_state="at_risk",
            going_well=[],
            needs_attention=[],
            exec_state=self._at_risk_state(),
            focus_now={"title": "x"},
            user_now=_at(19),
        )
        self.assertEqual(text, _HEADLINE_MATRIX["at_risk"]["evening"])

    def test_back_compat_no_user_now_uses_midday_default(self):
        """Existing callers that haven't been updated still work and
        get the previous-equivalent midday wording."""
        text = _derive_headline(
            overall_state="at_risk",
            going_well=[],
            needs_attention=[],
            exec_state=self._at_risk_state(),
            focus_now={"title": "x"},
        )
        self.assertEqual(text, _HEADLINE_MATRIX["at_risk"]["midday"])

    def test_recovery_mode_special_branch_preserved(self):
        """The RECOVERY/STABILIZE special branches were existing
        deterministic responses with their own narrative. They must
        still take precedence over the time-aware matrix."""
        state = self._at_risk_state()
        state["recovery_mode"] = "RECOVERY"
        text = _derive_headline(
            overall_state="at_risk",
            going_well=[],
            needs_attention=[],
            exec_state=state,
            focus_now={"title": "x"},
            user_now=_at(8),
        )
        self.assertIn("recover", text.lower())


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
        msg = (syn["message"] or "").lower()
        self.assertIn("average", msg)
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
