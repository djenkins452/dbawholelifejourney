"""Tests for capture template tags and filters."""

from django.test import TestCase

from apps.capture.templatetags.capture_filters import render_summary, summary_plain_text, format_duration


class RenderSummaryFilterTests(TestCase):
    """Tests for the render_summary template filter."""

    def test_empty_value_returns_empty_string(self):
        """Empty value returns empty string."""
        result = render_summary('')
        self.assertEqual(result, '')

    def test_none_value_returns_empty_string(self):
        """None value returns empty string."""
        result = render_summary(None)
        self.assertEqual(result, '')

    def test_converts_h2_headers(self):
        """## headers are converted to h3 with class."""
        markdown = "## Key Points\nSome content"
        result = render_summary(markdown)
        self.assertIn('<h3 class="summary-section-header">Key Points</h3>', result)

    def test_converts_bold_text(self):
        """**bold** text is converted to <strong>."""
        markdown = "This is **important** text"
        result = render_summary(markdown)
        self.assertIn('<strong>important</strong>', result)

    def test_converts_bullet_lists(self):
        """- bullet lists are converted to <ul><li>."""
        markdown = "- First item\n- Second item"
        result = render_summary(markdown)
        self.assertIn('<ul', result)
        self.assertIn('<li>', result)

    def test_preserves_paragraphs(self):
        """Paragraphs are preserved with class."""
        markdown = "First paragraph.\n\nSecond paragraph."
        result = render_summary(markdown)
        self.assertIn('<p class="summary-paragraph">', result)

    def test_real_summary_format(self):
        """Test with realistic summary format."""
        markdown = """## Overview
The speaker discusses workforce strategy alignment.

## Key Points
- Alignment with clinical goals is crucial
- Total rewards integration needed
- Market competitiveness is key

## Action Items
No specific action items identified."""

        result = render_summary(markdown)

        # Check headers
        self.assertIn('Overview', result)
        self.assertIn('Key Points', result)
        self.assertIn('Action Items', result)

        # Check list items
        self.assertIn('Alignment with clinical goals', result)

        # Should not have raw markdown
        self.assertNotIn('## ', result)


class SummaryPlainTextFilterTests(TestCase):
    """Tests for the summary_plain_text template filter."""

    def test_empty_value_returns_empty_string(self):
        """Empty value returns empty string."""
        result = summary_plain_text('')
        self.assertEqual(result, '')

    def test_removes_headers(self):
        """## headers are removed."""
        markdown = "## Key Points\nSome content"
        result = summary_plain_text(markdown)
        self.assertNotIn('##', result)
        self.assertIn('Key Points', result)

    def test_removes_bold_markers(self):
        """**bold** markers are removed but text preserved."""
        markdown = "This is **important** text"
        result = summary_plain_text(markdown)
        self.assertNotIn('**', result)
        self.assertIn('important', result)

    def test_removes_list_markers(self):
        """- list markers are removed."""
        markdown = "- First item\n- Second item"
        result = summary_plain_text(markdown)
        self.assertNotIn('- ', result)
        self.assertIn('First item', result)


class FormatDurationFilterTests(TestCase):
    """Tests for the format_duration template filter."""

    def test_zero_seconds(self):
        """Zero seconds returns 0:00."""
        self.assertEqual(format_duration(0), "0:00")

    def test_none_returns_zero(self):
        """None returns 0:00."""
        self.assertEqual(format_duration(None), "0:00")

    def test_seconds_only(self):
        """Under a minute shows 0:SS."""
        self.assertEqual(format_duration(45), "0:45")

    def test_minutes_and_seconds(self):
        """Minutes and seconds format correctly."""
        self.assertEqual(format_duration(65), "1:05")
        self.assertEqual(format_duration(125), "2:05")
        self.assertEqual(format_duration(600), "10:00")

    def test_hours_minutes_seconds(self):
        """Hours format as H:MM:SS."""
        self.assertEqual(format_duration(3661), "1:01:01")
        self.assertEqual(format_duration(7200), "2:00:00")

    def test_invalid_value(self):
        """Invalid values return 0:00."""
        self.assertEqual(format_duration("invalid"), "0:00")
        self.assertEqual(format_duration([]), "0:00")
