# ==============================================================================
# File: apps/ai/tests/test_conductor_2b.py
# Description: THE CONDUCTOR — Step 2b. The Classifier becomes AUTHORITATIVE for the ONE
#   speech act Step 2a proved in production: META at HIGH confidence (a critique of Beth's
#   guidance). Such a turn is now dispatched to the repair handler ahead of the keyword
#   lanes that were mis-owning it. Scope is exactly one speech act — every other
#   classification stays shadow (record-only). If repair yields nothing, routing falls
#   through unchanged.
# ==============================================================================
from unittest import mock
import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"
_NOW = "apps.core.utils.get_user_now"
_EVENING = datetime.datetime(2026, 7, 3, 19, 30, tzinfo=datetime.timezone.utc)


def _mkuser(email):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class AuthoritativeMetaTests(TestCase):
    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.u = _mkuser("conductor2b@example.com")
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)

    def _route(self, msg):
        from apps.ai.chatgpt_cos.lanes import route_message
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch(_C, side_effect=RuntimeError("no llm")), \
             mock.patch(_CT, side_effect=RuntimeError("no tools")), \
             mock.patch(_NOW, return_value=_EVENING):
            res = route_message(self.u, msg, self.conv)
        if res and res.get("answer"):
            AssistantMessage.objects.create(conversation=self.conv, role="assistant",
                                            content=res["answer"])
        return res

    def test_accountability_turn_now_owned_by_repair(self):
        # The production failure — a brand-new conversation critiquing her guidance.
        r = self._route("I noticed you let me slide on Bike Ride/Pickleball, Empty "
                        "Dishwasher, and Journal.")
        self.assertIsNotNone(r)
        self.assertEqual(r["lane"], "conversation_repair")       # not goals / reasoning
        low = r["answer"].lower()
        self.assertIn("you're right", low)                       # she owns it, doesn't deflect
        self.assertNotIn("appear to be slipping", low)           # the old wrong answer is gone

    def test_high_meta_emits_conduct_and_agree_true(self):
        self._route("Good evening")            # a real prior turn → has_prior True next
        msg = "that's not what I meant"
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch(_C, side_effect=RuntimeError("x")), \
             mock.patch(_CT, side_effect=RuntimeError("x")), \
             mock.patch(_NOW, return_value=_EVENING), \
             self.assertLogs("apps.ai.chatgpt_cos", level="INFO") as logs:
            from apps.ai.chatgpt_cos.lanes import route_message
            route_message(self.u, msg, self.conv)
        blob = "\n".join(logs.output)
        self.assertIn("COS_CONDUCT", blob)
        self.assertIn("authoritative=meta", blob)
        # Correctly owned now → the shadow match agrees.
        self.assertIn("expected=meta", blob)
        self.assertIn("agree=True", blob)

    def test_non_meta_is_untouched(self):
        # A greeting is orientation, not meta — the Conductor does NOT intervene; it routes
        # exactly as before (day-continuity / check-in path).
        r = self._route("Good evening")
        self.assertIsNotNone(r)
        self.assertNotEqual(r["lane"], "conversation_repair")

    def test_medium_meta_is_not_force_promoted(self):
        # A bare fact-critique is MEDIUM confidence — 2b promotes only HIGH. It must not be
        # force-routed by the authoritative block (it still routes through the normal path,
        # which handles it via the planner). We assert the authoritative block didn't claim
        # it as `conductor:meta` by checking it isn't logged as an authoritative conduct.
        self._route("Good evening")            # a real prior turn → has_prior True next
        msg = "are you sure?"
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch(_C, side_effect=RuntimeError("x")), \
             mock.patch(_CT, side_effect=RuntimeError("x")), \
             mock.patch(_NOW, return_value=_EVENING), \
             self.assertLogs("apps.ai.chatgpt_cos", level="INFO") as logs:
            from apps.ai.chatgpt_cos.lanes import route_message
            route_message(self.u, msg, self.conv)
        blob = "\n".join(logs.output)
        self.assertNotIn("authoritative=meta", blob)   # medium was NOT promoted
