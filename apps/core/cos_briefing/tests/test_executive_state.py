"""State-based executive reasoning adapter (state-adapter sprint, 2026-06-18).

Proves Beth reasons from STANDING STATE, not only transient events:
 1. positive standing state appears even when positive Insights are >7 days old
 2. weight loss surfaces as a biggest win
 3. glucose improvement surfaces as an improvement
 4. sleep decline surfaces as a decline
 5. sleep does not hide weight/glucose wins (anti-fixation)
 6. going_well is not empty when meaningful positive standing state exists
 7. thin-data degrades honestly (no fabricated wins)
 8. existing event-based Insights still work
 9. executive outputs are deterministic
"""
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.cos_briefing import executive_state as es_adapter
from apps.core.cos_briefing import executive_summary as es
from apps.core.cos_briefing.executive_state import ExecutiveStateSignal

User = get_user_model()


def _sig(domain, lens, direction, conf="high", title=None, mag=None,
         leverage=False):
    return ExecutiveStateSignal(
        domain=domain, lens=lens, direction=direction, magnitude=mag,
        confidence=conf, title=title or f"{domain} {lens}",
        message=f"{domain} {lens} msg", evidence=[f"{domain} evidence"],
        source=f"{domain}_state", leverage=leverage)


# ── Pure selection logic (no DB) ────────────────────────────────────────

class StateLensSelection(SimpleTestCase):
    def test_win_improvement_decline_are_distinct_domains(self):
        sigs = [
            _sig("weight", "win", "improving"),
            _sig("glucose", "improvement", "improving"),
            _sig("sleep", "decline", "declining"),
        ]
        L = es_adapter.select_executive_lenses(sigs)
        self.assertEqual(L["biggest_win"].domain, "weight")
        self.assertEqual(L["biggest_improvement"].domain, "glucose")
        self.assertEqual(L["biggest_decline"].domain, "sleep")
        # Three lenses → three different domains.
        self.assertEqual(
            len({L["biggest_win"].domain, L["biggest_improvement"].domain,
                 L["biggest_decline"].domain}), 3)

    def test_anti_fixation_sleep_does_not_fill_every_slot(self):
        # Sleep is the strongest declining signal; it must NOT also take the win
        # slot, and the real weight win must surface.
        sigs = [
            _sig("sleep", "decline", "declining"),
            _sig("sleep", "risk", "risk"),          # same domain, still sleep
            _sig("weight", "win", "improving"),
        ]
        L = es_adapter.select_executive_lenses(sigs)
        self.assertEqual(L["biggest_win"].domain, "weight")     # win not hidden
        self.assertEqual(L["biggest_decline"].domain, "sleep")
        self.assertNotEqual(L["biggest_win"].domain, L["biggest_decline"].domain)

    def test_thin_data_does_not_fabricate(self):
        # Only one signal → win is set, improvement/decline/opportunity empty.
        sigs = [_sig("weight", "win", "improving")]
        L = es_adapter.select_executive_lenses(sigs)
        self.assertEqual(L["biggest_win"].domain, "weight")
        self.assertIsNone(L["biggest_improvement"])   # no fabricated 2nd win
        self.assertIsNone(L["biggest_decline"])       # no fabricated decline
        self.assertIsNone(L["biggest_opportunity"])   # no leverage signal

    def test_no_signals_all_none(self):
        L = es_adapter.select_executive_lenses([])
        self.assertTrue(all(v is None for v in L.values()))

    def test_opportunity_is_the_leverage_constraint(self):
        # Opportunity = top declining LEVERAGE signal; may share Decline's
        # domain (sleep is both the decline and the highest-leverage fix).
        sigs = [
            _sig("weight", "win", "improving"),
            _sig("sleep", "decline", "declining", leverage=True),
            _sig("relationships", "decline", "declining"),  # not leverage
        ]
        L = es_adapter.select_executive_lenses(sigs)
        self.assertEqual(L["biggest_opportunity"].domain, "sleep")
        self.assertEqual(L["biggest_decline"].domain, "sleep")   # overlap allowed

    def test_deterministic(self):
        sigs = [
            _sig("weight", "win", "improving"),
            _sig("medication", "win", "improving"),
            _sig("sleep", "decline", "declining"),
        ]
        a = es_adapter.select_executive_lenses(list(sigs))
        b = es_adapter.select_executive_lenses(list(sigs))
        self.assertEqual({k: (v.domain if v else None) for k, v in a.items()},
                         {k: (v.domain if v else None) for k, v in b.items()})


class GoingWellMerge(SimpleTestCase):
    def test_standing_win_appears_when_insight_list_empty(self):
        merged = es._merge_standing_wins([], [_sig("weight", "win", "improving",
                                                   title="Weight down 14.1 lb")])
        self.assertTrue(any("Weight down" in g["title"] for g in merged))
        self.assertEqual(merged[0]["insight_type"], "standing_state")

    def test_dedupes_by_title(self):
        gw = [{"title": "Weight down 14.1 lb", "message": "x", "module": "weight",
               "insight_type": "weight_trend_down"}]
        merged = es._merge_standing_wins(
            gw, [_sig("weight", "win", "improving", title="Weight down 14.1 lb")])
        self.assertEqual(len(merged), 1)   # not duplicated

    def test_caps_at_max(self):
        wins = [_sig(f"d{i}", "win", "improving", title=f"win {i}")
                for i in range(10)]
        merged = es._merge_standing_wins([], wins)
        self.assertLessEqual(len(merged), es.MAX_GOING_WELL)

    def test_no_wins_returns_unchanged(self):
        gw = [{"title": "x", "message": "y", "module": "m", "insight_type": "t"}]
        self.assertEqual(es._merge_standing_wins(gw, [
            _sig("sleep", "decline", "declining")]), gw)


class SleepSignalBuilder(SimpleTestCase):
    def test_declining_sleep_is_a_decline(self):
        out = es_adapter._sleep_signals(
            {"sleep_trend": "decreasing", "sleep_consistency_score": 43,
             "sleep_avg_hours_7d": 6.7})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].direction, "declining")
        self.assertIn("6.7", out[0].message)
        self.assertIn("43", out[0].message)

    def test_improving_sleep_is_improvement(self):
        out = es_adapter._sleep_signals(
            {"sleep_trend": "increasing", "sleep_avg_hours_7d": 7.8})
        self.assertEqual(out[0].direction, "improving")

    def test_no_sleep_state_is_empty(self):
        self.assertEqual(es_adapter._sleep_signals({}), [])


# ── Grounded builders (DB + targeted mocks) ─────────────────────────────

def _user(email):
    u = User.objects.create_user(email=email, password="x" * 20)
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class WeightWinFromState(TestCase):
    def setUp(self):
        self.user = _user("ewin@test.com")

    def _weigh(self, value, days_ago):
        from apps.health.models import WeightEntry
        WeightEntry.objects.create(
            user=self.user, value=value, unit="lb",
            recorded_at=timezone.now() - timedelta(days=days_ago))

    def test_weight_loss_surfaces_as_win(self):
        self._weigh(312, 80)
        self._weigh(298, 1)
        out = es_adapter._weight_signals(self.user, {})
        self.assertEqual(len(out), 1)
        s = out[0]
        self.assertEqual(s.domain, "weight")
        self.assertEqual(s.lens, "win")
        self.assertEqual(s.direction, "improving")
        self.assertAlmostEqual(s.magnitude, 14.0, delta=0.5)
        self.assertIn("Weight down", s.title)

    def test_weight_gain_surfaces_as_decline(self):
        self._weigh(290, 80)
        self._weigh(300, 1)
        out = es_adapter._weight_signals(self.user, {})
        self.assertEqual(out[0].direction, "declining")


class GlucoseSignalGrounding(SimpleTestCase):
    def test_glucose_improving_is_improvement(self):
        with patch("apps.health.services.glucose_snapshot.build_glucose_summary",
                   return_value={"trend_7d_vs_30d": "improving", "average_7d": 120,
                                 "average_30d": 138, "projected_a1c": 6.2,
                                 "projected_a1c_confidence": "high"}):
            out = es_adapter._glucose_signals(object())
        self.assertEqual(out[0].lens, "improvement")
        self.assertEqual(out[0].direction, "improving")
        self.assertIn("120", out[0].message)

    def test_glucose_no_trend_is_omitted_not_fabricated(self):
        with patch("apps.health.services.glucose_snapshot.build_glucose_summary",
                   return_value={"trend_7d_vs_30d": "", "average_7d": None,
                                 "average_30d": None}):
            out = es_adapter._glucose_signals(object())
        self.assertEqual(out, [])   # honest omission

    def test_glucose_no_data_is_omitted(self):
        with patch("apps.health.services.glucose_snapshot.build_glucose_summary",
                   return_value=None):
            self.assertEqual(es_adapter._glucose_signals(object()), [])


# ── Executive summary integration ───────────────────────────────────────

class ExecutiveSummaryIntegration(TestCase):
    def setUp(self):
        self.user = _user("eint@test.com")

    def _insight(self, title, severity="positive", age_days=0, status="new"):
        from apps.core.ai_insights.models import Insight
        i = Insight.objects.create(
            user=self.user, module="health", insight_type="t", severity=severity,
            title=title, message="m", explain_why="w", dedupe_key=title,
            status=status)
        if age_days:
            Insight.objects.filter(pk=i.pk).update(
                created_at=timezone.now() - timedelta(days=age_days))
        return i

    def test_standing_win_visible_even_when_positive_insight_is_old(self):
        # Positive insight 30 days old → event path returns nothing, but the
        # standing win must still surface (the core fix).
        self._insight("Old win", age_days=30)
        with patch.object(es, "_collect_state_signals",
                          return_value=[_sig("weight", "win", "improving",
                                             title="Weight down 14.1 lb")]):
            out = es.build_executive_summary(self.user)
        titles = [g["title"] for g in out["going_well"]]
        self.assertIn("Weight down 14.1 lb", titles)
        self.assertNotIn("Old win", titles)               # aged out (event)
        self.assertIsNotNone(out["biggest_win"])
        self.assertEqual(out["biggest_win"]["domain"], "weight")

    def test_going_well_not_empty_with_standing_state(self):
        with patch.object(es, "_collect_state_signals",
                          return_value=[_sig("faith", "win", "improving",
                                             title="15-day reading streak")]):
            out = es.build_executive_summary(self.user)
        self.assertTrue(len(out["going_well"]) >= 1)

    def test_existing_fresh_insight_still_works(self):
        # Event pipeline intact: a fresh positive insight still appears.
        self._insight("Fresh win", age_days=0)
        with patch.object(es, "_collect_state_signals", return_value=[]):
            out = es.build_executive_summary(self.user)
        self.assertIn("Fresh win", [g["title"] for g in out["going_well"]])

    def test_sleep_decline_does_not_hide_weight_win(self):
        with patch.object(es, "_collect_state_signals", return_value=[
                _sig("weight", "win", "improving", title="Weight down 14.1 lb"),
                _sig("sleep", "decline", "declining",
                     title="Sleep consistency slipping")]):
            out = es.build_executive_summary(self.user)
        self.assertEqual(out["biggest_win"]["domain"], "weight")
        self.assertEqual(out["biggest_decline"]["domain"], "sleep")
        self.assertIn("Weight down 14.1 lb",
                      [g["title"] for g in out["going_well"]])

    def test_thin_data_degrades_without_fabrication(self):
        with patch.object(es, "_collect_state_signals", return_value=[
                _sig("weight", "win", "improving", title="Weight down 14.1 lb")]):
            out = es.build_executive_summary(self.user)
        self.assertIsNotNone(out["biggest_win"])
        self.assertIsNone(out["biggest_improvement"])
        self.assertIsNone(out["biggest_decline"])

    def test_deterministic_outputs(self):
        sigs = [_sig("weight", "win", "improving"),
                _sig("sleep", "decline", "declining")]
        with patch.object(es, "_collect_state_signals", return_value=sigs):
            a = es.build_executive_summary(self.user)
        with patch.object(es, "_collect_state_signals", return_value=sigs):
            b = es.build_executive_summary(self.user)
        for k in ("biggest_win", "biggest_decline", "most_important_trend"):
            self.assertEqual(
                (a[k] or {}).get("domain"), (b[k] or {}).get("domain"))


class FullBoardSteadyState(TestCase):
    """Every canonical domain reports a STATUS every cycle, even when quiet —
    and context/steady signals never leak into the win/decline lenses."""

    def setUp(self):
        self.user = _user("fullboard@test.com")  # minimal data → mostly unknown

    def test_every_domain_emits_a_status(self):
        sigs = es_adapter.build_executive_state_signals(self.user)
        domains = {s.domain for s in sigs}
        for d in es_adapter._FULL_BOARD:
            self.assertIn(d, domains, f"{d} missing from the board")

    def test_every_signal_has_status_polarity_consider(self):
        sigs = es_adapter.build_executive_state_signals(self.user)
        allowed = {"strong", "improving", "stable", "declining", "neglected",
                   "unknown"}
        for s in sigs:
            self.assertIn(s.status, allowed, f"{s.domain}:{s.status}")
            self.assertIn(s.polarity,
                          {"positive", "neutral", "negative", "unknown"})
            self.assertIn(s.consider_for,
                          {"risk", "opportunity", "progress", "context"})

    def test_quiet_domains_are_unknown_not_absent(self):
        # A minimal user has no work data → 'work' must be present as 'unknown',
        # not silently dropped.
        sigs = {s.domain: s for s in
                es_adapter.build_executive_state_signals(self.user)}
        self.assertEqual(sigs["work"].status, "unknown")

    def test_context_signals_excluded_from_lenses(self):
        # Steady-state context signals must NOT be selectable as win/decline/etc.
        from apps.core.cos_briefing.executive_state import (
            select_executive_lenses)
        sigs = es_adapter.build_executive_state_signals(self.user)
        picks = select_executive_lenses(sigs)
        for v in picks.values():
            if v is not None:
                self.assertNotEqual(getattr(v, "lens", None), "context")
