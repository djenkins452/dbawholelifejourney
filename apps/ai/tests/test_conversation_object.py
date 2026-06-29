# ==============================================================================
# File: apps/ai/tests/test_conversation_object.py
# Description: Conversation Object capability. A deterministic fact carries the
#   supporting facts + answers the natural follow-ups (comparison, supporting items)
#   from the active topic — no new retrieval, no LLM, no topic drift. Includes a
#   COMPLETENESS gate enforcing the future rule: a fact's declared follow-ups must
#   be backed by the supporting facts they need.
# ==============================================================================
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.core.utils import get_user_today
from apps.health.models import StepsEntry, FoodEntry
from apps.ai.models import AssistantConversation
from apps.ai.chatgpt_cos.foundational_facts import answer_foundational_fact
from apps.ai.chatgpt_cos.conversation_memory import (
    record_last_answer, compose_comparison,
)
from apps.ai.chatgpt_cos.lanes import _why_explainer_lane
from apps.ai.chatgpt_cos import conversation_object as CO

User = get_user_model()
_GMS = "apps.core.ai_state.state_engine.get_module_state"
_CALL = "apps.ai.services.ai_service._call_api"


class ComparisonAcrossDomainsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="co@test.com", password="x")
        self.today = get_user_today(self.user)
        self.conv = AssistantConversation.objects.create(user=self.user)

    def _ask(self, prompt, state=None):
        with mock.patch(_CALL, return_value=None):
            if state is not None:
                with mock.patch(_GMS, return_value=state):
                    r = answer_foundational_fact(self.user, prompt)
            else:
                r = answer_foundational_fact(self.user, prompt)
        record_last_answer(self.conv, "foundational_facts", r)
        self.conv.refresh_from_db()
        return r

    def test_steps_compared_to_yesterday_from_memory(self):
        StepsEntry.objects.create(user=self.user, count=4200, logged_date=self.today)
        StepsEntry.objects.create(user=self.user, count=8123,
                                  logged_date=self.today - timedelta(days=1))
        self._ask("How many steps today?")
        out = _why_explainer_lane(self.user, "Compared to yesterday?", self.conv)
        self.assertIsNotNone(out)
        self.assertEqual(out["fast_path"], "conversation_memory")   # no new retrieval
        self.assertIn("down", out["answer"].lower())
        self.assertIn("3923", out["answer"])

    def test_calories_compared_to_yesterday(self):
        FoodEntry.objects.create(user=self.user, food_name="x", meal_type="lunch",
                                 logged_date=self.today - timedelta(days=1),
                                 serving_size=1, quantity=1, total_calories=1800)
        self._ask("How many calories today?", state={"daily_calories": 2000})
        out = _why_explainer_lane(self.user, "Compared to yesterday?", self.conv)
        self.assertIn("up", out["answer"].lower())
        self.assertIn("200", out["answer"])

    def test_comparison_declines_when_no_prior_supporting(self):
        # A fact without a prior/average supporting fact can't compare → declines.
        self.assertIsNone(compose_comparison({"fact": {"value": 5}, "supporting": {}},
                                             self.user, kind="prior"))


class ConversationObjectCompletenessTests(SimpleTestCase):
    """FUTURE RULE: a fact's declared follow-ups must be backed by the supporting
    facts they need. A Conversation Object is incomplete otherwise."""

    _VALID_PROVIDER_KEYS = None

    def _valid_keys(self):
        if self._VALID_PROVIDER_KEYS is None:
            from apps.ai.cos_services.health_facts import _DAY_FACT_KEYS, _FACT_MAP
            from apps.ai.cos_services.execution_facts import EXECUTION_FACT_KEYS
            type(self)._VALID_PROVIDER_KEYS = (set(_FACT_MAP) | set(_DAY_FACT_KEYS)
                                               | set(EXECUTION_FACT_KEYS))
        return self._VALID_PROVIDER_KEYS

    def test_every_object_is_internally_complete(self):
        for key, sp in CO.CONVERSATION_OBJECTS.items():
            sup_labels = {label for label, _, _ in sp.get("supporting", ())}
            follows = sp.get("follows", ())
            # A comparison follow-up requires a comparison supporting fact.
            if CO.COMPARISON in follows:
                self.assertTrue({"prior", "average"} & sup_labels,
                                f"{key}: declares COMPARISON but no prior/average supporting fact")
            # A meals follow-up requires a meals supporting fact.
            if CO.SUPPORTING_MEALS in follows:
                self.assertIn("meals", sup_labels,
                              f"{key}: declares SUPPORTING_MEALS but no meals supporting fact")

    def test_supporting_provider_keys_are_real_facts(self):
        valid = self._valid_keys()
        for key, sp in CO.CONVERSATION_OBJECTS.items():
            for label, source, provider_key in sp.get("supporting", ()):
                self.assertIn(provider_key, valid,
                              f"{key}: supporting '{label}' → unknown fact '{provider_key}'")
