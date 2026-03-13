# ==============================================================================
# File: test_option_extraction.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for A/B/C option extraction from LLM response text.
#              Verifies that text-based options are parsed into structured
#              option dicts for rendering as interactive clickable chips.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-13
# ==============================================================================

from django.test import TestCase

from apps.ai.personal_assistant import PersonalAssistant


class TestExtractOptionsFromText(TestCase):
    """Verify A/B/C option patterns are extracted from LLM text."""

    def test_standard_abc_pattern(self):
        """Standard A) B) C) pattern is extracted."""
        text = (
            "You missed your workout. Let's decide:\n"
            "A) Do it now\n"
            "B) Schedule it for later\n"
            "C) Skip it"
        )
        cleaned, options = PersonalAssistant._extract_options_from_text(text)
        self.assertIsNotNone(options)
        self.assertEqual(len(options), 3)
        self.assertEqual(options[0]['key'], 'A')
        self.assertEqual(options[0]['label'], 'Do it now')
        self.assertEqual(options[1]['key'], 'B')
        self.assertEqual(options[1]['label'], 'Schedule it for later')
        self.assertEqual(options[2]['key'], 'C')
        self.assertEqual(options[2]['label'], 'Skip it')
        # Options should be removed from the text
        self.assertNotIn('A)', cleaned)
        self.assertNotIn('B)', cleaned)
        self.assertNotIn('C)', cleaned)
        # Preamble text should remain
        self.assertIn("missed your workout", cleaned)

    def test_dot_notation_pattern(self):
        """A. B. C. notation is also extracted."""
        text = (
            "How would you like to proceed?\n"
            "A. Mark it complete\n"
            "B. Reschedule to tomorrow\n"
        )
        cleaned, options = PersonalAssistant._extract_options_from_text(text)
        self.assertIsNotNone(options)
        self.assertEqual(len(options), 2)
        self.assertEqual(options[0]['label'], 'Mark it complete')
        self.assertEqual(options[1]['label'], 'Reschedule to tomorrow')

    def test_bold_markdown_pattern(self):
        """**A)** bold notation is extracted."""
        text = (
            "Ready to tackle this?\n"
            "**A)** Start now\n"
            "**B)** Defer to evening\n"
            "**C)** Convert to lighter version\n"
        )
        cleaned, options = PersonalAssistant._extract_options_from_text(text)
        self.assertIsNotNone(options)
        self.assertEqual(len(options), 3)
        self.assertEqual(options[0]['label'], 'Start now')

    def test_no_options_returns_none(self):
        """Text without option patterns returns (text, None)."""
        text = "Good morning! Here's your schedule for today."
        cleaned, options = PersonalAssistant._extract_options_from_text(text)
        self.assertIsNone(options)
        self.assertEqual(cleaned, text)

    def test_single_option_returns_none(self):
        """A single option line is not enough — need at least 2."""
        text = "Try this:\nA) Do it now\n"
        cleaned, options = PersonalAssistant._extract_options_from_text(text)
        self.assertIsNone(options)

    def test_empty_text_returns_none(self):
        """Empty text returns (text, None)."""
        cleaned, options = PersonalAssistant._extract_options_from_text("")
        self.assertIsNone(options)
        self.assertEqual(cleaned, "")

    def test_none_text_returns_none(self):
        """None text returns (None, None)."""
        cleaned, options = PersonalAssistant._extract_options_from_text(None)
        self.assertIsNone(options)

    def test_first_option_is_primary_style(self):
        """Option A gets 'primary' style, others get 'secondary'."""
        text = "Pick one:\nA) First\nB) Second\nC) Third\n"
        _, options = PersonalAssistant._extract_options_from_text(text)
        self.assertEqual(options[0]['style'], 'primary')
        self.assertEqual(options[1]['style'], 'secondary')
        self.assertEqual(options[2]['style'], 'secondary')

    def test_options_have_acknowledge_action(self):
        """General response options have 'acknowledge' action type."""
        text = "Choose:\nA) Yes\nB) No\n"
        _, options = PersonalAssistant._extract_options_from_text(text)
        for opt in options:
            self.assertEqual(opt['action'], 'acknowledge')

    def test_four_options_extracted(self):
        """Up to 4 options (A-D) are supported."""
        text = (
            "How urgent?\n"
            "A) Do it now\n"
            "B) This morning\n"
            "C) This afternoon\n"
            "D) Tomorrow\n"
        )
        _, options = PersonalAssistant._extract_options_from_text(text)
        self.assertIsNotNone(options)
        self.assertEqual(len(options), 4)
        self.assertEqual(options[3]['key'], 'D')
        self.assertEqual(options[3]['label'], 'Tomorrow')

    def test_cleaned_text_preserves_non_option_content(self):
        """The preamble and any text after options is preserved."""
        text = (
            "Here's what I recommend based on your schedule:\n\n"
            "A) Train now — you have a 45-minute window\n"
            "B) Schedule for 5pm\n"
            "C) Skip today\n\n"
            "Let me know!"
        )
        cleaned, options = PersonalAssistant._extract_options_from_text(text)
        self.assertIsNotNone(options)
        self.assertIn("Here's what I recommend", cleaned)
        self.assertNotIn("A)", cleaned)
