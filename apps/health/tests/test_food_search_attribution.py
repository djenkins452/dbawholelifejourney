# ==============================================================================
# File: apps/health/tests/test_food_search_attribution.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: A person typing in the food box is a person, not unattended spend
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-08
# ==============================================================================
"""Production, 2026-09-08. Searching "hibachi shrimp" in the Nutrition UI returned nothing.

The trace cleared every suspect in turn: FatSecret credentials present on web, the service
available, authentication succeeding, and FatSecret simply holding no match for that phrase.
The shared authority itself was fine.

The failure was mine, from `f4d08ef5`. That change made an UNCLASSIFIED provider call in
production count as autonomous — correctly, because absence of proof that a human asked is
not proof that one did — and I asserted the human on the chat runtime, the legacy entry
point, the streaming task and the journal seam. I missed this one. So when nothing matched,
the AI estimation tier was refused as unattended spend, `_estimate_with_ai` swallowed the
refusal, and autocomplete answered with an empty list. The person searching looked like
nobody at all.

No provider is called in this file; the estimator is mocked throughout.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.ai import llm_admission as adm
from apps.ai.llm_accounting import TRAFFIC_PRODUCTION, llm_traffic_context

User = get_user_model()


def _onboarded(email):
    """A signed-in user who has cleared the terms gate, or every request is a redirect."""
    from django.conf import settings

    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password="pw")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    prefs = getattr(user, "preferences", None)
    if prefs is not None:
        prefs.has_completed_onboarding = True
        prefs.save()
    return user


class SearchAttributionTests(TestCase):
    def setUp(self):
        self.user = _onboarded("fsa@contract.test")
        self.client.force_login(self.user)
        self.url = reverse("health:food_search_api")

    def _search(self, q="a food nobody has", estimate="1"):
        """Runs the real view; captures how the AI tier was classified when reached.

        `estimate=1` because ordinary autocomplete no longer reaches the paid tier at all
        (2026-09-08) — the attribution being tested here is what happens when a person
        explicitly asks for the estimate.
        """
        seen = {}

        def _estimate(*a, **kw):
            seen["autonomous"] = adm.current_workload_is_autonomous(adm.ENV_PRODUCTION)
            from apps.ai.llm_accounting import current_traffic_class
            seen["traffic"] = current_traffic_class()
            return None

        with mock.patch("apps.health.services.food_search.food_search_service."
                        "_search_local", return_value=[]), \
             mock.patch("apps.health.services.food_search.food_search_service."
                        "_search_fatsecret", return_value=[]), \
             mock.patch("apps.health.services.food_search.food_search_service."
                        "_estimate_with_ai", side_effect=_estimate):
            response = self.client.get(self.url, {"q": q, "estimate": estimate})
        return response, seen

    def test_a_person_searching_is_not_classified_as_unattended_spend(self):
        _response, seen = self._search()
        self.assertIn("autonomous", seen, "the estimation tier was never reached")
        self.assertFalse(seen["autonomous"],
                         "a human's search was refused as autonomous provider work")

    def test_the_turn_declares_itself_a_customers(self):
        _response, seen = self._search()
        self.assertEqual(seen["traffic"], TRAFFIC_PRODUCTION)

    def test_an_outer_classification_is_never_overwritten(self):
        """A certification or diagnostic run must keep its own class through this view."""
        from apps.ai.llm_accounting import TRAFFIC_CERTIFICATION
        with llm_traffic_context(traffic_class=TRAFFIC_CERTIFICATION):
            _response, seen = self._search()
        self.assertEqual(seen["traffic"], TRAFFIC_CERTIFICATION)

    def test_the_search_still_answers_normally(self):
        response, _seen = self._search()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])

    def test_a_local_match_never_reaches_the_paid_tier(self):
        """The cheap path stays cheap: something found means nothing estimated — and an
        ordinary search does not reach it even when nothing is found."""
        from apps.health.services.food_search import FoodSearchResult
        hit = FoodSearchResult(id="local_1", name="Hibachi Shrimp", brand="",
                               source="local", calories=300)
        with mock.patch("apps.health.services.food_search.food_search_service."
                        "_search_local", return_value=[hit]), \
             mock.patch("apps.health.services.food_search.food_search_service."
                        "_estimate_with_ai") as estimate:
            response = self.client.get(self.url, {"q": "hibachi shrimp",
                                                  "estimate": "1"})
        estimate.assert_not_called()
        self.assertEqual(response.json()["results"][0]["name"], "Hibachi Shrimp")


class EveryInteractiveSeamDeclaresItselfTests(TestCase):
    """The list that was incomplete. Adding a provider-calling user-facing surface
    without this assertion is a silent outage, not a visible error."""

    def test_all_known_interactive_seams_assert_production(self):
        import pathlib
        seams = {
            "apps/ai/model_interface/service.py": "generate",
            "apps/ai/personal_assistant.py": "send_message",
            "apps/ai/tasks.py": "send_message_stream",
            "apps/journal/services/journal_conversation.py": "_call",
            "apps/health/views.py": "FoodSearchAPIView",
        }
        for path, marker in seams.items():
            src = pathlib.Path(path).read_text(encoding="utf-8")
            self.assertIn(marker, src)
            self.assertIn("TRAFFIC_PRODUCTION", src,
                          f"{path} calls a provider for a human without saying so")
