"""The Check-in is authored by OpenAI from deterministic truth — the WLJ prose renderer is
retired. Verifies: the envelope carries every fact the renderer used; the public
entrypoints delegate to the OpenAI author; the author degrades to a deterministic FACT (not
prose) when the model is down; no briefing/situation/escalation prose remains in WLJ."""
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

User = get_user_model()

_RENDERER = Path(settings.BASE_DIR) / "apps" / "ai" / "beth_checkin_renderer.py"


class CheckinAuthoringTests(SimpleTestCase):
    @patch("apps.ai.services.ai_service")
    @patch("apps.ai.model_interface.service.ModelInterfaceService.build_standing_context")
    def test_openai_authors_from_the_envelope(self, mock_envelope, mock_ai):
        from apps.ai.checkin_author import author_checkin
        mock_envelope.return_value = {"current_action": {"primary_action": {"title": "Workout"}}}
        mock_ai._call_api.return_value = "You're at your workout time. Go get it."
        user = MagicMock(); user.id = 1
        out = author_checkin(user, phase="morning")
        self.assertEqual(out, "You're at your workout time. Go get it.")
        # The envelope (deterministic truth) was passed to the model.
        system_prompt = mock_ai._call_api.call_args[0][0]
        self.assertIn("DETERMINISTIC TRUTH", system_prompt)
        self.assertIn("Workout", system_prompt)

    @patch("apps.ai.services.ai_service")
    @patch("apps.ai.model_interface.service.ModelInterfaceService.build_standing_context")
    def test_degrades_to_deterministic_fact_not_prose(self, mock_envelope, mock_ai):
        from apps.ai.checkin_author import author_checkin
        mock_envelope.return_value = {}
        mock_ai._call_api.side_effect = Exception("model down")
        with patch("apps.core.execution.decision_authority.current_action_directive",
                   return_value="Next: Workout. Do this now."):
            user = MagicMock(); user.id = 1
            self.assertEqual(author_checkin(user), "Next: Workout. Do this now.")

    @patch("apps.ai.checkin_author.author_checkin")
    def test_public_entrypoints_delegate_to_author(self, mock_author):
        from apps.ai import beth_checkin_renderer as r
        mock_author.return_value = "authored"
        user = MagicMock(); user.id = 1
        self.assertEqual(r.render_checkin_for_time(user), "authored")
        self.assertEqual(r.render_morning_checkin(user), "authored")
        self.assertEqual(r.render_daily_briefing(user), "authored")
        self.assertTrue(mock_author.called)

    def test_renderer_has_no_prose_engine(self):
        """The retired prose/judgment functions must not come back into WLJ."""
        src = _RENDERER.read_text()
        for banned in ("_render_morning", "_build_triage", "compute_escalation_level",
                       "_assess_situation", "_morning_closing", "build_schedule_signals"):
            self.assertNotIn("def " + banned, src,
                             f"retired prose/judgment function {banned} reappeared")

    def test_state_language_guard_still_works(self):
        from apps.ai.beth_checkin_renderer import contains_state_language
        self.assertTrue(contains_state_language("You completed your workout, solid start!"))
        self.assertFalse(contains_state_language("Here is the plan."))


class EnvelopeCompletenessTests(TestCase):
    """Removing the renderer must lose NO truth: every fact it used is in the envelope."""

    @patch("apps.ai.services.ai_service")
    def test_envelope_carries_execution_state_facts(self, _mock_ai):
        from apps.ai.model_interface.service import ModelInterfaceService
        user = User.objects.create_user(email="env@example.com", password="x")
        ctx = ModelInterfaceService(user).build_standing_context()
        # The renderer's day facts now live in the envelope (facts only, no prose).
        self.assertIn("execution_state", ctx)
        self.assertIn("current_action", ctx)
        self.assertIn("missions", ctx)
        es = ctx["execution_state"]
        if isinstance(es, dict) and es.get("status") != "pending":
            for bucket in ("overdue", "due_now", "coming_up", "later", "completed",
                           "timing"):
                self.assertIn(bucket, es)

    @patch("apps.ai.services.ai_service")
    def test_structured_output_facts_from_authority_prose_from_model(self, mock_ai):
        from apps.ai.beth_checkin_renderer import build_cos_structured_output
        mock_ai._call_api.return_value = "Authored check-in."
        user = User.objects.create_user(email="struct@example.com", password="x")
        out = build_cos_structured_output(user)
        self.assertEqual(set(out.keys()),
                         {"do_now", "sequence", "next_action", "rendered_text"})
        self.assertEqual(out["rendered_text"], "Authored check-in.")  # model prose
