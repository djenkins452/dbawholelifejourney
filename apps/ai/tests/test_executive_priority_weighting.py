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
                    deferred_labels=set(), accomplishments=[], recovery_needed=False, hour=12)
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

    def test_reported_word_form_filters_a_differently_titled_item(self):
        # "journaled" (the user's word) must filter a "Journal your day" rhythm item —
        # stem-based completion match, the production "recommended journaling after done".
        pool = [_item("Journal your day", "routine_item", domain="journal"),
                _item("Stretch", "routine_item")]
        _, ranked = _rank(self.u, pool, accomplishments=["journaled"])
        self.assertNotIn("journal your day", [c["text"].lower() for c in ranked])

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


class EveningContextTests(TestCase):
    """Executive judgment IN CONTEXT — the 9:18 PM production failure. At night, remaining
    same-day health obligations outrank strategic work; a prescription due today is never
    buried; a supplement is not 'tomorrow's first priority'."""

    def setUp(self):
        self.u = User.objects.create_user(email="pawe@test.com", password="x")

    def test_evening_prescription_leads_strategic_and_supplement(self):
        # 9:18 PM: Metformin (prescription due tonight) leads; France (strategic) demoted;
        # Magnesium (supplement) sits below the prescription. THE production scenario.
        pool = [_item("Metformin HCL ER", "medication_dose", urgency="upcoming",
                      scheduled_time="21:00", domain="health"),
                _item("Magnesium glycinate", "supplement_dose", urgency="upcoming",
                      scheduled_time="21:00", domain="health")]
        top, ranked = _rank(self.u, pool, strategic_text="moving France 2027 forward", hour=21)
        self.assertIn("metformin", top["text"].lower())
        self.assertEqual(top["kind"], "health_obligation")
        # ordering: prescription > supplement > demoted strategic
        order = [c["text"].lower() for c in ranked]
        self.assertLess(order.index("metformin hcl er"),
                        [i for i, t in enumerate(order) if "france" in t][0])

    def test_strategic_is_demoted_below_remaining_health_at_night(self):
        pool = [_item("Magnesium", "supplement_dose", urgency="upcoming", domain="health")]
        top, _ = _rank(self.u, pool, strategic_text="moving France 2027 forward", hour=22)
        self.assertIn("magnesium", top["text"].lower())   # supplement 34 > evening strategic 26

    def test_prescription_due_now_beats_strategic_in_daytime(self):
        pool = [_item("Metformin", "medication_dose", urgency="now", domain="health")]
        top, _ = _rank(self.u, pool, strategic_text="moving France 2027 forward", hour=10)
        self.assertIn("metformin", top["text"].lower())   # due now (70) > strategic (66)

    def test_prescription_due_later_daytime_yields_to_strategic(self):
        # Not over-eager: a med due at 9 PM is not "the most important thing" at 10 AM.
        pool = [_item("Metformin", "medication_dose", urgency="upcoming", domain="health")]
        top, _ = _rank(self.u, pool, strategic_text="moving France 2027 forward", hour=10)
        self.assertIn("france", top["text"].lower())      # due later (50) < strategic (66)

    def test_remaining_health_obligations_prescriptions_first(self):
        from apps.core.cos_briefing.daily_agenda import _remaining_health_obligations
        items = [_item("Magnesium", "supplement_dose"), _item("Metformin", "medication_dose"),
                 _item("Shower", "routine_item")]
        hl = _remaining_health_obligations(items)
        self.assertEqual([i["title"] for i in hl], ["Metformin", "Magnesium"])  # rx first, hygiene excluded


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


class PriorityCorrectionTests(TestCase):
    """When the user corrects Beth's priority, she reconciles and re-answers — never a
    prescription fact dump (the production failure)."""

    def setUp(self):
        self.u = User.objects.create_user(email="pawc@test.com", password="x")

    def test_pushback_acknowledges_and_re_ranks(self):
        from apps.ai.chatgpt_cos.lanes import _priority_correction_lane
        pa = {"text": "take your remaining medication tonight",
              "why": "a prescription still due today — adherence comes first"}
        with mock.patch(_INTERP, return_value=ExecutiveSignals(priority_action=pa)):
            out = _priority_correction_lane(
                self.u,
                "You realize I already journaled, but I have two medicines left for today? "
                "You are just saying to ignore my medicine? Worst CoS ever. "
                "The most valuable thing is France 2027?")
        self.assertIsNotNone(out)
        self.assertEqual(out["lane"], "priority_correction")
        low = out["answer"].lower()
        self.assertIn("you're right", low)                 # acknowledges
        self.assertIn("already done", low)                 # drops completed journaling
        self.assertIn("remaining medication", low)         # corrected priority
        self.assertNotIn("atorvastatin", low)              # NOT a prescription fact dump

    def test_unrelated_message_not_claimed(self):
        from apps.ai.chatgpt_cos.lanes import _priority_correction_lane
        self.assertIsNone(_priority_correction_lane(self.u, "what's my weight right now?"))


class DailyAgendaValueTests(TestCase):
    def test_tomorrow_first_prefers_value_over_earlier_routine(self):
        from apps.core.cos_briefing.daily_agenda import _top_value_item
        items = [_item("Magnesium", "supplement_dose", scheduled_time="06:00"),
                 _item("Ship the release", "task", is_foundational=True, scheduled_time="16:00")]
        top = _top_value_item(items)
        self.assertEqual(top["title"], "Ship the release")   # value over earliest-scheduled
