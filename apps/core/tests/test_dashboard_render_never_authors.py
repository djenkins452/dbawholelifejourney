# ==============================================================================
# File: apps/core/tests/test_dashboard_render_never_authors.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: A page render is not a proactive event and can never author one
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-14
# ==============================================================================
"""Production, 2026-09-14: 29 proactive authoring attempts in eight minutes — one per
dashboard render.

`build_cos_structured_output` was written deterministic ("NO LLM calls"). When the
WLJ-authored renderer was retired, `author_checkin` — a provider call — was dropped into it,
and none of its five consumers changed: the dashboard opening message, the session-start
briefing, the legacy chat turn's "LOCKED CoS STATE" injection, and two "the LLM is
unavailable" fallbacks. Every one became a proactive authoring trigger keyed on a request.

Proactive authoring has exactly one lifecycle: the scheduled/event producers in
`proactive_checkins.py`. A page render is not in it. These tests make that structural.

No provider is called anywhere here; every path that could reach one is asserted not to.
"""

from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


def _onboarded(email):
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password="pw")
    TermsAcceptance.objects.create(
        user=user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    prefs = getattr(user, "preferences", None)
    if prefs is not None:
        prefs.has_completed_onboarding = True
        prefs.proactive_assistance_enabled = True      # the preference is ON, as in prod
        prefs.save()
    return user


class StructuredOutputIsDeterministicTests(TestCase):
    def setUp(self):
        self.user = _onboarded("so@contract.test")

    def test_the_structured_output_never_authors(self):
        from apps.ai.beth_checkin_renderer import build_cos_structured_output
        with mock.patch("apps.ai.checkin_author.author_checkin") as author, \
             mock.patch("apps.ai.services.ai_service._call_api") as call:
            out = build_cos_structured_output(self.user)
        author.assert_not_called()
        call.assert_not_called()
        self.assertEqual(out["rendered_text"], "")
        self.assertIn("do_now", out)

    def test_it_still_carries_the_facts(self):
        from apps.ai.beth_checkin_renderer import build_cos_structured_output
        with mock.patch("apps.core.execution.decision_authority.current_action",
                        return_value={"primary_action": {"title": "Prayer Time"}}):
            out = build_cos_structured_output(self.user)
        self.assertEqual(out["sequence"], ["Prayer Time"])
        self.assertEqual(out["next_action"]["title"], "Prayer Time")


class RepeatedRendersTests(TestCase):
    """The production sequence: open, refresh, refresh, refresh…"""

    def setUp(self):
        self.user = _onboarded("render@contract.test")
        self.client.force_login(self.user)

    def test_repeated_opening_renders_create_no_authoring_attempts(self):
        from apps.ai.models import ToolCallLog
        url = reverse("ai:api_opening")
        with mock.patch("apps.ai.checkin_author.author_checkin") as author, \
             mock.patch("apps.ai.services.ai_service._call_api") as call:
            for _ in range(5):
                self.client.get(url)
        author.assert_not_called()
        call.assert_not_called()
        self.assertEqual(ToolCallLog.objects.filter(user=self.user, kind="checkin").count(),
                         0, "a page render wrote a proactive decision row")

    def test_the_state_guard_blocks_without_authoring(self):
        from apps.ai.beth_checkin_renderer import guard_llm_output
        with mock.patch("apps.ai.checkin_author.author_checkin") as author:
            out = guard_llm_output("You completed all your tasks today!", self.user)
        author.assert_not_called()
        self.assertEqual(out, "")

    def test_a_clean_reply_passes_the_guard_untouched(self):
        from apps.ai.beth_checkin_renderer import guard_llm_output
        self.assertEqual(guard_llm_output("Here is the answer.", self.user),
                         "Here is the answer.")


class OnlyTheLifecycleAuthorsTests(TestCase):
    """Structural: `author_checkin` is reachable from the proactive producers and nowhere
    a request could trigger it."""

    def test_no_request_path_module_reaches_the_author(self):
        import pathlib
        forbidden = (
            "apps/ai/views.py", "apps/ai/greeting_service.py",
            "apps/dashboard/views.py", "apps/ai/personal_assistant.py",
        )
        for path in forbidden:
            src = pathlib.Path(path).read_text(encoding="utf-8")
            self.assertNotIn("author_checkin", src,
                             f"{path} can author a proactive check-in from a request")

    def test_the_structured_output_body_does_not_reference_the_author(self):
        """Asserts on CODE — the docstring names the author to explain why it is gone."""
        import ast
        import inspect
        import textwrap

        from apps.ai import beth_checkin_renderer as r
        tree = ast.parse(textwrap.dedent(inspect.getsource(r.build_cos_structured_output)))
        fn = tree.body[0]
        body = fn.body[1:] if ast.get_docstring(fn) else fn.body
        code = "\n".join(ast.unparse(n) for n in body)
        self.assertNotIn("author_checkin", code)

    def test_the_lifecycle_entry_points_still_author(self):
        """The fix removes request-path authoring, not authoring."""
        import inspect

        from apps.ai import beth_checkin_renderer as r
        for fn in (r.render_checkin_for_time, r.render_morning_checkin,
                   r.render_daily_briefing):
            self.assertIn("author_checkin", inspect.getsource(fn))

    def test_the_scheduled_producers_still_reach_the_author(self):
        import pathlib
        src = pathlib.Path("apps/ai/proactive_checkins.py").read_text(encoding="utf-8")
        self.assertIn("render_checkin_for_time", src)
        self.assertIn("author_checkin", src)

