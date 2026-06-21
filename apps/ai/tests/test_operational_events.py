"""Operational reminders federated into the CoS event stream (2026-06-21).

approaching / due_now / past_due / recurring_problem persist as GuidanceItems in
the SAME stream as strategic events — one unified awareness model. Covers the
directive's 10 required areas.
"""
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai import cos_event_engine as eng

User = get_user_model()


def _user(email):
    u = User.objects.create_user(email=email, password="x" * 20)
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _exec_state(upcoming=None, now=None, overdue=None):
    return {"upcoming_actions": upcoming or [], "now_actions": now or [],
            "overdue_actions": overdue or []}


class OperationalDetection(TestCase):
    def setUp(self):
        self.user = _user("op@test.com")

    def _detect(self, **kw):
        with patch("apps.core.execution.execution_state.build_execution_state",
                   return_value=_exec_state(**kw)):
            return eng.detect_operational_events(self.user)

    def test_approaching_event_creation(self):       # area 1
        evs, ok = self._detect(upcoming=[{"title": "Workout", "time_display": "5:00 PM"}])
        self.assertTrue(ok)
        e = evs[0]
        self.assertEqual(e.category, eng.APPROACHING)
        self.assertIn("coming up", e.what_happened)
        self.assertEqual(e.dedupe_key, "cos_event:op:health:workout")

    def test_due_now_event_creation(self):           # area 2
        evs, _ = self._detect(now=[{"title": "Prayer Time", "time_display": "5:30 AM"}])
        self.assertEqual(evs[0].category, eng.DUE_NOW)
        self.assertEqual(evs[0].module, "faith")     # keyword → faith module
        self.assertIn("due now", evs[0].what_happened)

    def test_past_due_event_creation(self):          # area 3
        evs, _ = self._detect(overdue=[{"title": "Metformin", "time_display": "8:00 AM",
                                        "is_foundational": True}])
        e = evs[0]
        self.assertEqual(e.category, eng.PAST_DUE)
        self.assertIn("overdue", e.what_happened)
        self.assertEqual(e.priority, 2)              # foundational

    def test_completed_items_skipped(self):
        evs, _ = self._detect(overdue=[{"title": "Done", "completed_today": True}])
        self.assertEqual(evs, [])


class RecurringAndResolution(TestCase):
    def setUp(self):
        self.user = _user("oprec@test.com")
        self.ev = eng._operational_event(
            eng.PAST_DUE, {"title": "Metformin", "time_display": "8:00 AM"})

    def test_recurrence_escalates_to_recurring_problem(self):   # area 4
        from apps.core.ai_guidance.models import GuidanceItem
        item, created = eng.persist_event(self.user, self.ev)
        self.assertTrue(created)
        # Seed two earlier distinct overdue days, then re-detect today (=3).
        today = timezone.now().date()
        meta = item.metadata
        meta["overdue_dates"] = [(today - timedelta(days=2)).isoformat(),
                                 (today - timedelta(days=1)).isoformat()]
        GuidanceItem.objects.filter(pk=item.pk).update(metadata=meta)
        item2, _ = eng.persist_event(self.user, self.ev)
        print(f"\n>>>RECURRING: {item2.message}\n<<<")
        self.assertEqual(item2.metadata["category"], eng.RECURRING_PROBLEM)
        self.assertEqual(item2.guidance_type, "cos_event:recurring_problem")
        self.assertIn("becoming a pattern", item2.message)
        self.assertEqual(item2.priority, 2)

    def test_dedupe_one_row_escalates_across_categories(self):  # area 6
        from apps.core.ai_guidance.models import GuidanceItem
        appr = eng._operational_event(eng.APPROACHING, {"title": "Metformin"})
        eng.persist_event(self.user, appr)
        eng.persist_event(self.user, self.ev)        # same item, now past_due
        rows = GuidanceItem.objects.filter(
            user=self.user, dedupe_key="cos_event:op:health:metformin")
        self.assertEqual(rows.count(), 1)            # ONE row
        self.assertEqual(rows.first().metadata["category"], eng.PAST_DUE)

    def test_auto_resolution_on_completion(self):    # area 5
        from apps.core.ai_guidance.models import GuidanceItem
        with patch.object(eng, "detect_events", return_value=[]), \
             patch("apps.core.execution.execution_state.build_execution_state",
                   return_value=_exec_state(overdue=[{"title": "Metformin"}])):
            eng.run_cos_event_engine(self.user)
        self.assertTrue(GuidanceItem.objects.filter(
            user=self.user, dedupe_key="cos_event:op:health:metformin",
            is_active=True).exists())
        # Item completed → no longer detected → resolved.
        with patch.object(eng, "detect_events", return_value=[]), \
             patch("apps.core.execution.execution_state.build_execution_state",
                   return_value=_exec_state()):
            r = eng.run_cos_event_engine(self.user)
        self.assertEqual(r["resolved"], 1)
        self.assertFalse(GuidanceItem.objects.filter(
            user=self.user, dedupe_key="cos_event:op:health:metformin",
            is_active=True).exists())

    def test_failed_op_detection_does_not_resolve(self):
        # ok=False (execution_state raised) must NOT resolve operational events.
        from apps.core.ai_guidance.models import GuidanceItem
        eng.persist_event(self.user, self.ev)
        with patch.object(eng, "detect_events", return_value=[]), \
             patch.object(eng, "detect_operational_events", return_value=([], False)):
            eng.run_cos_event_engine(self.user)
        self.assertTrue(GuidanceItem.objects.filter(
            user=self.user, dedupe_key="cos_event:op:health:metformin",
            is_active=True).exists())


class UnifiedStreamVisibility(TestCase):
    def setUp(self):
        self.user = _user("opvis@test.com")

    def test_notification_center_visibility(self):   # area 7
        from apps.core.ai_guidance.models import GuidanceItem
        eng.persist_event(self.user, eng._operational_event(
            eng.PAST_DUE, {"title": "Metformin"}))
        # Same query the notification center / active_guidance uses.
        visible = GuidanceItem.objects.filter(
            user=self.user, is_active=True, dismissed_at__isnull=True,
            dedupe_key__startswith="cos_event:")
        self.assertEqual(visible.count(), 1)

    def test_beth_standing_read_visibility(self):    # area 8
        from apps.ai.cos_intelligence import cos_intelligence_narrative
        eng.persist_event(self.user, eng._operational_event(
            eng.PAST_DUE, {"title": "Metformin", "time_display": "8:00 AM"}))
        out = cos_intelligence_narrative({"events": eng.recent_cos_events(self.user)})
        self.assertIn("Event [past due]", out)
        self.assertIn("Metformin", out)

    def test_strategic_and_operational_coexist(self):  # area 10 + unified
        from apps.core.ai_guidance.models import GuidanceItem
        strat = eng.CoSEvent(eng.STRATEGIC_RISK, "sleep", "Sleep down",
                             "Sleep fell.", "Matters.", "Protect it.")
        with patch.object(eng, "detect_events", return_value=[strat]), \
             patch("apps.core.execution.execution_state.build_execution_state",
                   return_value=_exec_state(overdue=[{"title": "Metformin"}])):
            r = eng.run_cos_event_engine(self.user)
        self.assertEqual(r["created"], 2)
        cats = set(GuidanceItem.objects.filter(
            user=self.user, is_active=True).values_list("metadata__category", flat=True))
        self.assertIn("strategic_risk", cats)
        self.assertIn("past_due", cats)

    def test_no_assistant_messages_created(self):    # area 9 (proactive untouched)
        from apps.ai.models import AssistantMessage
        before = AssistantMessage.objects.filter(conversation__user=self.user).count()
        with patch.object(eng, "detect_events", return_value=[]), \
             patch("apps.core.execution.execution_state.build_execution_state",
                   return_value=_exec_state(overdue=[{"title": "Metformin"}])):
            eng.run_cos_event_engine(self.user)
        after = AssistantMessage.objects.filter(conversation__user=self.user).count()
        self.assertEqual(before, after)              # event engine ≠ chat nudge
