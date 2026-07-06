# ==============================================================================
# File: apps/ai/tests/test_significant_event_pipeline.py
# Description: Significant Event Pipeline (v1) — the Chief-of-Staff reflex.
#   PERMANENT REGRESSION for the production capability gap: Danny hit the
#   "France 2027 Family 18K Mission" weight milestone (283.1 lb vs a 284.9 lb
#   target due June 30, achieved July 2 — two days late but achieved), and
#   nothing recognized it as mission-significant until the 3-hour scheduler.
#   A production-ready CoS must react in the moment: recognize → judge → update
#   dependent truth → persist → notify → re-plan. No OpenAI on this path.
# ==============================================================================
from datetime import date, datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.events.domain_events import EventTypes
from apps.purpose.models import GoalMilestone, LifeGoal
from apps.health.models import WeightEntry
from apps.core.ai_guidance.models import GuidanceItem
from apps.ai.significant_events import (
    classify_significance, react_to_significant_event,
    enqueue_significant_event_reaction, is_significant_event_type,
)
from apps.ai.cos_event_engine import (
    run_cos_event_engine, recent_cos_events, _WIN_PREFIX, MAJOR_WIN,
)

User = get_user_model()


class SignificantEventPipelineTests(TestCase):
    """The France 2027 milestone case + the CoS-reflex acceptance criteria."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="danny-sig@example.com", password="pw12345!")

        # The Primary Mission with a 12-rung milestone ladder.
        self.mission = LifeGoal.objects.create(
            user=self.user, title="France 2027 Family 18K Mission",
            status="active", is_primary_mission=True)

        # m1 — a prior weight rung, ALREADY achieved → mission starts at 1/12.
        self.m1 = GoalMilestone.objects.create(
            goal=self.mission, title="Reach 289.9 lb", sort_order=1,
            objective_metric="weight_lb", objective_operator="lte",
            objective_target_value=289.9, completed=True,
            completed_date=date(2026, 5, 1))
        # m2 — THE France milestone: 284.9 lb, due June 30, not yet complete.
        self.m2 = GoalMilestone.objects.create(
            goal=self.mission, title="Reach 284.9 lb", sort_order=2,
            objective_metric="weight_lb", objective_operator="lte",
            objective_target_value=284.9, target_date=date(2026, 6, 30),
            completed=False)
        # m3 — the NEXT rung: 279.9 lb (the re-plan target).
        self.m3 = GoalMilestone.objects.create(
            goal=self.mission, title="Reach 279.9 lb", sort_order=3,
            objective_metric="weight_lb", objective_operator="lte",
            objective_target_value=279.9, target_date=date(2026, 8, 31),
            completed=False)
        # m4..m12 — achievement milestones (non-weight) to fill the ladder to 12.
        for i in range(4, 13):
            GoalMilestone.objects.create(
                goal=self.mission, title=f"Milestone {i}", sort_order=i,
                completed=False)

        # The exact France 2027 event payload the evaluator emits.
        self.france_data = {
            "milestone_id": self.m2.id, "goal_id": self.mission.id,
            "title": self.m2.title, "metric": "weight_lb",
            "target_value": 284.9, "target_date": "2026-06-30",
            "current_weight": 283.1, "achieved_date": "2026-07-02",
        }

    def _log_weight(self, value, when):
        return WeightEntry.objects.create(
            user=self.user, value=value, unit="lb", status="active",
            recorded_at=timezone.make_aware(datetime(when.year, when.month,
                                                      when.day, 8, 0)))

    def _completed_count(self):
        return self.mission.milestones.filter(completed=True).count()

    # ── milestone completion + mission progress (acceptance 1 & 2) ──────

    def test_weight_entry_completes_milestone_and_moves_mission_1_to_2(self):
        self.assertEqual(self._completed_count(), 1)          # 1/12 before
        self._log_weight(283.1, date(2026, 7, 2))              # signal → evaluate
        self.m2.refresh_from_db()
        self.assertTrue(self.m2.completed)                     # milestone achieved
        self.assertEqual(self.m2.completed_date, timezone.localdate())
        self.assertEqual(self._completed_count(), 2)           # 2/12 after
        self.m3.refresh_from_db()
        self.assertFalse(self.m3.completed)                    # next rung untouched

    # ── the event fires on achievement, onto the existing bus ───────────

    def test_achievement_emits_event_and_reaches_the_reflex(self):
        # The WeightEntry save → signal → evaluate → FALSE→TRUE transition must
        # emit purpose.milestone.completed, which reaches the pipeline enqueue.
        with mock.patch(
            "apps.ai.significant_events.enqueue_significant_event_reaction"
        ) as enq:
            self._log_weight(283.1, date(2026, 7, 2))
        enq.assert_called()
        _user, evtype, data = enq.call_args[0]
        self.assertEqual(evtype, EventTypes.PURPOSE_MILESTONE_COMPLETED)
        self.assertEqual(data["goal_id"], self.mission.id)
        self.assertEqual(data["target_value"], 284.9)
        self.assertEqual(data["current_weight"], 283.1)
        self.assertEqual(data["target_date"], "2026-06-30")

    # ── significance classification (acceptance: "determine why it matters") ─

    def test_classify_mission_milestone_is_significant(self):
        self.assertTrue(
            is_significant_event_type(EventTypes.PURPOSE_MILESTONE_COMPLETED))
        v = classify_significance(
            self.user, EventTypes.PURPOSE_MILESTONE_COMPLETED, self.france_data)
        self.assertIsNotNone(v)
        self.assertEqual(v["kind"], "mission_milestone")
        self.assertTrue(v["is_mission"])
        self.assertEqual(v["priority"], 2)                     # mission → surfaces first

    def test_non_significant_event_is_ignored(self):
        self.assertIsNone(classify_significance(
            self.user, EventTypes.HEALTH_WEIGHT_LOGGED, {}))

    # ── request path stays fast: reaction is ENQUEUED, not run inline ───

    def test_reaction_is_enqueued_not_run_inline(self):
        with mock.patch(
            "apps.ai.tasks.react_to_significant_event_task.delay"
        ) as delay:
            enqueue_significant_event_reaction(
                self.user, EventTypes.PURPOSE_MILESTONE_COMPLETED,
                self.france_data)
        delay.assert_called_once()
        # Nothing persisted synchronously on the emitting path.
        self.assertFalse(GuidanceItem.objects.filter(
            user=self.user, dedupe_key__startswith=_WIN_PREFIX).exists())

    # ── THE France 2027 regression — the full CoS reflex ────────────────

    @mock.patch("apps.core.ai_delivery.delivery_engine.deliver_single")
    def test_france_2027_regression_full_reflex(self, deliver):
        # Reach the milestone (completes m2 → 2/12), then run the reaction the
        # background worker runs — WITHOUT the 3-hour scheduler. The DNE front
        # door is mocked: the pipeline's contract is to HAND OFF to it (DNE
        # applies its own quiet-hours/throttle/dedupe policies + has its own
        # tests); exercising its DB writes here only adds cross-transaction noise.
        self._log_weight(283.1, date(2026, 7, 2))
        summary = react_to_significant_event(
            self.user, EventTypes.PURPOSE_MILESTONE_COMPLETED, self.france_data)

        # recognized + judged mission-significant
        self.assertTrue(summary["significant"])
        self.assertTrue(summary["is_mission"])
        self.assertTrue(summary["ok"])

        # mission progress reflects reality: 2 of 12
        self.assertEqual(summary["mission_progress"],
                         {"completed": 2, "total": 12})

        # a significant event / MAJOR WIN was persisted (sticky key)
        self.assertTrue(summary["event_persisted"])
        win = GuidanceItem.objects.filter(
            user=self.user, dedupe_key__startswith=_WIN_PREFIX).first()
        self.assertIsNotNone(win)
        self.assertEqual(win.metadata.get("category"), MAJOR_WIN)
        self.assertEqual(win.priority, 2)
        self.assertTrue(win.metadata.get("significant_event"))

        # available to Beth IMMEDIATELY (standing read), no scheduler wait
        events = recent_cos_events(self.user)
        self.assertTrue(any(e["title"] == "Reach 284.9 lb"
                            and e["category"] == MAJOR_WIN for e in events))

        # CoS-quality acknowledgment: what happened + why + what next
        ack = summary["acknowledgment"]
        self.assertIn("Reach 284.9 lb", ack)          # the milestone
        self.assertIn("283.1", ack)                    # actual weight (evidence)
        self.assertIn("284.9", ack)                    # target (evidence)
        self.assertIn("2 days late", ack)              # honest: achieved late
        self.assertIn("2 of 12", ack)                  # mission progress (framed as meaning)
        # WHY is meaning-first now — progression tied to THIS mission's purpose,
        # never the old generic "concrete step / reinforces the routine" copy.
        self.assertIn("real progress toward", ack.lower())
        self.assertIn("France 2027 Family 18K Mission", ack)
        self.assertNotIn("concrete step toward the mission you set", ack)

        # next milestone / next planning step is identified
        nm = summary["next_milestone"]
        self.assertIsNotNone(nm)
        self.assertEqual(nm["target_value"], 279.9)
        self.assertIn("279.9", ack)                    # surfaced in the acknowledgment

        # notified through the existing delivery infrastructure (DNE front door).
        # (assert_called, not _once: under Celery-EAGER the weight write already
        # drove the pipeline once end-to-end, and this explicit call is the
        # idempotent second pass — proof the full production path fires on its own.)
        self.assertTrue(summary["notified"])
        self.assertTrue(deliver.called)
        self.assertEqual(deliver.call_args[0][1], "COS")          # source engine
        payload = deliver.call_args[1]["payload"]
        self.assertEqual(payload["priority"], 2)                  # mission priority
        self.assertEqual(payload["message_type"], "cos_major_win")

    @mock.patch("apps.core.ai_delivery.delivery_router.deliver_in_app")
    @mock.patch("apps.core.ai_delivery.delivery_engine.deliver_single")
    def test_win_speaks_the_milestone_own_meaning_when_described(self, _d, _di):
        # When the milestone has its OWN meaning (a description), the win
        # acknowledgment must speak THAT — not a generic template. Proves the
        # stored recommendation uses the meaning-first composer, meaning-first.
        self.m2.description = "Six consecutive months of consistent progress"
        self.m2.save(update_fields=["description"])
        self._log_weight(283.1, date(2026, 7, 2))
        summary = react_to_significant_event(
            self.user, EventTypes.PURPOSE_MILESTONE_COMPLETED, self.france_data)
        ack = summary["acknowledgment"]
        self.assertIn("Six consecutive months of consistent progress", ack)
        self.assertIn("real progress toward", ack.lower())
        self.assertNotIn("concrete step toward the mission you set", ack)
        self.assertNotIn("banking it now", ack.lower())
        self.assertNotIn("next rung", ack.lower())

    # ── the one-time win is sticky (not auto-resolved by re-detection) ──

    @mock.patch("apps.core.ai_delivery.delivery_router.deliver_in_app")
    @mock.patch("apps.core.ai_delivery.delivery_engine.deliver_single")
    def test_win_survives_cos_event_engine_re_detection(self, _dsingle, _dinapp):
        self._log_weight(283.1, date(2026, 7, 2))
        react_to_significant_event(
            self.user, EventTypes.PURPOSE_MILESTONE_COMPLETED, self.france_data)
        win = GuidanceItem.objects.get(
            user=self.user, dedupe_key__startswith=_WIN_PREFIX)
        self.assertTrue(win.is_active)

        # A later scheduler pass must NOT resolve a milestone you actually hit.
        run_cos_event_engine(self.user)
        win.refresh_from_db()
        self.assertTrue(win.is_active)
        self.assertIsNone(win.dismissed_at)


class FranceTitleFormPropagationTests(TestCase):
    """The PRODUCTION shape (Stage-1 propagation regression). Migration 0018
    wired only the 289.9 rung to objective form; the 284.9 rung Danny actually
    crossed is TITLE-FORM (`objective_metric` NULL). Before the fix the evaluator
    ignored title-form rows, so 284.9 never completed — the dashboard (which
    reads milestone truth LIVE) correctly showed the mission frozen at 1/12 with
    the achieved rung still 'next'. This proves detection now fires for title-form
    milestones and propagates to the dashboard's OWN live consumers."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="france-tf@example.com", password="pw12345!")
        self.mission = LifeGoal.objects.create(
            user=self.user, title="France 2027 Family 18K Mission",
            status="active", is_primary_mission=True)
        # 289.9 — the ONE rung migration 0018 wired to objective form; done.
        self.m_289 = GoalMilestone.objects.create(
            goal=self.mission, title="Goal Weight of 289.9", sort_order=1,
            objective_metric="weight_lb", objective_operator="lte",
            objective_target_value=289.9, completed=True,
            completed_date=date(2026, 5, 1))
        # 284.9 — TITLE-FORM (objective_metric NULL), due June 30. Hit July 2.
        self.m_284 = GoalMilestone.objects.create(
            goal=self.mission, title="Reach 284.9 lb", sort_order=2,
            target_date=date(2026, 6, 30), completed=False)
        # 279.9 — TITLE-FORM, the next rung.
        self.m_279 = GoalMilestone.objects.create(
            goal=self.mission, title="Reach 279.9 lb", sort_order=3,
            target_date=date(2026, 8, 31), completed=False)
        # Non-weight achievement rungs (must stay manual) → total 12.
        for i in range(4, 13):
            GoalMilestone.objects.create(
                goal=self.mission, title=f"Run milestone {i}", sort_order=i,
                completed=False)

    def _log_weight(self, value, when):
        return WeightEntry.objects.create(
            user=self.user, value=value, unit="lb", status="active",
            recorded_at=timezone.make_aware(datetime(when.year, when.month,
                                                      when.day, 8, 0)))

    @mock.patch("apps.core.ai_delivery.delivery_engine.deliver_single")
    def test_title_form_crossing_completes_and_moves_the_live_dashboard(self, deliver):
        # BEFORE: the dashboard's live sources show the bug — 1/12, 284.9 next.
        self.assertEqual(self.mission.completed_milestone_count, 1)
        self.assertEqual(self.mission.next_milestone.id, self.m_284.id)

        # Cross the TITLE-FORM rung (283.1 <= 284.9).
        self._log_weight(283.1, date(2026, 7, 2))

        # Stage 1 now fires for a title-form milestone.
        self.m_284.refresh_from_db()
        self.assertTrue(self.m_284.completed)
        self.assertEqual(self.m_284.completed_date, timezone.localdate())

        # Dashboard's OWN live consumers move forward immediately (no snapshot,
        # no scheduler): completed_milestone_count + next_milestone.
        self.assertEqual(self.mission.milestone_count, 12)
        self.assertEqual(self.mission.completed_milestone_count, 2)        # 1/12 → 2/12
        self.assertEqual(self.mission.next_milestone.id, self.m_279.id)    # not the done rung

        # The next weight rung is NOT falsely completed (283.1 > 279.9).
        self.m_279.refresh_from_db()
        self.assertFalse(self.m_279.completed)

        # Full reflex fired end-to-end (eager): MAJOR_WIN in Beth's standing read
        # + notified via the DNE.
        win = GuidanceItem.objects.filter(
            user=self.user, dedupe_key__startswith=_WIN_PREFIX).first()
        self.assertIsNotNone(win)
        self.assertTrue(any(e["category"] == MAJOR_WIN
                            for e in recent_cos_events(self.user)))
        self.assertTrue(deliver.called)

    def test_title_form_completion_is_one_way(self):
        # Cross it, then regain weight — a title-form achievement must NOT
        # auto-uncomplete (respects manual toggles); only objective-form rows
        # are bidirectional.
        self._log_weight(283.1, date(2026, 7, 2))
        self.m_284.refresh_from_db()
        self.assertTrue(self.m_284.completed)

        self._log_weight(290.0, date(2026, 7, 3))
        self.m_284.refresh_from_db()
        self.assertTrue(self.m_284.completed)          # stays complete (one-way)
        self.m_289.refresh_from_db()
        self.assertFalse(self.m_289.completed)         # objective-form DID uncomplete

    def test_non_weight_achievement_never_auto_completes(self):
        # A rung with no weight target is left manual (Phase-1 back-compat).
        self._log_weight(200.0, date(2026, 7, 2))      # below every weight rung
        for i in range(4, 13):
            m = self.mission.milestones.get(title=f"Run milestone {i}")
            self.assertFalse(m.completed, f"'{m.title}' must stay manual")


class WinInternalConsistencyTests(TestCase):
    """PERMANENT REGRESSION (2026-07-06): a persisted MAJOR-WIN GuidanceItem was
    internally inconsistent — a completed milestone on the "Relationship with God"
    goal produced title "Milestone reached" (generic) and a next milestone of
    "Goal Weight 279.9 lb" (from the WEIGHT goal). Two composer bugs:

      1. title fell back to the literal "Milestone reached" because the event
         ``data`` carries no title and the real milestone_id title was never read.
      2. the next milestone came from ``goal_pace(user)`` — a user-global WEIGHT
         trajectory — instead of the completed goal's own next rung.

    The win's mission, current milestone, and next milestone must ALL come from
    the SAME goal.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="danny-consistency@example.com", password="pw12345!")

        # The user's PRIMARY MISSION is a weight goal — so goal_pace(user) would
        # (wrongly) return a weight milestone for ANY completion if unscoped.
        self.weight_mission = LifeGoal.objects.create(
            user=self.user, title="France 2027 Family 18K Mission",
            status="active", is_primary_mission=True)
        GoalMilestone.objects.create(
            goal=self.weight_mission, title="Reach 289.9 lb", sort_order=1,
            objective_metric="weight_lb", objective_operator="lte",
            objective_target_value=289.9, completed=True,
            completed_date=date(2026, 5, 1))
        GoalMilestone.objects.create(
            goal=self.weight_mission, title="Goal Weight 279.9", sort_order=2,
            objective_metric="weight_lb", objective_operator="lte",
            objective_target_value=279.9, target_date=date(2026, 7, 31),
            completed=False)
        WeightEntry.objects.create(
            user=self.user, value=285.0, unit="lb", status="active",
            recorded_at=timezone.make_aware(datetime(2026, 7, 1, 8, 0)))

        # A SEPARATE, non-primary goal with a real milestone ladder + meanings.
        self.faith_goal = LifeGoal.objects.create(
            user=self.user, title="Relationship with God",
            status="active", is_primary_mission=False)
        self.june = GoalMilestone.objects.create(
            goal=self.faith_goal, title="June Prayer Milestone", sort_order=6,
            description="Six consecutive months of consistent prayer",
            target_date=date(2026, 6, 30), completed=True,
            completed_date=date(2026, 6, 30))
        self.july = GoalMilestone.objects.create(
            goal=self.faith_goal, title="July Prayer Milestone", sort_order=7,
            target_date=date(2026, 7, 31), completed=False)

        # The domain event as the purpose evaluator emits it for a NON-weight
        # milestone: goal_id + milestone_id, but NO "title" (the title-bug trigger).
        self.faith_data = {
            "milestone_id": self.june.id,
            "goal_id": self.faith_goal.id,
        }

    @mock.patch("apps.core.ai_delivery.delivery_router.deliver_in_app")
    @mock.patch("apps.core.ai_delivery.delivery_engine.deliver_single")
    def test_win_is_scoped_to_the_completing_goal(self, _d, _di):
        summary = react_to_significant_event(
            self.user, EventTypes.PURPOSE_MILESTONE_COMPLETED, self.faith_data)
        self.assertTrue(summary["ok"])

        win = GuidanceItem.objects.get(
            user=self.user,
            dedupe_key=f"cos_event:win:milestone:{self.june.id}")

        # (1) TITLE is the REAL milestone title — never the generic literal.
        self.assertEqual(win.title, "June Prayer Milestone")
        self.assertNotEqual(win.title, "Milestone reached")
        self.assertIn("June Prayer Milestone", win.message)

        # (2) NEXT milestone belongs to the SAME goal — NOT the weight mission.
        nm = summary["next_milestone"]
        self.assertEqual(nm["title"], "July Prayer Milestone")
        self.assertEqual(nm["kind"], "milestone")
        self.assertIsNone(nm["target_value"])          # non-weight → no lb number

        # (3) NO cross-mission contamination anywhere in the acknowledgment.
        self.assertNotIn("279.9", win.message)
        self.assertNotIn("Goal Weight", win.message)
        self.assertNotIn(" lb", win.message)
        self.assertIn("Relationship with God", win.message)   # the right mission
        self.assertIn("July Prayer Milestone", win.message)   # the right next rung

        # (4) The milestone's OWN meaning is spoken (meaning-first, not generic).
        self.assertIn("Six consecutive months of consistent prayer", win.message)

    @mock.patch("apps.core.ai_delivery.delivery_router.deliver_in_app")
    @mock.patch("apps.core.ai_delivery.delivery_engine.deliver_single")
    def test_final_rung_completion_reports_goal_rungs_done(self, _d, _di):
        # Complete the LAST incomplete milestone → next-step is the goal itself,
        # never another goal's plan.
        self.july.completed = True
        self.july.completed_date = date(2026, 7, 31)
        self.july.save(update_fields=["completed", "completed_date"])
        data = {"milestone_id": self.july.id, "goal_id": self.faith_goal.id}
        summary = react_to_significant_event(
            self.user, EventTypes.PURPOSE_MILESTONE_COMPLETED, data)
        nm = summary["next_milestone"]
        self.assertEqual(nm["kind"], "goal_reached")
        self.assertEqual(nm["title"], "Relationship with God")

    def test_recompose_heals_a_cross_mission_row_in_place(self):
        # Simulate the exact production artifact: a win row persisted by the OLD
        # composer — generic title + a weight-goal next rung baked into message.
        bad = GuidanceItem.objects.create(
            user=self.user, title="Milestone reached",
            message=("You hit the “Milestone reached” milestone on Relationship "
                     "with God. That's milestone 6 of 12 on this mission. Bank "
                     "this one, then line up the next rung: Goal Weight 279.9 "
                     "(279.9 lb)."),
            priority=3, guidance_type="cos_event:major_win", source="composite",
            module="purpose",
            dedupe_key=f"cos_event:win:milestone:{self.june.id}",
            metadata={"category": MAJOR_WIN, "significant_event": True,
                      "next_milestone": {"kind": "milestone",
                                         "title": "Goal Weight 279.9",
                                         "target_value": 279.9}})

        from apps.ai.significant_events import recompose_milestone_win
        healed = recompose_milestone_win(bad)

        self.assertIsNotNone(healed)
        self.assertEqual(healed.id, bad.id)                 # rewritten IN PLACE
        self.assertEqual(healed.title, "June Prayer Milestone")
        self.assertNotIn("279.9", healed.message)           # weight rung gone
        self.assertNotIn("Goal Weight", healed.message)
        self.assertIn("June Prayer Milestone", healed.message)
        self.assertIn("July Prayer Milestone", healed.message)   # SAME-mission next
        self.assertEqual(
            healed.metadata["next_milestone"]["title"], "July Prayer Milestone")

        # Only ONE row exists for the key — upsert, not duplicate.
        self.assertEqual(GuidanceItem.objects.filter(
            dedupe_key=f"cos_event:win:milestone:{self.june.id}").count(), 1)
