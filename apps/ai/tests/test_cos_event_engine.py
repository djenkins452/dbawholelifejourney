"""Chief of Staff Event Engine — detect → persist → resolve, with recurrence.

Events persist as GuidanceItem (notification center + Beth context) and carry the
mandatory three-part explanation (what / why / what-to-do). No new model.
"""
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.ai import cos_event_engine as eng
from apps.core.cos_briefing.executive_state import ExecutiveStateSignal

User = get_user_model()


def _sig(domain, lens, direction, title, message):
    return ExecutiveStateSignal(
        domain=domain, lens=lens, direction=direction, magnitude=None,
        confidence="high", title=title, message=message, evidence=[],
        source=f"{domain}_state", leverage=True)


class EventShape(SimpleTestCase):
    def test_three_part_message_and_keys(self):
        e = eng.CoSEvent(eng.STRATEGIC_RISK, "sleep", "Sleep down",
                         "Sleep fell.", "It matters.", "Fix it.")
        self.assertEqual(e.message, "Sleep fell. It matters. Fix it.")
        self.assertEqual(e.dedupe_key, "cos_event:strategic_risk:sleep")
        self.assertEqual(e.module, "health")

    def test_domain_module_mapping(self):
        self.assertEqual(eng.CoSEvent(eng.MAJOR_WIN, "faith", "t", "a", "b", "c").module, "faith")
        self.assertEqual(eng.CoSEvent(eng.STRATEGIC_RISK, "relationship", "t", "a", "b", "c").module, "relationships")


def _user(email):
    u = User.objects.create_user(email=email, password="x" * 20)
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class Detection(TestCase):
    def setUp(self):
        self.user = _user("eng@test.com")

    def _detect_with(self, intel, picks):
        with patch("apps.ai.cos_intelligence.build_cos_intelligence", return_value=intel), \
             patch("apps.core.cos_briefing.executive_state.build_executive_state_signals", return_value=[]), \
             patch("apps.core.cos_briefing.executive_state.select_executive_lenses", return_value=picks):
            return eng.detect_events(self.user)

    def test_detects_all_strategic_categories(self):
        intel = {"goal_pace": {"target_date": "2026-06-13", "remaining": 58.3,
                               "current_pace_lb_wk": 0.88, "target_passed": True},
                 "recommendation_effectiveness": "now 298 lb. This appears to be working."}
        picks = {
            "biggest_decline": _sig("sleep", "decline", "declining", "Sleep down", "Sleep is trending down."),
            "biggest_improvement": _sig("medication", "improvement", "improving", "Meds up", "100% adherence."),
            "biggest_win": _sig("weight", "win", "improving", "Down 12 lb", "Down 12 lb since start."),
        }
        cats = {(e.category, e.domain) for e in self._detect_with(intel, picks)}
        self.assertIn((eng.STRATEGIC_RISK, "weight"), cats)      # target passed
        self.assertIn((eng.STRATEGIC_RISK, "sleep"), cats)       # decline
        self.assertIn((eng.STRATEGIC_OPPORTUNITY, "medication"), cats)
        self.assertIn((eng.MAJOR_WIN, "weight"), cats)
        self.assertIn((eng.STRATEGIC_OPPORTUNITY, "recommendation"), cats)  # working

    def test_recommendation_not_working_is_risk(self):
        events = self._detect_with(
            {"recommendation_effectiveness": "it hasn't moved — time for a different approach."}, {})
        self.assertIn((eng.STRATEGIC_RISK, "recommendation"),
                      {(e.category, e.domain) for e in events})


class Persistence(TestCase):
    def setUp(self):
        self.user = _user("persist@test.com")
        self.ev = eng.CoSEvent(eng.STRATEGIC_RISK, "sleep", "Sleep down",
                               "Sleep fell below average.", "It matters.", "Protect sleep.")

    def test_create_then_recurrence_increments(self):
        item, created = eng.persist_event(self.user, self.ev)
        self.assertTrue(created)
        self.assertEqual(item.metadata["occurrence_count"], 1)
        self.assertEqual(item.guidance_type, "cos_event:strategic_risk")
        self.assertEqual(item.module, "health")
        item2, created2 = eng.persist_event(self.user, self.ev)
        self.assertFalse(created2)
        self.assertEqual(item2.pk, item.pk)
        self.assertEqual(item2.metadata["occurrence_count"], 2)

    def test_recurrence_escalates_framing_after_weeks(self):
        from apps.core.ai_guidance.models import GuidanceItem
        item, _ = eng.persist_event(self.user, self.ev)
        GuidanceItem.objects.filter(pk=item.pk).update(
            created_at=timezone.now() - timedelta(days=21))
        item2, _ = eng.persist_event(self.user, self.ev)
        print(f"\n>>>RECUR: {item2.message}\n<<<")
        self.assertIn("flagging this for about 3 weeks", item2.message)

    def test_run_engine_and_auto_resolve(self):
        from apps.core.ai_guidance.models import GuidanceItem
        risk = self.ev
        with patch.object(eng, "detect_events", return_value=[risk]):
            r1 = eng.run_cos_event_engine(self.user)
        self.assertEqual(r1["created"], 1)
        self.assertTrue(GuidanceItem.objects.filter(
            user=self.user, dedupe_key=risk.dedupe_key, is_active=True).exists())
        # Next run no longer detects it -> auto-resolved.
        with patch.object(eng, "detect_events", return_value=[]):
            r2 = eng.run_cos_event_engine(self.user)
        self.assertEqual(r2["resolved"], 1)
        self.assertFalse(GuidanceItem.objects.filter(
            user=self.user, dedupe_key=risk.dedupe_key, is_active=True).exists())

    def test_respects_proactive_switch_off(self):
        self.user.preferences.assistant_proactive_checkins = False
        self.user.preferences.save()
        with patch.object(eng, "detect_events", return_value=[self.ev]):
            r = eng.run_cos_event_engine(self.user)
        self.assertEqual(r["created"], 0)

    def test_recent_cos_events(self):
        eng.persist_event(self.user, self.ev)
        out = eng.recent_cos_events(self.user)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["category"], "strategic_risk")
        self.assertEqual(out[0]["domain"], "sleep")


class Integration(TestCase):
    def setUp(self):
        self.user = _user("eng_int@test.com")

    def test_events_in_standing_read(self):
        from apps.ai.cos_intelligence import cos_intelligence_narrative
        eng.persist_event(self.user, eng.CoSEvent(
            eng.STRATEGIC_RISK, "sleep", "Sleep down",
            "Sleep fell.", "It matters.", "Protect it."))
        out = cos_intelligence_narrative({"events": eng.recent_cos_events(self.user)})
        self.assertIn("Event [strategic risk]", out)

    def test_registered_in_scheduler(self):
        from apps.core.ai_scheduler.scheduler_registry import get_registered_tasks
        self.assertIn("run_cos_event_engine", get_registered_tasks())


class InAppDelivery(TestCase):
    """New strategic CoS events are delivered to the in-app notification center
    at creation, so they reach the web bell without aging out of the DNE scan."""

    def setUp(self):
        self.user = _user("delivery@test.com")

    def test_new_strategic_event_creates_notification(self):
        from unittest.mock import patch
        from apps.core.models import Notification
        ev = eng.CoSEvent(eng.STRATEGIC_RISK, "sleep", "Sleep is trending down",
                          "Sleep down.", "Constraint.", "Protect it.")
        with patch.object(eng, "detect_events", return_value=[ev]), \
             patch.object(eng, "detect_operational_events", return_value=([], True)):
            res = eng.run_cos_event_engine(self.user)
        self.assertEqual(res["delivered"], 1)
        self.assertTrue(Notification.objects.filter(
            user=self.user, category="intelligence").exists())

    def test_delivery_dedupes_on_rerun(self):
        from unittest.mock import patch
        from apps.core.models import Notification
        ev = eng.CoSEvent(eng.STRATEGIC_RISK, "sleep", "Sleep is trending down",
                          "Sleep down.", "Constraint.", "Protect it.")
        with patch.object(eng, "detect_events", return_value=[ev]), \
             patch.object(eng, "detect_operational_events", return_value=([], True)):
            eng.run_cos_event_engine(self.user)
            res2 = eng.run_cos_event_engine(self.user)   # already exists -> not new
        self.assertEqual(res2["delivered"], 0)
        self.assertEqual(Notification.objects.filter(
            user=self.user, category="intelligence").count(), 1)

    def test_operational_events_not_double_notified(self):
        from unittest.mock import patch
        from apps.core.models import Notification
        op = eng._operational_event(eng.PAST_DUE, {"title": "Prayer Time"})
        with patch.object(eng, "detect_events", return_value=[]), \
             patch.object(eng, "detect_operational_events", return_value=([op], True)):
            res = eng.run_cos_event_engine(self.user)
        self.assertEqual(res["delivered"], 0)   # operational handled elsewhere
        self.assertFalse(Notification.objects.filter(
            user=self.user, category="intelligence").exists())
