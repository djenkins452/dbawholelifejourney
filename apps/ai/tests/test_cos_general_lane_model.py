# ==============================================================================
# File: apps/ai/tests/test_cos_general_lane_model.py
# Description: Differential — "Give me John 3:16" (tool loop, COS_MODEL) SUCCEEDS
#   while "What is Metformin used for?" (general lane) FAILED because the general
#   lane defaulted to OPENAI_MODEL (self.model) instead of COS_MODEL. The two CoS
#   paths must use the SAME model. First divergence: lane → model selection.
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.chatgpt_cos.lanes import _looks_general, general_answer

User = get_user_model()
_CALL_API = "apps.ai.services.ai_service._call_api"


class FirstDivergenceRoutingTests(TestCase):
    """The two questions split at lane selection: John 3:16 is NOT general (→ tool
    loop, COS_MODEL); Metformin IS general (→ general lane)."""

    def test_john_316_is_not_general_metformin_is(self):
        self.assertFalse(_looks_general("Give me John 3:16"),
                         "John 3:16 carries a pronoun → not general → tool loop (COS_MODEL)")
        self.assertTrue(_looks_general("What is Metformin used for?"),
                        "Metformin question → general lane")


class GeneralLaneModelTests(TestCase):
    """The fix: the general lane uses COS_MODEL, the SAME model as the tool loop —
    so it can no longer fail while the tool loop succeeds."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="genmodel@example.com", password="x")

    @override_settings(COS_MODEL="gpt-4o", OPENAI_MODEL="some-broken-model")
    def test_general_lane_passes_cos_model_not_openai_model(self):
        with mock.patch(_CALL_API, return_value="Metformin lowers blood sugar.") as m:
            general_answer(self.user, "What is Metformin used for?")
        self.assertTrue(m.called, "general lane must reach _call_api")
        _, kwargs = m.call_args
        self.assertEqual(kwargs.get("model"), "gpt-4o",
                         "general lane must use COS_MODEL, not OPENAI_MODEL")
        self.assertNotEqual(kwargs.get("model"), "some-broken-model")

    @override_settings(COS_MODEL="cos-model-x", OPENAI_MODEL="other-model")
    def test_general_lane_and_tool_loop_agree_on_model(self):
        # The tool loop already passes COS_MODEL (service.generate); the general
        # lane now does too — the divergence that broke Metformin is gone.
        from django.conf import settings
        with mock.patch(_CALL_API, return_value="ok") as m:
            general_answer(self.user, "What is photosynthesis?")
        _, kwargs = m.call_args
        self.assertEqual(kwargs.get("model"), settings.COS_MODEL)

    def test_general_lane_still_answers_when_model_reachable(self):
        educational = ("Metformin is commonly used to help lower blood sugar in "
                       "people with type 2 diabetes.")
        with mock.patch(_CALL_API, return_value=educational):
            out = general_answer(self.user, "What is Metformin used for?")
        self.assertEqual(out["answer"], educational)
        self.assertNotIn("temporarily unavailable", out["answer"].lower())
