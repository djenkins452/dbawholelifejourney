# ==============================================================================
# File: apps/ai/tests/test_prompt_templates_build.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: A prompt that cannot be built is a feature that does not run.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Every system prompt must actually assemble.

On 2026-07-19 a JSON example was added to the intent-recognition prompt:

    log_body_measurements(measurements=[{"metric":"neck","value":16.29,...}])

inside an f-string. Python read `{"metric"` as a replacement field, `:` as the start of
a format spec, and the rest as the spec — `ValueError: Invalid format specifier`. The
prompt could not be built at all.

`recognize_intents` catches broadly and logs "Intent recognition error", so nothing
crashed and nothing complained. Intent recognition simply returned nothing, for six
weeks, and the only evidence was a log line nobody was reading.

These tests build the prompts. That is the whole test — a prompt that raises is a
feature that silently does not run.
"""
import re

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class TheIntentPromptAssemblesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="prompt@example.com",
                                             password="pw" * 8)

    def _service(self):
        from apps.ai.intent_service import IntentService
        return IntentService()

    def test_it_builds_with_a_user(self):
        prompt = self._service()._build_intent_system_prompt(
            user=self.user, page_context=None)
        self.assertGreater(len(prompt), 1000)

    def test_it_builds_without_a_user(self):
        """The no-user path is the one the failing tests exercised."""
        prompt = self._service()._build_intent_system_prompt(user=None,
                                                             page_context=None)
        self.assertGreater(len(prompt), 1000)

    def test_it_builds_with_page_context(self):
        prompt = self._service()._build_intent_system_prompt(
            user=self.user, page_context={"page": "health"})
        self.assertGreater(len(prompt), 1000)

    def test_the_measurement_example_survives_as_readable_json(self):
        """Escaping the braces must not leave doubled ones in what the model reads."""
        prompt = self._service()._build_intent_system_prompt(user=self.user,
                                                             page_context=None)
        line = next(l for l in prompt.split("\n")
                    if "uploaded screenshot showing neck" in l)
        self.assertIn('{"metric":"neck","value":16.29,"unit":"in"}', line)
        self.assertNotIn("{{", line)
        self.assertNotIn("}}", line)

    def test_recognition_does_not_swallow_a_broken_prompt(self):
        """The defect was invisible because the failure was caught and logged.

        The prompt building itself is asserted above; this pins the shape of the bug —
        an exception here becomes a silent empty result, so the prompt must not be able
        to raise in the first place.
        """
        import inspect

        from apps.ai.intent_service import IntentService

        source = inspect.getsource(IntentService.recognize_intents)
        self.assertIn("except", source,
                      "recognition is deliberately forgiving at runtime — which is "
                      "exactly why the prompt must be proven to build in a test")


class NoPromptFStringHidesAJsonExampleTests(TestCase):
    """The same mistake, anywhere else in the prompt builders.

    A literal `{"key": value}` inside an f-string is always this bug. Scanning for it is
    cheaper than waiting for the next feature to go quietly dead.
    """

    #: Modules whose whole job is assembling prompts.
    MODULES = (
        "apps/ai/intent_service.py",
        "apps/ai/model_interface/constitution.py",
    )

    def test_no_unescaped_json_object_inside_an_fstring(self):
        from pathlib import Path

        from django.conf import settings

        offenders = []
        for relative in self.MODULES:
            path = Path(settings.BASE_DIR) / relative
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            # Only f-strings can misread a brace; find them, then look inside.
            for match in re.finditer(r'f"""(.*?)"""', text, re.S):
                body = match.group(1).replace("{{", "\x00").replace("}}", "\x01")
                for field in re.finditer(r'\{([^{}]*)\}', body):
                    expression = field.group(1)
                    # A replacement field is an expression, optionally `!r`/`:spec`.
                    # `{"metric":"neck"...}` is a JSON object pretending to be one.
                    if expression.lstrip().startswith(('"', "'")):
                        line = text[:match.start()].count("\n") + \
                            body[:field.start()].count("\n") + 1
                        offenders.append(f"{relative}:{line} {{{expression[:50]}}}")
        self.assertEqual(
            offenders, [],
            "a JSON example inside an f-string is read as a format field and raises "
            f"ValueError when the prompt is built: {offenders}")
