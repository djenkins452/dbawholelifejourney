# ==============================================================================
# File: apps/ai/tests/test_executive_priority_weighting.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: EXECUTIVE PRIORITY WEIGHTING — Beth ranks candidate actions by executive
#   VALUE, not chronology. One capability behind five production failures (Shower,
#   Protein, Pattern, Magnesium, Journaling): the priority/next/tomorrow/wind-down
#   surfaces surfaced the next-SCHEDULED item instead of what actually matters.
#   interpret().priority_action ranks health-critical / strategic / opportunity /
#   today's incomplete items by value, filters completed/accomplished/deferred, and uses
#   scheduled_time only as a tiebreaker.
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos.executive_interpretation import (
    interpret, _rank_priority_actions, ExecutiveSignals,
)
from apps.ai.chatgpt_cos.lanes import _deterministic_priority_answer, _next_rhythm_lane

User = get_user_model()
_RRI = "apps.core.cos_briefing.rhythm_api.get_remaining_rhythm_items"
_INTERP = "apps.ai.chatgpt_cos.executive_interpretation.interpret"


def _item(title, source_type="routine_item", is_foundational=False, urgency="upcoming",
          scheduled_time="", domain="", completed_today=False):
    return {"title": title, "source_type": source_type, "is_foundational": is_foundational,
            "urgency": urgency, "scheduled_time": scheduled_time, "domain": domain,
            "completed_today": completed_today}


def _rank(user, pool, **kw):
    defaults = dict(health_critical=[], opportunity=None, strategic_text="",
                    deferred_labels=set(), accomplishments=[], recovery_needed=False)
    defaults.update(kw)
    with mock.patch(_RRI, return_value=pool):
        return _rank_priority_actions(user, **defaults)


class RankerTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(email="paw@test.com", password="x")

    def test_overdue_shower_does_not_outrank_a_real_commitment(self):
        # SYMPTOM 1: Shower (routine_item) must not win just because it's overdue/earliest.
        pool = [_item("Shower", "routine_item", urgency="overdue", scheduled_time="07:00"),
                _item("Finish the Q3 report", "task", scheduled_time="14:00")]
        top, _ = _rank(self.u, pool)
        self.assertEqual(top["text"], "Finish the Q3 report")   # task (44) > routine (24)

    def test_health_critical_leads_everything(self):
        pool = [_item("Finish the Q3 report", "task")]
        top, _ = _rank(self.u, pool,
                       health_critical=[{"text": "take your overdue morning meds",
                                         "why": "overdue since 8am"}])
        self.assertEqual(top["source"], "health_critical")
        self.assertIn("meds", top["text"].lower())

    def test_strategic_beats_a_scheduled_supplement(self):
        # SYMPTOM 4/Magnesium: a supplement never outranks strategic/mission work.
        pool = [_item("Magnesium", "supplement_dose", scheduled_time="06:00")]
        top, _ = _rank(self.u, pool, strategic_text="moving France 2027 forward")
        self.assertIn("france 2027", top["text"].lower())        # strategic (66) > supplement (20)

    def test_completed_today_is_filtered(self):
        # SYMPTOM 5/Journaling: an already-done item is never a candidate.
        pool = [_item("Journal", "routine_item", domain="journal", completed_today=True),
                _item("Stretch", "routine_item")]
        _, ranked = _rank(self.u, pool)
        self.assertNotIn("journal", [c["text"].lower() for c in ranked])

    def test_accomplished_and_deferred_are_filtered(self):
        pool = [_item("Journal", "routine_item"), _item("Shower", "routine_item"),
                _item("Stretch", "routine_item")]
        _, ranked = _rank(self.u, pool, accomplishments=["Journal"],
                          deferred_labels={"shower"})
        titles = [c["text"].lower() for c in ranked]
        self.assertNotIn("journal", titles)      # already accomplished
        self.assertNotIn("shower", titles)       # user deferred it away

    def test_chronology_is_only_a_tiebreaker(self):
        # Equal-value items → earlier scheduled wins (tiebreaker). But VALUE always beats
        # an earlier clock time: a task at 23:00 outranks supplements at 06:00.
        equal = [_item("Vitamin C", "supplement_dose", scheduled_time="09:00"),
                 _item("Magnesium", "supplement_dose", scheduled_time="06:00")]
        top, _ = _rank(self.u, equal)
        self.assertEqual(top["text"], "Magnesium")               # equal value → earliest time

        mixed = equal + [_item("Pay the invoice", "task", scheduled_time="23:00")]
        top2, _ = _rank(self.u, mixed)
        self.assertEqual(top2["text"], "Pay the invoice")        # value beats earlier schedule


class InterpretIntegrationTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(email="pawi@test.com", password="x")

    def test_priority_action_is_value_ranked_not_scheduled(self):
        pool = [_item("Shower", "routine_item", urgency="overdue", scheduled_time="07:00"),
                _item("Finish the launch plan", "task", scheduled_time="15:00")]
        with mock.patch("apps.ai.cos_services.get_domain_state", return_value={"state": {}}), \
                mock.patch("apps.ai.chatgpt_cos.executive_interpretation._health_critical_actions",
                           return_value=[]), \
                mock.patch(_RRI, return_value=pool):
            sig = interpret(self.u)
        self.assertIsNotNone(sig.priority_action)
        self.assertIn("launch plan", sig.priority_action["text"].lower())  # not the overdue Shower


class LaneConsumptionTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(email="pawl@test.com", password="x")

    def test_priority_now_consumes_priority_action(self):
        pa = {"text": "take your overdue morning meds", "why": "overdue since 8am",
              "source": "health_critical"}
        with mock.patch(_INTERP, return_value=ExecutiveSignals(priority_action=pa)):
            ans = _deterministic_priority_answer(self.u).lower()
        self.assertIn("most important thing right now", ans)
        self.assertIn("take your overdue morning meds", ans)
        self.assertIn("outranks what's merely next on the schedule", ans)

    def test_next_rhythm_consumes_priority_action_not_schedule(self):
        pa = {"text": "finish the launch plan", "why": "foundational to your mission"}
        with mock.patch(_INTERP, return_value=ExecutiveSignals(priority_action=pa)):
            out = _next_rhythm_lane(self.u, "what should I do next?")
        self.assertIsNotNone(out)
        self.assertEqual(out["lane"], "next_rhythm")
        low = out["answer"].lower()
        self.assertIn("most valuable thing to do next is finish the launch plan", low)


class DailyAgendaValueTests(TestCase):
    def test_tomorrow_first_prefers_value_over_earlier_routine(self):
        from apps.core.cos_briefing.daily_agenda import _top_value_item
        items = [_item("Magnesium", "supplement_dose", scheduled_time="06:00"),
                 _item("Ship the release", "task", is_foundational=True, scheduled_time="16:00")]
        top = _top_value_item(items)
        self.assertEqual(top["title"], "Ship the release")   # value over earliest-scheduled
