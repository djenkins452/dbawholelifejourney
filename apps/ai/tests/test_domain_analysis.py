# ==============================================================================
# File: apps/ai/tests/test_domain_analysis.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The ANALYSIS truth surface — the deterministic guarantee behind
#   "investigate before concluding". Encodes the BEHAVIORAL CONTRACT as a
#   deterministic, model-free test: when WLJ holds relevant truth for a subject,
#   get_domain_analysis returns it composed in ONE bundle with holds_data=True
#   (so a reasoner cannot truthfully say "insufficient"); only a genuine absence
#   of WLJ truth yields status=empty / holds_data=False. Composition only — it
#   reuses the domain's existing history()/describe() surfaces; no new retrieval.
# ==============================================================================
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.domain_analysis import (
    analysis_capability_index,
    analysis_capable_domains,
    get_domain_analysis,
)
from apps.health.models import (
    Exercise, ExerciseSet, WorkoutExercise, WorkoutSession,
)

User = get_user_model()


def _seed_workouts(user, days):
    today = date.today()
    for d in days:
        s = WorkoutSession.objects.create(user=user, date=today - timedelta(days=d),
                                          name=f"Day{d}")
        ex = Exercise.objects.create(name="Standing Calf Raise", category="resistance",
                                     load_type="external", is_active=True)
        we = WorkoutExercise.objects.create(session=s, exercise=ex, order=0)
        ExerciseSet.objects.create(workout_exercise=we, set_number=1,
                                   weight=Decimal("135"), reps=12)


class StatePresenceTests(TestCase):
    """Blocker #8: a disabled/empty STATE must NOT be counted as an assessment signal —
    otherwise the overview reports holds_data=True over zero data (a fabrication trap)."""

    def test_disabled_or_empty_state_is_not_a_signal(self):
        from apps.ai.cos_services.domain_analysis import _state_is_present
        self.assertFalse(_state_is_present(None))
        self.assertFalse(_state_is_present({}))
        self.assertFalse(_state_is_present({"enabled": False}))       # finance-not-set-up marker
        self.assertFalse(_state_is_present({"enabled": True}))        # flag only, no facts

    def test_state_with_real_facts_is_a_signal(self):
        from apps.ai.cos_services.domain_analysis import _state_is_present
        self.assertTrue(_state_is_present({"net_worth": 0}))          # 0 is a real value
        self.assertTrue(_state_is_present({"enabled": True, "net_worth": 1200}))
        self.assertTrue(_state_is_present({"overdue_count": 3}))


class AnalysisCapabilityTests(TestCase):
    def test_health_advertises_analyzable_subjects(self):
        idx = analysis_capability_index()
        self.assertIn("health", idx)
        for subject in ("workouts", "weight", "sleep", "steps"):
            self.assertIn(subject, idx["health"])
        self.assertIn("health", analysis_capable_domains())


class AnalysisGuaranteeTests(TestCase):
    """THE acceptance criterion, deterministic: truth present → never 'insufficient'."""

    def setUp(self):
        self.user = User.objects.create_user(email="analysis@test.com", password="x")

    def test_present_truth_yields_holds_data_with_the_full_bundle(self):
        # The exact failing scenario: workouts logged this month → "analyze my workout trends"
        _seed_workouts(self.user, days=[1, 3, 6, 9])
        a = get_domain_analysis(self.user, "health", "workouts")

        self.assertEqual(a["status"], "ready")
        self.assertTrue(a["holds_data"])            # ← the reasoner MUST NOT say "insufficient"
        self.assertEqual(a["evidence"], "rich")     # 4 sessions ≥ threshold

        # One call carried the WHOLE investigation:
        self.assertEqual(a["all_time"]["total"], 4)                 # span/count
        self.assertTrue(a["all_time"]["span"]["start"])
        self.assertTrue(any(w.get("present")                        # trailing-window trend
                            for w in a["history"].values()))
        self.assertEqual(a["records"]["count"], 4)                  # record detail present
        # …and the detail is real (exercises/sets/reps/weights), not just a count
        first = a["records"]["records"][0]
        self.assertIn("Calf Raise", str(first))                     # the exercise, in the record

    def test_recent_activity_never_reads_empty_via_a_prior_calendar_window(self):
        # The period-semantics trap that produced the false "insufficient": this-month
        # activity must surface even though a prior calendar window (last_month) is empty.
        _seed_workouts(self.user, days=[0, 2, 5])
        a = get_domain_analysis(self.user, "health", "workouts")
        self.assertEqual(a["status"], "ready")
        self.assertTrue(a["holds_data"])
        self.assertTrue(a["history"]["this_month"]["present"])

    def test_thin_but_present_truth_is_thin_not_absent(self):
        _seed_workouts(self.user, days=[2])          # a single session
        a = get_domain_analysis(self.user, "health", "workouts")
        self.assertEqual(a["status"], "ready")
        self.assertTrue(a["holds_data"])
        self.assertEqual(a["evidence"], "thin")      # present but < threshold — still NOT insufficient

    def test_genuine_absence_is_the_only_insufficient(self):
        # No workouts at all → the ONE honest "insufficient".
        a = get_domain_analysis(self.user, "health", "workouts")
        self.assertEqual(a["status"], "empty")
        self.assertFalse(a["holds_data"])
        self.assertEqual(a["evidence"], "absent")

    def test_all_time_carries_coherent_lifetime_change(self):
        # The production trust failure: "how much have I lost total" was answered by pairing
        # a trailing window's baseline (309.4) with the all-time start date (Aug 2 2024).
        # all_time must now carry ONE coherent lifetime change: earliest reading WITH its
        # date -> latest reading WITH its date -> delta/direction, from a SINGLE source.
        from django.utils import timezone
        from apps.health.models import WeightEntry
        now = timezone.now()
        WeightEntry.objects.create(user=self.user, value=Decimal("339.0"), unit="lb",
                                   recorded_at=now - timedelta(days=400))   # the true start
        WeightEntry.objects.create(user=self.user, value=Decimal("309.4"), unit="lb",
                                   recorded_at=now - timedelta(days=60))    # a mid point
        WeightEntry.objects.create(user=self.user, value=Decimal("282.9"), unit="lb",
                                   recorded_at=now - timedelta(days=1))     # latest
        a = get_domain_analysis(self.user, "health", "weight")
        at = a["all_time"]
        # endpoints are the EARLIEST and LATEST readings, each with its own date + value
        self.assertAlmostEqual(float(at["start"]["value"]), 339.0, places=1)
        self.assertAlmostEqual(float(at["end"]["value"]), 282.9, places=1)
        self.assertNotEqual(at["start"]["date"], at["end"]["date"])
        # the coherent total-change fact: 339 -> 282.9 (a loss), NOT 309.4 -> 282.9
        ch = at["change"]
        self.assertAlmostEqual(float(ch["first"]), 339.0, places=1)
        self.assertAlmostEqual(float(ch["last"]), 282.9, places=1)
        self.assertEqual(ch["direction"], "falling")
        self.assertAlmostEqual(float(ch["delta"]), -56.1, places=1)

    def test_subject_without_entity_still_composes_history(self):
        # A history-only subject (weight) has no records but still analyzes.
        from django.utils import timezone
        from apps.health.models import WeightEntry
        now = timezone.now()
        for d in (1, 4, 8):
            WeightEntry.objects.create(user=self.user, value=Decimal("185.0"),
                                       unit="lb", recorded_at=now - timedelta(days=d))
        a = get_domain_analysis(self.user, "health", "weight")
        self.assertEqual(a["status"], "ready")
        self.assertTrue(a["holds_data"])
        self.assertIsNone(a.get("records"))          # no entity surface for weight


class AnalysisHonestStateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="analysis2@test.com", password="x")

    # Blocker #5: an unknown domain/subject must NEVER produce a `reason` that leaks internal
    # routing language — the model narrates `reason` verbatim ("the life domain isn't
    # supported"). The status token stays for WLJ's own routing; the customer-facing reason is
    # sanitized + guides a graceful pivot.
    _LEAK_TERMS = ("not in the truth resolution layer", "unsupported", "unknown domain",
                   "not an analyzable subject")

    def test_unknown_subject_is_unsupported_not_a_guess(self):
        a = get_domain_analysis(self.user, "health", "quidditch")
        self.assertEqual(a["status"], "unsupported")
        self.assertIn("workouts", a["analyzable_subjects"])
        reason = (a.get("reason") or "").lower()
        for term in self._LEAK_TERMS:
            self.assertNotIn(term, reason)
        self.assertIn("do not tell the user", reason)

    def test_unknown_domain_is_unsupported_domain(self):
        a = get_domain_analysis(self.user, "atlantis", "workouts")
        self.assertEqual(a["status"], "unsupported_domain")
        reason = (a.get("reason") or "").lower()
        for term in self._LEAK_TERMS:
            self.assertNotIn(term, reason)
        self.assertIn("do not tell the user", reason)          # never expose it as unsupported
        self.assertIn("analysis_capable_domains", a)           # gives the model real areas

    def test_whole_life_request_answers_directly_never_asks_to_narrow(self):
        # Blocker #6: "give me an overall assessment of my whole life" (unknown domain 'life',
        # overview subject) must guide the model to ANSWER — lead with the executive read — and
        # must NEVER tell it to hand scoping back to the user ("which area would you like?").
        a = get_domain_analysis(self.user, "life", "overall")
        self.assertEqual(a["status"], "unsupported_domain")
        reason = (a.get("reason") or "").lower()
        self.assertIn("whole-life", reason)
        self.assertIn("give a real assessment", reason)
        self.assertIn("do not ask them to narrow", reason)
        self.assertNotIn("offer to assess", reason)     # no defer-to-user language
        for term in self._LEAK_TERMS:
            self.assertNotIn(term, reason)

    def test_wrap_truth_never_re_emits_the_raw_status_token(self):
        # The model-interface wrap MUST preserve the customer-safe reason, not the bare
        # "unsupported_domain" token it used to hand the model to narrate.
        from apps.ai.model_interface.service import _wrap_truth
        raw = get_domain_analysis(self.user, "life", "overall")
        env = _wrap_truth(raw, source="get_analysis")
        self.assertEqual(env["status"], "insufficient_evidence")
        self.assertNotEqual((env.get("reason") or "").strip().lower(), "unsupported_domain")
        self.assertIn("do not tell the user", (env.get("reason") or "").lower())


class WholeDomainOverviewTests(TestCase):
    """The production defect: 'overall health' → get_analysis(health, 'overall') returned
    `unsupported`. A whole-domain request must compose EVERY subject, never dead-end."""

    def setUp(self):
        self.user = User.objects.create_user(email="overview@test.com", password="x")

    def _seed_weight(self):
        from django.utils import timezone
        from apps.health.models import WeightEntry
        now = timezone.now()
        for d in (1, 4, 8):
            WeightEntry.objects.create(user=self.user, value=Decimal("282.0"),
                                       unit="lb", recorded_at=now - timedelta(days=d))

    def test_overall_is_advertised_for_multi_subject_health(self):
        # Discoverability: the capability index the model reads must list 'overall'.
        idx = analysis_capability_index()
        self.assertIn("overall", idx["health"])

    def test_overall_composes_every_subject_never_unsupported(self):
        self._seed_weight()
        _seed_workouts(self.user, days=[1, 3, 6])
        a = get_domain_analysis(self.user, "health", "overall")
        self.assertEqual(a["status"], "ready")           # NOT "unsupported"
        self.assertTrue(a["holds_data"])
        # The roll-up carried the subjects that have data.
        self.assertTrue(a["subjects"]["weight"]["present"])
        self.assertTrue(a["subjects"]["workouts"]["present"])
        self.assertGreaterEqual(a["subjects_with_data"], 2)

    def test_natural_phrasing_overall_health_routes_to_overview(self):
        # The EXACT subject the model passed in production.
        self._seed_weight()
        a = get_domain_analysis(self.user, "health", "overall health")
        self.assertEqual(a["status"], "ready")
        self.assertEqual(a["subject"], "overall")
        self.assertTrue(a["holds_data"])

    def test_aliases_are_deduped_by_metric(self):
        # blood_pressure/bp share one metric → composed once, not twice.
        self._seed_weight()
        a = get_domain_analysis(self.user, "health", "overall")
        covered = a["subjects_covered"]
        self.assertNotIn("bp", covered)                  # the alias is dropped
        self.assertIn("blood_pressure", covered)         # the canonical name is kept

    def test_genuine_absence_across_all_subjects_is_empty(self):
        a = get_domain_analysis(self.user, "health", "overall")
        self.assertEqual(a["status"], "empty")
        self.assertFalse(a["holds_data"])
        self.assertEqual(a["evidence"], "absent")


class OverviewWindowFidelityTests(TestCase):
    """The requested window is HONORED exactly — every subject is composed against the SAME
    resolved window and nothing outside it. Prevents out-of-window (e.g. this-month) data
    from influencing a "last week" summary."""

    def setUp(self):
        self.user = User.objects.create_user(email="window@test.com", password="x")

    def _weight(self, days_ago, value):
        from django.utils import timezone
        from apps.health.models import WeightEntry
        WeightEntry.objects.create(
            user=self.user, value=Decimal(str(value)), unit="lb",
            recorded_at=timezone.now() - timedelta(days=days_ago))

    def test_out_of_window_data_is_excluded(self):
        # Two readings inside the last 7 days, one 20 days ago (this month, NOT last week).
        self._weight(1, 281)
        self._weight(3, 282)
        self._weight(20, 300)                       # OUTSIDE a 7-day window
        a = get_domain_analysis(self.user, "health", "overall", period="last_7_days")
        w = a["subjects"]["weight"]
        self.assertTrue(w["present"])
        self.assertEqual(w["count"], 2)             # the day-20 reading must NOT be counted
        self.assertEqual(a["window"]["days"], 7)
        self.assertLess(a["window"]["start"], a["window"]["end"])   # window disclosed

    def test_natural_language_window_resolved_by_shared_authority(self):
        # "past 7 days" must resolve to the same 7-day window (alias in periods.py).
        self._weight(2, 281)
        self._weight(20, 300)
        a = get_domain_analysis(self.user, "health", "overall", period="past 7 days")
        self.assertEqual(a["subjects"]["weight"]["count"], 1)   # only the in-window reading
        self.assertEqual(a["window"]["name"], "last_7_days")
        self.assertEqual(a["window"]["days"], 7)

    def test_last_n_days_resolves_to_a_trailing_window(self):
        # "last 30 days" (the acceptance-test phrasing) must resolve to a 30-day trailing
        # window, not fall back to 7 days.
        self._weight(2, 281)
        a = get_domain_analysis(self.user, "health", "overall", period="last 30 days")
        self.assertEqual(a["window"]["days"], 30)
        self.assertFalse(a["window"]["requested_period_unresolved"])

    def test_default_window_is_domain_natural_not_seven_days(self):
        # A fixed 7-day default is not customer-natural (a week is too short to judge health).
        # With NO period stated, health defaults to its natural 30-day horizon.
        self._weight(2, 281)
        a = get_domain_analysis(self.user, "health", "overall")
        self.assertEqual(a["window"]["days"], 30)
        self.assertIsNone(a["window"]["requested_period"])
        self.assertTrue(a["window"]["auto_selected"])
        self.assertFalse(a["window"]["widened"])

    def test_default_horizon_differs_by_domain(self):
        from apps.ai.cos_services.domain_analysis import _DOMAIN_DEFAULT_DAYS
        self.assertEqual(_DOMAIN_DEFAULT_DAYS["finance"], 30)      # ~ current month
        self.assertEqual(_DOMAIN_DEFAULT_DAYS["relationships"], 90)  # seasonal, not weekly

    def test_auto_widen_finds_most_recent_window_with_activity(self):
        # Only reading is 60 days ago: the 30-day natural window is empty, so WLJ widens to the
        # most recent horizon that holds data (90 days) rather than reporting "no data".
        self._weight(60, 290)
        a = get_domain_analysis(self.user, "health", "overall")
        self.assertEqual(a["status"], "ready")
        self.assertTrue(a["window"]["widened"])
        self.assertEqual(a["window"]["days"], 90)
        self.assertTrue(a["subjects"]["weight"]["present"])
        self.assertIn("widened", a["window"]["state_the_period"].lower())

    def test_explicit_period_is_never_widened(self):
        # An explicit user period is honored EXACTLY — no smart default, no widen — even empty.
        self._weight(60, 290)
        a = get_domain_analysis(self.user, "health", "overall", period="last_7_days")
        self.assertEqual(a["window"]["days"], 7)
        self.assertFalse(a["window"]["widened"])
        self.assertFalse(a["window"]["auto_selected"])

    def test_change_carries_within_window_direction(self):
        # What improved / got worse: the deterministic within-window trend.
        self._weight(6, 286)                        # earlier in the window
        self._weight(1, 281)                        # later — weight fell
        a = get_domain_analysis(self.user, "health", "overall", period="last_7_days")
        change = a["subjects"]["weight"]["change"]
        self.assertIsNotNone(change)
        self.assertEqual(change["direction"], "falling")

    def test_unresolvable_period_falls_back_never_dead_ends(self):
        self._weight(2, 281)
        a = get_domain_analysis(self.user, "health", "overall", period="qwerty")
        self.assertEqual(a["status"], "ready")                 # NOT unsupported / error
        self.assertEqual(a["window"]["name"], "last_7_days")
        self.assertTrue(a["window"]["requested_period_unresolved"])


class PlatformAssessmentTests(TestCase):
    """The reusable platform: a whole-domain assessment composes STATE (where things stand)
    + TRENDS (what's changing). Coverage tracks composed truth, so a domain with >=2 current
    metrics but no history still gets an assessment from its state — no per-domain
    registration, never Health-special."""

    def setUp(self):
        self.user = User.objects.create_user(email="platform@test.com", password="x")

    def test_health_state_is_delivered_as_concepts_not_a_flat_dump(self):
        # Health is the concept proving-ground: its whole-domain assessment delivers
        # deterministic facts ORGANIZED BY CONCEPT (weight under body composition), with NO
        # flat 115-key state dump. The state's facts light up the assessment via concepts.
        from unittest.mock import patch
        fake_state = {"weight_current": 282.0, "sleep_avg_hours_7d": 6.5}
        with patch("apps.ai.cos_services.domain_analysis._overview_state",
                   return_value=fake_state):
            a = get_domain_analysis(self.user, "health", "overall")
        self.assertEqual(a["status"], "ready")
        self.assertTrue(a["holds_data"])
        self.assertNotIn("state", a)                       # no flat state dump for health
        self.assertIn("concepts", a)
        # weight arrives grouped under body composition, not as a loose key
        self.assertEqual(a["concepts"]["body_composition"]["members"]["weight"]["value"], 282.0)
        self.assertIn("sleep_recovery", a["concepts"])

    def test_finance_is_assessment_capable_via_current_state(self):
        # Finance has 0 history + 0 analysis subjects but 2 current metrics → it now composes
        # a whole-domain assessment (from state), and NEVER returns 'unsupported' for the
        # broad question. This is the class the customer felt ("how are my finances" broke).
        from unittest.mock import patch
        with patch("apps.ai.cos_services.domain_analysis._overview_state",
                   return_value={"net_worth": 120000, "month_spending": 4200}):
            a = get_domain_analysis(self.user, "finance", "overall")
        self.assertEqual(a["status"], "ready")
        self.assertTrue(a["holds_data"])
        self.assertEqual(a["state"]["net_worth"], 120000)

    def test_finance_advertised_overall_in_capability_index(self):
        # The model can DISCOVER that finance answers a whole-domain assessment.
        idx = analysis_capability_index()
        self.assertIn("overall", idx.get("finance", ()))

    def test_no_state_and_no_trend_is_honest_empty_not_unsupported(self):
        # Capable domain, but genuinely no state and no trend data → honest empty (a genuine
        # absence), never 'unsupported' and never a fabricated verdict.
        from unittest.mock import patch
        with patch("apps.ai.cos_services.domain_analysis._overview_state", return_value={}):
            a = get_domain_analysis(self.user, "finance", "overall")
        self.assertEqual(a["status"], "empty")
        self.assertFalse(a["holds_data"])
        self.assertEqual(a["evidence"], "absent")
