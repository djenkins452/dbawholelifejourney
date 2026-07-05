# ==============================================================================
# File: apps/ai/tests/test_executive_reconciliation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: EXECUTIVE STATE RECONCILIATION. When the user supplies trustworthy
#   evidence that an item Beth is treating as today's priority is not appropriate ("I
#   did it yesterday", "I don't need one", "that's a morning-only activity", "that
#   meeting was canceled"), Beth ACCEPTS it, UPDATES her executive understanding, and
#   CONTINUES — instead of retrieving a fact and collapsing. Production failure:
#   "I showered late yesterday … weighing in" → Beth returned yesterday's WEIGHT (the
#   weight_history lane grabbed the reason), then "I couldn't pull that together."
#   General, NOT hardcoded: items resolve from the user's OWN rhythm + the item Beth
#   just surfaced.
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos import reconciliation
from apps.ai.chatgpt_cos.lanes import route_message
from apps.ai.models import AssistantConversation, AssistantMessage

User = get_user_model()
_R = "apps.core.cos_briefing.rhythm_api.get_remaining_rhythm_items"
_HC = "apps.ai.chatgpt_cos.executive_interpretation._health_critical_actions"

# The user's OWN rhythm — nothing about the capability is specific to these titles.
RHYTHM = [{"title": "Shower", "scheduled_time": "07:00"},
          {"title": "Measurements"},
          {"title": "Fish Oil", "scheduled_time": "20:00"}]

# The exact production message.
PROD = ("I don't really need one. I showered late yesterday. Too late to Measure, "
        "that is a first thing in the morning activity like weighing in.")


class ReconciliationDetectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="recon@test.com", password="x")

    def test_resolves_named_items_and_leaves_others(self):
        with mock.patch(_R, return_value=RHYTHM):
            rec = reconciliation.detect(self.user, PROD)
        self.assertIsNotNone(rec)
        self.assertEqual({it["title"] for it in rec.items}, {"Shower", "Measurements"})
        self.assertEqual(rec.resume, "tomorrow morning")     # morning-only → tomorrow morning

    def test_referential_resolves_the_item_beth_just_surfaced(self):
        conv = AssistantConversation.objects.create(user=self.user)
        AssistantMessage.objects.create(conversation=conv, role="assistant",
                                        content="Next up: Shower (7:00 AM). It's marked as overdue.")
        with mock.patch(_R, return_value=RHYTHM):
            rec = reconciliation.detect(self.user, "I don't really need one.", conv)
        self.assertEqual({it["title"] for it in rec.items}, {"Shower"})

    def test_already_did_defers_to_tomorrow(self):
        with mock.patch(_R, return_value=RHYTHM):
            rec = reconciliation.detect(self.user, "I already did the shower and measurements today.")
        self.assertEqual({it["title"] for it in rec.items}, {"Shower", "Measurements"})
        self.assertEqual(rec.resume, "tomorrow")

    def test_a_question_is_never_reconciliation(self):
        # "what was my weight yesterday?" is a QUERY — reconciliation must decline so
        # weight_history keeps its job.
        with mock.patch(_R, return_value=RHYTHM):
            self.assertIsNone(reconciliation.detect(self.user, "what was my weight yesterday?"))

    def test_unrelated_statement_not_claimed(self):
        with mock.patch(_R, return_value=RHYTHM):
            self.assertIsNone(reconciliation.detect(self.user, "I'm going to work on France today."))

    def test_evidence_without_a_matching_item_declines(self):
        # A reconciliation act about something NOT on the rhythm resolves no item → decline.
        with mock.patch(_R, return_value=RHYTHM):
            self.assertIsNone(reconciliation.detect(self.user, "the dentist appointment was canceled."))


class ReconciliationComposeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="reconc@test.com", password="x")

    def test_accepts_updates_and_continues(self):
        with mock.patch(_R, return_value=RHYTHM):
            rec = reconciliation.detect(self.user, PROD)
            text = reconciliation.compose(self.user, rec).lower()
        self.assertIn("that makes sense", text)              # ACCEPTS
        self.assertIn("stop treating", text)                 # UPDATES
        self.assertIn("shower", text)
        self.assertIn("measurements", text)
        self.assertIn("tomorrow morning", text)              # resume window
        self.assertIn("fish oil", text)                      # RECALCULATES: what remains
        self.assertNotIn("you weighed", text)                # never a weight lookup


class ReconciliationStateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="reconst@test.com", password="x")

    def test_answer_records_deferral_into_the_one_picture(self):
        with mock.patch(_R, return_value=RHYTHM):
            out = reconciliation.answer(self.user, PROD)
        self.assertEqual(out["lane"], "reconciliation")
        from apps.ai.chatgpt_cos.executive_interpretation import interpret
        sig = interpret(self.user)
        labels = {(d.get("item") or "").lower() for d in sig.deferred}
        self.assertIn("shower", labels)
        self.assertIn("measurements", labels)

    def test_deferred_item_drops_out_of_the_lead_picture(self):
        from apps.ai.chatgpt_cos import executive_evidence
        executive_evidence.record_deferral(self.user, "Shower")
        with mock.patch(_HC, return_value=[{"text": "Shower is overdue", "why": "routine"}]):
            from apps.ai.chatgpt_cos.executive_interpretation import interpret
            sig = interpret(self.user)
        self.assertEqual(sig.health_critical, [])            # reconciled away → not led with


class ReconciliationRoutingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="reconrt@test.com", password="x")

    def test_reconciliation_beats_weight_history_on_the_production_turn(self):
        conv = AssistantConversation.objects.create(user=self.user)
        with mock.patch(_R, return_value=RHYTHM):
            out = route_message(self.user, PROD, conv)
        self.assertEqual(out["lane"], "reconciliation")      # NOT weight_history
        low = out["answer"].lower()
        self.assertIn("stop treating", low)
        self.assertNotIn("you weighed", low)                 # the production bug is gone
