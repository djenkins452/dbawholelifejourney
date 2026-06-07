"""Double Progression Strength Service — earned, deterministic progression.

Trust contracts under test:
  · PRs are NEVER the trigger word for advice (search the rendered copy).
  · Completion = earned, NOT survival = earned (readiness gate).
  · Logic ≠ copy: rationale_key + numbers → message, not the other way.
  · Fail-closed: any safety hold downgrades to HOLDING; never advances.
  · Path A classification with isolation as the conservative default.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.health.models import (
    Exercise,
    ExerciseSet,
    WorkoutExercise,
    WorkoutSession,
)
from apps.health.services.double_progression import (
    classify_exercise,
    evaluate_double_progression,
    render_recommendation_copy,
    REP_LADDER,
    REQUIRED_SESSIONS,
    STAGE_EARNED_REPS,
    STAGE_REP_RANGE_TRANSITION,
    STAGE_EARNED_WEIGHT,
    STAGE_HOLDING,
)
from apps.users.models import TermsAcceptance

User = get_user_model()


def _user(email="dp@test.com"):
    u = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=u,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _exercise(name="Chest Press", muscle="chest", category="resistance",
              movement_type="weighted", load_type="external"):
    return Exercise.objects.create(
        name=name, muscle_group=muscle, category=category,
        movement_type=movement_type, load_type=load_type,
    )


def _session(user, days_ago=0):
    today = timezone.now().date()
    s = WorkoutSession.objects.create(
        user=user, date=today - timedelta(days=days_ago),
        completed_at=timezone.now() - timedelta(days=days_ago),
        status="active",
    )
    return s


def _log_set(session, exercise, *, weight, reps, set_number=1,
             is_warmup=False, notes="", exercise_notes=""):
    we, _ = WorkoutExercise.objects.get_or_create(
        session=session, exercise=exercise, defaults={"order": 0},
    )
    if exercise_notes:
        we.notes = exercise_notes
        we.save()
    return ExerciseSet.objects.create(
        workout_exercise=we,
        set_number=set_number,
        weight=Decimal(str(weight)) if weight is not None else None,
        reps=reps,
        is_warmup=is_warmup,
        notes=notes,
    )


#: A healthy SAE fitness/health snapshot — used by all "no global hold"
#: tests so the safety gate is OPEN unless the test explicitly modifies it.
HEALTHY_FITNESS = {"workouts_7d": 3, "workouts_30d": 12}
HEALTHY_HEALTH = {"sleep_status": "good", "sleep_last_night_hours": 7.5}


# ── Classification (Path A) ────────────────────────────────────────


class ClassificationTests(TestCase):
    """Pattern-based classification — no migration, isolation is the
    SAFE default."""

    def test_chest_press_is_compound(self):
        ex = _exercise(name="Chest Press")
        self.assertEqual(classify_exercise(ex), "compound")

    def test_leg_press_is_compound(self):
        ex = _exercise(name="Leg Press", muscle="legs")
        self.assertEqual(classify_exercise(ex), "compound")

    def test_lateral_raise_is_isolation(self):
        ex = _exercise(name="Lateral Raise", muscle="shoulders")
        self.assertEqual(classify_exercise(ex), "isolation")

    def test_bicep_curl_is_isolation(self):
        ex = _exercise(name="Bicep Curl", muscle="biceps")
        self.assertEqual(classify_exercise(ex), "isolation")

    def test_leg_extension_not_misclassified_as_leg_press(self):
        """The 'extension' isolation pattern must win over any
        compound-leaning fallback for the muscle group."""
        ex = _exercise(name="Leg Extension", muscle="legs")
        self.assertEqual(classify_exercise(ex), "isolation")

    def test_unknown_defaults_to_isolation(self):
        """Conservative fallback — small step, longer ladder."""
        ex = _exercise(name="Mystery Move", muscle="")
        self.assertEqual(classify_exercise(ex), "isolation")

    def test_muscle_group_fallback_compound(self):
        ex = _exercise(name="Generic Press Movement Z", muscle="chest")
        # 'press' substring hits compound directly anyway, but cover
        # the muscle fallback path:
        ex2 = _exercise(name="Heavy Mover", muscle="back")
        self.assertEqual(classify_exercise(ex2), "compound")


# ── Stage ladder — compound ───────────────────────────────────────


class CompoundLadderTests(TestCase):
    """Compound ladder: 10 → 12 → +weight. No 15-rep step."""

    def setUp(self):
        self.user = _user("comp@test.com")
        self.ex = _exercise(name="Chest Press", muscle="chest")

    def _log_three_clean_sessions(self, *, weight, reps, working_sets=3):
        """K sessions, every working set at top weight hits `reps`."""
        for d in (10, 5, 0):
            sess = _session(self.user, days_ago=d)
            for n in range(1, working_sets + 1):
                _log_set(sess, self.ex, weight=weight, reps=reps,
                         set_number=n)

    def test_earned_reps_at_10_recommends_12(self):
        self._log_three_clean_sessions(weight=50, reps=10)
        recs = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS, health_state=HEALTHY_HEALTH,
        )
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(r["stage"], STAGE_EARNED_REPS)
        self.assertEqual(r["ladder_type"], "compound")
        self.assertEqual(r["rationale_key"], "earned_reps")
        self.assertEqual(r["next_target"]["reps"], 12)
        self.assertEqual(r["next_target"]["weight_lb"], 50.0)
        # PRs are NEVER the trigger word.
        copy = render_recommendation_copy(r)
        self.assertNotIn("PR", copy)
        self.assertNotIn("personal record", copy.lower())

    def test_earned_12_reps_recommends_weight_increase_not_15(self):
        """Compound MUST skip the 15-rep rung — heavier joint cost."""
        self._log_three_clean_sessions(weight=50, reps=12)
        recs = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS, health_state=HEALTHY_HEALTH,
        )
        r = recs[0]
        self.assertEqual(r["stage"], STAGE_EARNED_WEIGHT)
        self.assertEqual(r["next_target"]["reps"], 10)
        # +5 lb step for compound.
        self.assertEqual(r["next_target"]["weight_lb"], 55.0)


# ── Stage ladder — isolation ──────────────────────────────────────


class IsolationLadderTests(TestCase):
    """Isolation ladder: 10 → 12 → 15 → +weight. Smaller step."""

    def setUp(self):
        self.user = _user("iso@test.com")
        self.ex = _exercise(name="Lateral Raise", muscle="shoulders")

    def _log(self, *, weight, reps):
        for d in (10, 5, 0):
            sess = _session(self.user, days_ago=d)
            for n in range(1, 4):
                _log_set(sess, self.ex, weight=weight, reps=reps,
                         set_number=n)

    def test_earned_12_recommends_15(self):
        self._log(weight=15, reps=12)
        recs = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS, health_state=HEALTHY_HEALTH,
        )
        r = recs[0]
        self.assertEqual(r["stage"], STAGE_REP_RANGE_TRANSITION)
        self.assertEqual(r["next_target"]["reps"], 15)
        self.assertEqual(r["ladder_type"], "isolation")
        self.assertEqual(r["rationale_key"], "earned_range")

    def test_earned_15_recommends_small_weight_increase(self):
        self._log(weight=15, reps=15)
        recs = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS, health_state=HEALTHY_HEALTH,
        )
        r = recs[0]
        self.assertEqual(r["stage"], STAGE_EARNED_WEIGHT)
        self.assertEqual(r["next_target"]["weight_lb"], 17.5)
        self.assertEqual(r["next_target"]["reps"], 10)


# ── Readiness gate — completion ≠ survival ────────────────────────


class ReadinessGateTests(TestCase):
    """The contract the user explicitly added — multiple proxies for
    'completed comfortably' in the absence of RPE."""

    def setUp(self):
        self.user = _user("rd@test.com")
        self.ex = _exercise(name="Chest Press", muscle="chest")

    def _three_sessions(self, *, weight, reps_per_session, set_count=3,
                       notes_per_session=None, exercise_notes_per_session=None):
        notes_per_session = notes_per_session or [""] * 3
        exercise_notes_per_session = exercise_notes_per_session or [""] * 3
        sessions = []
        for i, d in enumerate((10, 5, 0)):
            sess = _session(self.user, days_ago=d)
            for n in range(1, set_count + 1):
                _log_set(
                    sess, self.ex,
                    weight=weight, reps=reps_per_session[i],
                    set_number=n, notes=notes_per_session[i],
                    exercise_notes=exercise_notes_per_session[i],
                )
            sessions.append(sess)
        return sessions

    def test_any_set_below_target_holds_not_advances(self):
        """Three sessions where one session had a 9-rep set — survived
        but not earned. Stage stays HOLDING."""
        self._three_sessions(weight=50, reps_per_session=[10, 9, 10])
        recs = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS, health_state=HEALTHY_HEALTH,
        )
        r = recs[0]
        self.assertEqual(r["stage"], STAGE_HOLDING)
        self.assertEqual(r["rationale_key"], "stable")

    def test_failure_note_in_set_holds(self):
        self._three_sessions(
            weight=50, reps_per_session=[10, 10, 10],
            notes_per_session=["", "", "form broke on last set"],
        )
        recs = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS, health_state=HEALTHY_HEALTH,
        )
        r = recs[0]
        self.assertEqual(r["stage"], STAGE_HOLDING)
        self.assertIn("form_signal", r["safety_holds"])

    def test_failure_note_on_workout_exercise_holds(self):
        self._three_sessions(
            weight=50, reps_per_session=[10, 10, 10],
            exercise_notes_per_session=["", "shaky reps today", ""],
        )
        recs = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS, health_state=HEALTHY_HEALTH,
        )
        r = recs[0]
        self.assertEqual(r["stage"], STAGE_HOLDING)
        self.assertIn("form_signal", r["safety_holds"])

    def test_low_workout_consistency_holds(self):
        self._three_sessions(weight=50, reps_per_session=[10, 10, 10])
        recs = evaluate_double_progression(
            self.user,
            fitness_state={"workouts_7d": 0, "workouts_30d": 3},
            health_state=HEALTHY_HEALTH,
        )
        r = recs[0]
        self.assertEqual(r["stage"], STAGE_HOLDING)
        self.assertIn("low_consistency", r["safety_holds"])

    def test_poor_sleep_holds(self):
        self._three_sessions(weight=50, reps_per_session=[10, 10, 10])
        recs = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS,
            health_state={"sleep_status": "poor",
                          "sleep_last_night_hours": 4.5},
        )
        r = recs[0]
        self.assertEqual(r["stage"], STAGE_HOLDING)
        self.assertIn("poor_sleep", r["safety_holds"])

    def test_low_recovery_holds(self):
        self._three_sessions(weight=50, reps_per_session=[10, 10, 10])
        recs = evaluate_double_progression(
            self.user,
            fitness_state={**HEALTHY_FITNESS, "recovery_score_today": 30},
            health_state=HEALTHY_HEALTH,
        )
        r = recs[0]
        self.assertEqual(r["stage"], STAGE_HOLDING)
        self.assertIn("low_recovery", r["safety_holds"])

    def test_illness_holds(self):
        self._three_sessions(weight=50, reps_per_session=[10, 10, 10])
        recs = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS,
            health_state={**HEALTHY_HEALTH, "illness_active": True},
        )
        r = recs[0]
        self.assertEqual(r["stage"], STAGE_HOLDING)
        self.assertIn("illness", r["safety_holds"])

    def test_multiple_holds_stack(self):
        self._three_sessions(weight=50, reps_per_session=[10, 10, 10])
        recs = evaluate_double_progression(
            self.user,
            fitness_state={"workouts_7d": 0, "workouts_30d": 3},
            health_state={"sleep_status": "poor"},
        )
        r = recs[0]
        self.assertEqual(r["stage"], STAGE_HOLDING)
        self.assertIn("low_consistency", r["safety_holds"])
        self.assertIn("poor_sleep", r["safety_holds"])

    def test_missing_state_fails_closed(self):
        """No SAE state available at all — must NOT advance."""
        self._three_sessions(weight=50, reps_per_session=[10, 10, 10])
        recs = evaluate_double_progression(self.user)
        r = recs[0]
        self.assertEqual(r["stage"], STAGE_HOLDING)


# ── History eligibility ───────────────────────────────────────────


class HistoryEligibilityTests(TestCase):
    def setUp(self):
        self.user = _user("hist@test.com")
        self.ex = _exercise(name="Chest Press", muscle="chest")

    def test_insufficient_sessions_omitted_from_output(self):
        for d in (5, 0):
            sess = _session(self.user, days_ago=d)
            _log_set(sess, self.ex, weight=50, reps=10)
        recs = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS, health_state=HEALTHY_HEALTH,
        )
        # INSUFFICIENT_HISTORY entries are filtered out — caller never
        # has to know about that stage.
        self.assertEqual(recs, [])

    def test_warmups_ignored(self):
        for d in (10, 5, 0):
            sess = _session(self.user, days_ago=d)
            _log_set(sess, self.ex, weight=30, reps=15, set_number=1,
                     is_warmup=True)
            _log_set(sess, self.ex, weight=50, reps=10, set_number=2)
            _log_set(sess, self.ex, weight=50, reps=10, set_number=3)
        recs = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS, health_state=HEALTHY_HEALTH,
        )
        r = recs[0]
        self.assertEqual(r["current"]["weight_lb"], 50.0)
        self.assertEqual(r["stage"], STAGE_EARNED_REPS)

    def test_inconsistent_top_weight_holds(self):
        """Three sessions but weight wandered → no plateau, no rec."""
        sess1 = _session(self.user, days_ago=10)
        _log_set(sess1, self.ex, weight=50, reps=10)
        sess2 = _session(self.user, days_ago=5)
        _log_set(sess2, self.ex, weight=55, reps=10)
        sess3 = _session(self.user, days_ago=0)
        _log_set(sess3, self.ex, weight=60, reps=10)
        recs = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS, health_state=HEALTHY_HEALTH,
        )
        r = recs[0]
        self.assertEqual(r["stage"], STAGE_HOLDING)

    def test_stale_history_holds(self):
        """All three sessions older than 14 days → stale → HOLD."""
        for d in (30, 25, 20):
            sess = _session(self.user, days_ago=d)
            _log_set(sess, self.ex, weight=50, reps=10)
        recs = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS, health_state=HEALTHY_HEALTH,
        )
        if recs:
            self.assertEqual(recs[0]["stage"], STAGE_HOLDING)
            self.assertIn("stale_history", recs[0]["safety_holds"])

    def test_weight_within_half_pound_tolerance_same_bucket(self):
        """49.9 and 50.0 should bucket together — no false plateau-break."""
        for d, w in ((10, "49.9"), (5, "50.0"), (0, "50.0")):
            sess = _session(self.user, days_ago=d)
            for n in (1, 2, 3):
                _log_set(sess, self.ex, weight=w, reps=10, set_number=n)
        recs = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS, health_state=HEALTHY_HEALTH,
        )
        r = recs[0]
        self.assertEqual(r["stage"], STAGE_EARNED_REPS)


# ── Per-exercise scoping + idempotency ────────────────────────────


class ScopingAndIdempotencyTests(TestCase):
    def setUp(self):
        self.user = _user("sc@test.com")

    def test_exercise_id_scopes_to_one(self):
        ex1 = _exercise(name="Chest Press", muscle="chest")
        ex2 = _exercise(name="Lateral Raise", muscle="shoulders")
        for d in (10, 5, 0):
            sess = _session(self.user, days_ago=d)
            _log_set(sess, ex1, weight=50, reps=10)
            _log_set(sess, ex2, weight=15, reps=10)
        single = evaluate_double_progression(
            self.user, exercise_id=ex1.id,
            fitness_state=HEALTHY_FITNESS, health_state=HEALTHY_HEALTH,
        )
        self.assertEqual(len(single), 1)
        self.assertEqual(single[0]["exercise_name"], "Chest Press")

    def test_idempotent(self):
        ex = _exercise(name="Chest Press", muscle="chest")
        for d in (10, 5, 0):
            sess = _session(self.user, days_ago=d)
            _log_set(sess, ex, weight=50, reps=10)
        r1 = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS, health_state=HEALTHY_HEALTH,
        )
        r2 = evaluate_double_progression(
            self.user,
            fitness_state=HEALTHY_FITNESS, health_state=HEALTHY_HEALTH,
        )
        self.assertEqual(r1, r2)


# ── Copy rendering — Visual/Trust Contract ────────────────────────


class CopyRenderingTests(TestCase):
    """Logic ≠ copy. Test the renderer separately so that copy changes
    never require touching detection logic."""

    def test_earned_reps_copy_names_exercise_and_numbers(self):
        rec = {
            "exercise_name": "Chest Press",
            "ladder_type": "compound",
            "stage": STAGE_EARNED_REPS,
            "current": {"weight_lb": 50.0, "reps": 10, "sessions": 3},
            "next_target": {"weight_lb": 50.0, "reps": 12},
            "rationale_key": "earned_reps",
            "safety_holds": [],
        }
        copy = render_recommendation_copy(rec)
        self.assertIn("Chest Press", copy)
        self.assertIn("50", copy)
        self.assertIn("12", copy)
        self.assertNotIn("PR", copy)
        self.assertNotIn("personal record", copy.lower())
        self.assertNotIn("plateau", copy.lower())

    def test_earned_weight_copy_suggests_small_increase(self):
        rec = {
            "exercise_name": "Chest Press",
            "ladder_type": "compound",
            "stage": STAGE_EARNED_WEIGHT,
            "current": {"weight_lb": 50.0, "reps": 12, "sessions": 3},
            "next_target": {"weight_lb": 55.0, "reps": 10},
            "rationale_key": "earned_weight",
            "safety_holds": [],
        }
        copy = render_recommendation_copy(rec)
        self.assertIn("small increase", copy)
        self.assertIn("55", copy)
        self.assertIn("return to 10", copy)
        self.assertNotIn("PR", copy)

    def test_safety_hold_copy_is_stay_consistent(self):
        rec = {
            "exercise_name": "Shoulder Press",
            "ladder_type": "compound",
            "stage": STAGE_HOLDING,
            "current": {"weight_lb": 50.0, "reps": 10, "sessions": 3},
            "next_target": None,
            "rationale_key": "stable",
            "safety_holds": ["poor_sleep"],
        }
        copy = render_recommendation_copy(rec)
        self.assertIn("Stay consistent", copy)
        self.assertIn("sleep", copy.lower())
        self.assertNotIn("PR", copy)
        self.assertNotIn("increase", copy.lower())


# ── Ladder shape constants (lock the approved spec in code) ──────


class LadderShapeTests(TestCase):
    """Approved spec: compound 10→12→+weight; isolation 10→12→15→+weight."""

    def test_compound_ladder_does_not_include_15(self):
        self.assertEqual(REP_LADDER["compound"], [10, 12])

    def test_isolation_ladder_extends_to_15(self):
        self.assertEqual(REP_LADDER["isolation"], [10, 12, 15])

    def test_required_sessions_matches_existing_prefill_convention(self):
        self.assertEqual(REQUIRED_SESSIONS, 3)
