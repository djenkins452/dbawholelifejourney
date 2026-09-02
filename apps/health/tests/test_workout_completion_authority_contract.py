"""Contract: ONE completion authority for workouts.

`WorkoutQueries._COMPLETED_Q` is the single definition of "this workout happened".
It was broadened on 2026-04-04 (5d046408) because structured workouts do not stamp
`completed_at` until the explicit "Complete Workout" click, yet a session with
exercises logged is done from the user's point of view.

Nine production surfaces never got that memo and kept their own
`completed_at__isnull=False`, so the Health UI, the daily summary, the activity
signals, the exports and the dashboard all under-counted relative to the CoS —
`workout_minutes_7d` said 135 where the daily summary said 75 over the same
sessions. This test exists so a tenth copy cannot be written.

Adding an entry to ALLOWED_RAW_COMPLETION_FILTERS is the reviewed audit trail: it
must be a query that is NOT asking "did this workout happen".
"""
import ast
import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase

APPS_ROOT = Path(__file__).resolve().parents[2]

# Paths that legitimately hold a raw `completed_at__isnull=False` on WorkoutSession,
# each with the reason it is not the completion question.
ALLOWED_RAW_COMPLETION_FILTERS = {
    # The authority itself.
    "health/services/workout_queries.py":
        "Defines _COMPLETED_Q — this IS the rule.",
    # Not 'is it complete' but 'does it have a comparable time window': the HealthKit
    # dedup compares started_at/completed_at against an incoming workout's span, so
    # both timestamps must be present for the overlap test to mean anything.
    "mobile/views.py":
        "HealthKit overlap dedup needs both timestamps to compare spans, not completion.",
    # Ordering hazard, deliberately left narrow: these order by -completed_at to pick
    # "the most recent", and sessions completed without the click carry a NULL there,
    # which would order unpredictably. Tracked as a residual, not a silent exception.
    "health/services/fitness_progression.py":
        "Orders by -completed_at to take the last N sessions; NULLs would destabilise it.",
    "health/views.py":
        "Template-default prefill orders by -completed_at (same NULL-ordering hazard).",
    # Not the truth question at all. Auto-completing a routine item is an ACTION taken
    # on the user's behalf: logged sets prove work happened, but acting on a session
    # the user is still in the middle of would tick off their morning routine after one
    # warm-up set. The explicit completion stamp is the signal that they are finished.
    "health/signals.py":
        "Routine auto-complete is an action, not a truth read — it needs the finish.",
}

# Historical tools must keep the semantics they ran with.
EXEMPT_DIR_PARTS = ("migrations", "management", "tests")

RAW_PREDICATE = re.compile(r"(?<![\w.])completed_at__isnull\s*=\s*False")


class WorkoutCompletionAuthorityContract(SimpleTestCase):

    def _offending_files(self):
        offenders = {}
        for path in APPS_ROOT.rglob("*.py"):
            rel = path.relative_to(APPS_ROOT).as_posix()
            if any(part in path.parts for part in EXEMPT_DIR_PARTS):
                continue
            if path.name.startswith("test_") or path.name.startswith("tests"):
                continue
            source = path.read_text(encoding="utf-8", errors="ignore")
            if "WorkoutSession" not in source:
                continue
            # Ignore the predicate when it only appears inside comments/docstrings.
            code_hits = [
                line for line in source.splitlines()
                if RAW_PREDICATE.search(line) and not line.lstrip().startswith("#")
            ]
            if code_hits:
                offenders[rel] = code_hits
        return offenders

    def test_no_new_hand_rolled_completion_predicate(self):
        """No production module may re-derive workout completion for itself."""
        offenders = self._offending_files()
        unexpected = {k: v for k, v in offenders.items()
                      if k not in ALLOWED_RAW_COMPLETION_FILTERS}
        self.assertEqual(
            unexpected, {},
            "These modules hand-roll workout completion instead of calling "
            "WorkoutQueries. Route them through the canonical service, or add an "
            "entry to ALLOWED_RAW_COMPLETION_FILTERS explaining why the query is "
            "not asking whether the workout happened:\n"
            + "\n".join(f"  {k}: {v}" for k, v in unexpected.items()),
        )

    def test_allowlist_has_no_stale_entries(self):
        """An allowlist entry that no longer applies must be removed, not left to rot."""
        offenders = self._offending_files()
        stale = sorted(set(ALLOWED_RAW_COMPLETION_FILTERS) - set(offenders))
        self.assertEqual(
            stale, [],
            f"Allowlisted but no longer holding a raw predicate — delete these: {stale}",
        )

    def test_authority_recognises_evidence_of_work(self):
        """The rule itself: completed_at OR exercises OR duration, and nothing less."""
        from apps.health.services.workout_queries import _COMPLETED_Q
        rendered = str(_COMPLETED_Q)
        for clause in ("completed_at__isnull", "workout_exercises__isnull",
                       "duration_minutes__isnull"):
            self.assertIn(clause, rendered)

    def test_minutes_have_a_named_authority(self):
        """Totalling minutes is a named method, so surfaces cannot each invent one."""
        from apps.health.services.workout_queries import WorkoutQueries
        self.assertTrue(callable(WorkoutQueries.minutes_on))
        self.assertTrue(callable(WorkoutQueries.minutes_in_range))
        self.assertTrue(callable(WorkoutQueries.completed))


class WorkoutWritersProduceRecognisableTruth(TestCase):
    """A writer that records a completed workout must write a shape the authority accepts.

    Two production writers did not, so the row existed while the truth did not:
    the execution path's "mark my workout complete" (no completed_at, no duration, no
    exercises — the one shape _COMPLETED_Q rejects) and the assistant's quick-reply
    logger (duration but no completion stamp, visible to the CoS and invisible to the
    Health UI). Recording a completion and then answering "you have not worked out" is
    the trust-breaker; these assert it cannot recur.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        User = get_user_model()
        self.user = User.objects.create_user(
            email="writer-truth@example.com", password="testpass123")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        from django.utils import timezone
        self.today = timezone.localdate()

    def test_execution_completion_is_visible_to_the_authority(self):
        from apps.core.execution.execution_completion import _complete_workout
        from apps.health.services.workout_queries import WorkoutQueries

        result = _complete_workout(self.user, "Leg Day", self.today)
        self.assertEqual(result["status"], "recorded")
        self.assertTrue(
            WorkoutQueries.is_completed_on(self.user, self.today),
            "The assistant said it recorded a workout; WLJ must agree one happened.",
        )

    def test_execution_completion_invents_no_duration(self):
        """Recording that a workout happened must not fabricate how long it was."""
        from apps.core.execution.execution_completion import _complete_workout
        from apps.health.services.workout_queries import WorkoutQueries

        _complete_workout(self.user, "Leg Day", self.today)
        self.assertEqual(WorkoutQueries.minutes_on(self.user, self.today), 0)

    def test_already_complete_uses_the_same_rule(self):
        """A merely-started session is not a reason to refuse to record a completion."""
        from apps.core.execution.execution_completion import _complete_workout
        from apps.health.models import WorkoutSession
        from apps.health.services.workout_queries import WorkoutQueries
        from django.utils import timezone

        WorkoutSession.objects.create(
            user=self.user, date=self.today, name="Started Only",
            started_at=timezone.now())

        result = _complete_workout(self.user, "Leg Day", self.today)
        self.assertEqual(result["status"], "recorded")
        self.assertTrue(WorkoutQueries.is_completed_on(self.user, self.today))

    def test_assistant_quick_reply_log_is_visible_to_every_surface(self):
        from apps.ai.quick_reply_handlers import handle_confirm_workout
        from apps.health.services.workout_queries import WorkoutQueries
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

        res = handle_confirm_workout(self.user, {"workout_type": "Walking", "duration": 25})
        self.assertTrue(res["success"])
        self.assertTrue(WorkoutQueries.is_completed_on(self.user, self.today))
        self.assertEqual(WorkoutQueries.minutes_on(self.user, self.today), 25)
        dhs = DailyHealthSummaryBuilder()._collect_workouts(self.user, self.today)
        self.assertEqual(dhs["workout_minutes"], 25)
