# ==============================================================================
# File: apps/ai/tests/test_execution_facts.py
# Description: Batch 2 (Layer 1) — deterministic providers for the status questions
#   that previously fell to the tool-loop LLM: journaled today? worked out today?
#   appointments today? next appointment? Each now reads a canonical Domain Truth
#   Contract / pre-computed SAE state (Architecture Laws 0/1/4). No OpenAI.
# ==============================================================================
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.utils import get_user_today
from apps.journal.models import JournalEntry
from apps.health.models import WorkoutSession
from apps.ai.chatgpt_cos.foundational_facts import (
    classify_foundational_fact, format_fact_sentence,
)
from apps.ai.cos_services.execution_facts import get_foundational_execution_facts

User = get_user_model()
_GMS = "apps.core.ai_state.state_engine.get_module_state"


class ExecutionFactClassifierTests(TestCase):
    def test_status_questions_route_to_execution_keys(self):
        self.assertEqual(classify_foundational_fact("Did I journal today?"), "journal_today")
        self.assertEqual(classify_foundational_fact("Have I worked out today?"), "workout_today")
        self.assertEqual(classify_foundational_fact("Do I have any appointments today?"), "appointments_today")
        self.assertEqual(classify_foundational_fact("What's my next appointment?"), "next_appointment")
        self.assertEqual(classify_foundational_fact("What's on my calendar?"), "appointments_today")

    def test_coaching_questions_do_not_match(self):
        # No status phrasing → must NOT be claimed as a deterministic fact.
        self.assertIsNone(classify_foundational_fact("What workout should I do today?"))
        self.assertIsNone(classify_foundational_fact("Should I journal more often?"))

    def test_workout_yesterday_is_deterministic_not_llm_fallback(self):
        # CERTIFICATION REGRESSION (det_workouts): "Did I work out yesterday?" must NOT
        # return None (which routed it to the tool-loop generic fallback). It is a
        # completed-day deterministic fact, answerable for yesterday as well as today.
        self.assertEqual(classify_foundational_fact("Did I work out yesterday?"),
                         "workout_yesterday")
        self.assertEqual(classify_foundational_fact("Did I workout today?"),
                         "workout_today")


class ExecutionFactRetrievalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="exec@test.com", password="x")
        cls.today = get_user_today(cls.user)

    def test_journal_today_true_and_false(self):
        f = get_foundational_execution_facts(self.user, ["journal_today"])["journal_today"]
        self.assertFalse(f["value"])
        self.assertEqual(format_fact_sentence("journal_today", f),
                         "Not yet — you haven't journaled today.")
        JournalEntry.objects.create(user=self.user, entry_date=self.today)
        f = get_foundational_execution_facts(self.user, ["journal_today"])["journal_today"]
        self.assertTrue(f["value"])
        self.assertEqual(format_fact_sentence("journal_today", f), "Yes — you've journaled today.")

    def test_workout_today_true_and_false(self):
        f = get_foundational_execution_facts(self.user, ["workout_today"])["workout_today"]
        self.assertFalse(f["value"])
        # status defaults to 'active' (soft-delete field); duration_minutes marks
        # the session as completed per WorkoutQueries._COMPLETED_Q.
        WorkoutSession.objects.create(user=self.user, date=self.today,
                                      duration_minutes=30)
        f = get_foundational_execution_facts(self.user, ["workout_today"])["workout_today"]
        self.assertTrue(f["value"])
        self.assertEqual(format_fact_sentence("workout_today", f),
                         "Yes — you've logged a workout today.")

    def test_workout_yesterday_resolves_deterministically(self):
        from datetime import timedelta
        yest = self.today - timedelta(days=1)
        f = get_foundational_execution_facts(self.user, ["workout_yesterday"])["workout_yesterday"]
        self.assertFalse(f["value"])
        self.assertEqual(format_fact_sentence("workout_yesterday", f),
                         "No — you didn't log a workout yesterday.")  # det_workouts: 'didn't'
        WorkoutSession.objects.create(user=self.user, date=yest, duration_minutes=45)
        f = get_foundational_execution_facts(self.user, ["workout_yesterday"])["workout_yesterday"]
        self.assertTrue(f["value"])
        self.assertEqual(format_fact_sentence("workout_yesterday", f),
                         "Yes — you logged a workout yesterday.")     # det_workouts: 'workout'

    def test_appointments_today_from_calendar_state(self):
        state = {"today_events": [{"title": "Dentist", "start": "9:00 AM"},
                                  {"title": "Standup", "start": "10:30 AM"}],
                 "next_event": {"title": "Standup", "start": "10:30 AM"}}
        with mock.patch(_GMS, return_value=state):
            facts = get_foundational_execution_facts(
                self.user, ["appointments_today", "next_appointment"])
        appt = facts["appointments_today"]
        self.assertEqual(appt["value"], 2)
        self.assertEqual(format_fact_sentence("appointments_today", appt),
                         "You have 2 appointments today: Dentist at 9:00 AM; Standup at 10:30 AM.")
        self.assertEqual(format_fact_sentence("next_appointment", facts["next_appointment"]),
                         "Your next appointment is Standup at 10:30 AM.")

    def test_meals_today_retrieves_actual_meals_not_storage_jargon(self):
        # Defect Class 2 — Beth must retrieve breakfast/lunch/dinner, never leak
        # "meal entry" / storage concepts, and answer WHAT was eaten (not a date).
        from apps.health.models import FoodEntry
        self.assertEqual(classify_foundational_fact("What did I eat today?"), "meals_today")
        f = get_foundational_execution_facts(self.user, ["meals_today"])["meals_today"]
        self.assertEqual(format_fact_sentence("meals_today", f),
                         "You haven't logged any food today yet.")
        FoodEntry.objects.create(user=self.user, food_name="Oatmeal",
                                 meal_type="breakfast", logged_date=self.today,
                                 serving_size=1, quantity=1)
        FoodEntry.objects.create(user=self.user, food_name="Salad",
                                 meal_type="lunch", logged_date=self.today,
                                 serving_size=1, quantity=1)
        f = get_foundational_execution_facts(self.user, ["meals_today"])["meals_today"]
        s = format_fact_sentence("meals_today", f)
        self.assertIn("Breakfast", s)
        self.assertIn("Oatmeal", s)
        self.assertIn("Lunch", s)
        self.assertIn("Salad", s)
        self.assertIn("\u2022", s)  # bulleted list
        self.assertNotIn("entry", s.lower())       # no storage jargon
        self.assertNotIn("food entry", s.lower())

    def test_meals_yesterday_retrieves_real_meals(self):
        # Defect Class 3 — "What did I eat yesterday?" must retrieve real meals.
        from datetime import timedelta
        from apps.health.models import FoodEntry
        self.assertEqual(classify_foundational_fact("What did I eat yesterday?"),
                         "meals_yesterday")
        yest = self.today - timedelta(days=1)
        FoodEntry.objects.create(user=self.user, food_name="Eggs", meal_type="breakfast",
                                 logged_date=yest, serving_size=1, quantity=1)
        f = get_foundational_execution_facts(self.user, ["meals_yesterday"])["meals_yesterday"]
        s = format_fact_sentence("meals_yesterday", f)
        self.assertIn("Yesterday you logged:", s)
        self.assertIn("Breakfast", s)
        self.assertIn("Eggs", s)
        self.assertNotIn("entry", s.lower())
        # empty case
        f2 = get_foundational_execution_facts(
            User.objects.create_user(email="noeat@test.com", password="x"),
            ["meals_yesterday"])["meals_yesterday"]
        self.assertEqual(format_fact_sentence("meals_yesterday", f2),
                         "You didn't log any food yesterday.")

    def test_meds_today_adherence_from_sae(self):
        # Defect Class 5 — deterministic medication rollout ("did I take my meds today").
        self.assertEqual(classify_foundational_fact("Did I take my meds today?"), "meds_today")
        state = {"expected_today": 3, "today_taken": 2, "today_pending": 1, "today_missed": 0}
        with mock.patch(_GMS, return_value=state):
            f = get_foundational_execution_facts(self.user, ["meds_today"])["meds_today"]
        self.assertEqual(format_fact_sentence("meds_today", f),
                         "You've taken 2 of 3 doses today, with 1 still to take.")
        with mock.patch(_GMS, return_value={"expected_today": 0}):
            f = get_foundational_execution_facts(self.user, ["meds_today"])["meds_today"]
        self.assertEqual(format_fact_sentence("meds_today", f),
                         "You don't have any medications scheduled for today.")

    def test_last_journal_date_from_sae(self):
        # Defect Class 5 — deterministic journal rollout ("when did I last journal").
        self.assertEqual(classify_foundational_fact("When did I last journal?"), "last_journal")
        with mock.patch(_GMS, return_value={"last_entry": "2026-06-25", "days_since_entry": 3}):
            f = get_foundational_execution_facts(self.user, ["last_journal"])["last_journal"]
        self.assertEqual(format_fact_sentence("last_journal", f),
                         "You last journaled on 2026-06-25 (3 days ago).")

    def test_empty_calendar_is_honest(self):
        with mock.patch(_GMS, return_value={"today_events": [], "next_event": None}):
            facts = get_foundational_execution_facts(
                self.user, ["appointments_today", "next_appointment"])
        self.assertEqual(format_fact_sentence("appointments_today", facts["appointments_today"]),
                         "You have nothing on your calendar today.")
        self.assertEqual(facts["next_appointment"]["status"], "unknown")
