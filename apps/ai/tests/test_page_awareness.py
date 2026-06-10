"""Beth Page Awareness v1 — gated, humble, anti-hallucination prompt instruction.

The instruction must:
  - reference page context as "what WLJ provided", never "I can see your screen"
  - be confident + specific ONLY when structured content is present
  - be honest (location-only) when page content didn't come through
  - always carry the "never claim what isn't listed" guard
  - return '' when there's no page_context (so it can't affect anything else)
"""

import types
from unittest import mock

from django.test import SimpleTestCase

from apps.ai.personal_assistant import (
    _build_page_awareness_instruction as build,
    _lookup_journey_scripture,
)


class PageAwarenessTests(SimpleTestCase):
    FAITH_FULL = {
        "url": "/faith/reading-plans/progress/12",
        "module": "faith",
        "page_title": "Today's Reading",
        "page_content": {
            "type": "reading_plan_progress",
            "scriptures": ["Exodus 14:5-31"],
            "scripture_text": "And it was told the king of Egypt that the people fled...",
        },
    }
    FAITH_LOCATION_ONLY = {
        "url": "/faith/reading-plans/progress/12",
        "module": "faith",
        "page_title": "Today's Reading",
        "page_content": None,  # DOM extraction failed / iOS
    }
    WEIGHT_PAGE = {
        "module": "health",
        "page_title": "Weight",
        "page_content": {"type": "health", "current_weight": 289.9},
    }

    def test_no_page_context_is_empty(self):
        self.assertEqual(build(None), "")
        self.assertEqual(build({}), "")

    def test_prohibits_visual_screen_claim(self):
        # The phrase appears ONLY inside the prohibition ("NEVER 'I can see your
        # screen'") — Beth is told not to say it.
        for ctx in (self.FAITH_FULL, self.FAITH_LOCATION_ONLY, self.WEIGHT_PAGE):
            out = build(ctx).lower()
            self.assertIn('never "i can see your screen"', out)

    def test_humility_framing_present(self):
        out = build(self.FAITH_FULL).lower()
        self.assertTrue(
            "page context wlj provided" in out or "you're on the" in out)

    def test_always_carries_anti_hallucination_guard(self):
        for ctx in (self.FAITH_FULL, self.FAITH_LOCATION_ONLY, self.WEIGHT_PAGE):
            out = build(ctx).lower()
            self.assertIn("never claim to see anything not listed", out)

    def test_faith_full_is_confident_and_specific(self):
        out = build(self.FAITH_FULL)
        self.assertIn("Exodus 14:5-31", out)            # confident example
        self.assertIn("if the user asks whether", out.lower())  # answer the meta-question

    def test_faith_location_only_is_honest_partial(self):
        out = build(self.FAITH_LOCATION_ONLY).lower()
        self.assertIn("you're on the today's reading", out)
        self.assertIn("don't see the scripture content", out)
        # Must NOT use the confident scripture example when content is missing.
        self.assertNotIn("i can see today's reading is", out)

    def test_weight_page_uses_canonical_figures_note(self):
        out = build(self.WEIGHT_PAGE).lower()
        # has_content True via current_weight -> confident branch
        self.assertIn("canonical figures", out)

    def test_location_only_for_unknown_module(self):
        out = build({"module": "", "page_title": "", "page_content": None}).lower()
        self.assertIn("this page", out)
        self.assertIn("don't see the page details", out)


class JourneyScriptureLookupTests(SimpleTestCase):
    """/faith/journey/today/ — the client extractor has no branch for this route,
    so scripture comes from a server-side lookup (mirrors reading-plans)."""

    def test_no_active_journey_returns_empty(self):
        with mock.patch("apps.faith.journey.services.get_active_journey", return_value=None):
            refs, text = _lookup_journey_scripture(object())
        self.assertEqual(refs, [])
        self.assertEqual(text, "")

    def test_parses_scripture_refs_and_blocks(self):
        day = types.SimpleNamespace(
            scripture_refs=["Exodus 14:5-31"],
            scripture_content={"translation": "WEB",
                               "blocks": [{"text": "And it was told the king..."},
                                          {"text": "So he made ready his chariot."}]})
        with mock.patch("apps.faith.journey.services.get_active_journey", return_value=object()), \
             mock.patch("apps.faith.journey.services.get_current_day", return_value=day):
            refs, text = _lookup_journey_scripture(object())
        self.assertEqual(refs, ["Exodus 14:5-31"])
        self.assertIn("And it was told the king", text)
        self.assertIn("made ready his chariot", text)

    def test_lookup_never_raises(self):
        with mock.patch("apps.faith.journey.services.get_active_journey",
                        side_effect=RuntimeError("boom")):
            refs, text = _lookup_journey_scripture(object())
        self.assertEqual((refs, text), ([], ""))

    def test_both_paths_wire_journey_lookup(self):
        # Parity: both prompt builders must perform the journey scripture lookup.
        import inspect
        from apps.ai.personal_assistant import PersonalAssistant
        fast = inspect.getsource(PersonalAssistant._build_fast_context)
        full = inspect.getsource(PersonalAssistant._generate_response)
        self.assertIn("_lookup_journey_scripture", fast)
        self.assertIn("_lookup_journey_scripture", full)


class StreamingParityTests(SimpleTestCase):
    """Both prompt-assembly paths must inject page awareness. The web UI streams
    via _build_fast_context; if only _generate_response had it, awareness would
    never activate on web (the v1 regression we just root-caused)."""

    def test_both_prompt_paths_inject_awareness(self):
        import inspect
        from apps.ai.personal_assistant import PersonalAssistant
        fast = inspect.getsource(PersonalAssistant._build_fast_context)
        full = inspect.getsource(PersonalAssistant._generate_response)
        self.assertIn("_build_page_awareness_instruction", fast,
                      "fast/streaming path lost the page-awareness instruction")
        self.assertIn("_build_page_awareness_instruction", full,
                      "non-streaming path lost the page-awareness instruction")
