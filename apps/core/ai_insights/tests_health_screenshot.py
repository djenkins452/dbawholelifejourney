# ==============================================================================
# File: tests_health_screenshot.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for PIE Health Screenshot Interpretation pipeline.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-10
# ==============================================================================
"""
Tests for the PIE Health Screenshot Interpretation module.

Coverage:
  - screenshot_parser: structured extraction (mocked Vision API)
  - sleep_analysis: deterministic analysis with known inputs
  - user_context: data gathering with/without available data
  - cos_context: system prompt injection formatting
  - PIE rule: SleepScreenshotAnalysisRule applies/evaluate
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.ai_insights.health.reference_ranges import (
    MEDICAL_DISCLAIMER,
    SLEEP_DURATION_MAX,
    SLEEP_DURATION_MIN,
    SLEEP_STAGES,
)
from apps.core.ai_insights.health.sleep_analysis import (
    SleepScreenshotAnalysisRule,
    analyze_sleep_data,
)
from apps.users.models import User


# ── Test Data Fixtures ──────────────────────────────────────────────


HEALTHY_SLEEP_PARSED = {
    "screenshot_type": "sleep",
    "sleep_summary": {
        "average_sleep_minutes": 465,  # 7h 45m — healthy
        "average_rem_minutes": 100,    # ~21.5% — in range
        "average_core_minutes": 250,   # ~53.8% — in range
        "average_deep_minutes": 80,    # ~17.2% — in range
        "average_awake_minutes": 20,
    },
    "time_period": "7 days",
    "raw_text": "Sleep 7h 45m average",
}

DEFICIT_SLEEP_PARSED = {
    "screenshot_type": "sleep",
    "sleep_summary": {
        "average_sleep_minutes": 340,  # 5h 40m — severe deficit (< 360)
        "average_rem_minutes": 65,     # ~19.1% — below 20%
        "average_core_minutes": 210,   # ~61.8% — above 60%
        "average_deep_minutes": 38,    # ~11.2% — below 13%
        "average_awake_minutes": 14,
    },
    "time_period": "7 days",
    "raw_text": "Sleep 5h 40m average",
}

MILD_DEFICIT_PARSED = {
    "screenshot_type": "sleep",
    "sleep_summary": {
        "average_sleep_minutes": 400,  # 6h 40m — mild deficit
        "average_rem_minutes": 90,     # ~22.5% — in range
        "average_core_minutes": 215,   # ~53.75% — in range
        "average_deep_minutes": 65,    # ~16.25% — in range
        "average_awake_minutes": 12,
    },
    "time_period": "7 days",
    "raw_text": "Sleep 6h 40m average",
}

RECENT_SLEEP_ONLY = {
    "screenshot_type": "sleep",
    "recent_sleep": {
        "date": "2026-03-10",
        "total_sleep_minutes": 392,
        "rem_minutes": 96,
        "core_minutes": 239,
        "deep_minutes": 57,
        "awake_minutes": 9,
    },
    "time_period": "last night",
    "raw_text": "Last night sleep data",
}

VISION_API_RESPONSE = '{"screenshot_type":"sleep","sleep_summary":{"average_sleep_minutes":395,"average_rem_minutes":87,"average_core_minutes":262,"average_deep_minutes":45,"average_awake_minutes":16},"time_period":"7 days","raw_text":"sample"}'


# ── Sleep Analysis Tests ────────────────────────────────────────────


class SleepAnalysisTests(TestCase):
    """Test the deterministic analyze_sleep_data() function."""

    def test_healthy_sleep_returns_positive(self):
        result = analyze_sleep_data(HEALTHY_SLEEP_PARSED)
        self.assertIsNotNone(result)
        self.assertEqual(result['severity'], 'positive')
        self.assertIn('summary_insight', result)
        self.assertIsInstance(result['observations'], list)
        self.assertTrue(len(result['observations']) > 0)

    def test_severe_deficit_returns_warning(self):
        result = analyze_sleep_data(DEFICIT_SLEEP_PARSED)
        self.assertIsNotNone(result)
        self.assertEqual(result['severity'], 'warning')
        # Should flag duration deficit
        obs_text = ' '.join(result['observations'])
        self.assertIn('below', obs_text.lower())

    def test_mild_deficit_returns_info(self):
        result = analyze_sleep_data(MILD_DEFICIT_PARSED)
        self.assertIsNotNone(result)
        self.assertEqual(result['severity'], 'info')

    def test_none_input_returns_none(self):
        self.assertIsNone(analyze_sleep_data(None))

    def test_empty_dict_returns_none(self):
        self.assertIsNone(analyze_sleep_data({}))

    def test_missing_sleep_data_returns_none(self):
        self.assertIsNone(analyze_sleep_data({"screenshot_type": "sleep"}))

    def test_recent_sleep_fallback(self):
        """Should work with recent_sleep when sleep_summary missing."""
        result = analyze_sleep_data(RECENT_SLEEP_ONLY)
        self.assertIsNotNone(result)
        self.assertIn('summary_insight', result)

    def test_stage_distribution_analysis(self):
        """Stages outside reference range should be flagged."""
        result = analyze_sleep_data(DEFICIT_SLEEP_PARSED)
        obs_text = ' '.join(result['observations'])
        # Deep at ~11.1% — below 13% min
        self.assertIn('Deep', obs_text)
        self.assertIn('below', obs_text.lower())

    def test_cycle_completion(self):
        """360 min / 90 = 4.0 cycles — should flag."""
        result = analyze_sleep_data(DEFICIT_SLEEP_PARSED)
        obs_text = ' '.join(result['observations'])
        self.assertIn('cycle', obs_text.lower())

    def test_healthy_stages_not_flagged_as_problems(self):
        """When all stages are in range, no 'below' language."""
        result = analyze_sleep_data(HEALTHY_SLEEP_PARSED)
        for obs in result['observations']:
            if 'REM' in obs or 'Deep' in obs or 'Core' in obs:
                self.assertNotIn('below the typical', obs)

    def test_recommendation_always_present(self):
        for data in [HEALTHY_SLEEP_PARSED, DEFICIT_SLEEP_PARSED, MILD_DEFICIT_PARSED]:
            result = analyze_sleep_data(data)
            self.assertTrue(
                len(result['recommendation']) > 0,
                f"Recommendation missing for {data['sleep_summary'].get('average_sleep_minutes', 'N/A')} min",
            )

    def test_medical_disclaimer_included(self):
        result = analyze_sleep_data(HEALTHY_SLEEP_PARSED)
        self.assertEqual(result['medical_disclaimer'], MEDICAL_DISCLAIMER)

    def test_evidence_dict_present(self):
        result = analyze_sleep_data(HEALTHY_SLEEP_PARSED)
        evidence = result['evidence']
        self.assertEqual(evidence['total_minutes'], 465)
        self.assertIn('cycles', evidence)
        self.assertIn('duration_status', evidence)
        self.assertIn('stage_analysis', evidence)


# ── User Context Connections ────────────────────────────────────────


class SleepAnalysisUserContextTests(TestCase):
    """Test user context connections in sleep analysis."""

    def test_wake_time_implication(self):
        ctx = {'wake_time': '05:00'}
        result = analyze_sleep_data(DEFICIT_SLEEP_PARSED, ctx)
        impl_text = ' '.join(result['implications'])
        self.assertIn('05:00', impl_text)
        self.assertIn('lights out', impl_text.lower())

    def test_no_wake_implication_for_healthy_sleep(self):
        ctx = {'wake_time': '06:00'}
        result = analyze_sleep_data(HEALTHY_SLEEP_PARSED, ctx)
        impl_text = ' '.join(result.get('implications', []))
        self.assertNotIn('lights out', impl_text.lower())

    def test_active_user_deep_sleep_warning(self):
        ctx = {'activity_level': 'very_active'}
        result = analyze_sleep_data(DEFICIT_SLEEP_PARSED, ctx)
        impl_text = ' '.join(result['implications'])
        self.assertIn('recovery', impl_text.lower())

    def test_weight_goal_implication(self):
        ctx = {'has_weight_goal': True}
        result = analyze_sleep_data(DEFICIT_SLEEP_PARSED, ctx)
        impl_text = ' '.join(result['implications'])
        self.assertIn('insulin', impl_text.lower())

    def test_insulin_health_fact(self):
        ctx = {'health_facts': ['Type 2 diabetes']}
        result = analyze_sleep_data(DEFICIT_SLEEP_PARSED, ctx)
        impl_text = ' '.join(result['implications'])
        self.assertIn('insulin sensitivity', impl_text.lower())

    def test_health_goal_reference(self):
        ctx = {'health_goals': ['Improve sleep quality']}
        result = analyze_sleep_data(DEFICIT_SLEEP_PARSED, ctx)
        impl_text = ' '.join(result['implications'])
        self.assertIn('Improve sleep quality', impl_text)

    def test_empty_user_context_still_works(self):
        result = analyze_sleep_data(DEFICIT_SLEEP_PARSED, {})
        self.assertIsNotNone(result)
        # Should still have observations and recommendation
        self.assertTrue(len(result['observations']) > 0)
        self.assertTrue(len(result['recommendation']) > 0)


# ── Screenshot Parser Tests ─────────────────────────────────────────


class ScreenshotParserTests(TestCase):
    """Test parse_health_screenshot with mocked Vision API."""

    @patch('apps.core.ai_insights.health.screenshot_parser.settings')
    @patch('apps.core.ai_insights.health.screenshot_parser._get_client')
    def test_successful_sleep_parse(self, mock_get_client, mock_settings):
        mock_settings.OPENAI_API_KEY = 'test-key'
        mock_settings.OPENAI_VISION_MODEL = 'gpt-4o'

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = VISION_API_RESPONSE
        mock_response.usage = MagicMock(prompt_tokens=500, completion_tokens=100)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        from apps.core.ai_insights.health.screenshot_parser import (
            parse_health_screenshot,
        )
        result = parse_health_screenshot('base64data', 'image/jpeg')

        self.assertIsNotNone(result)
        self.assertEqual(result['screenshot_type'], 'sleep')
        self.assertEqual(result['sleep_summary']['average_sleep_minutes'], 395)

    @patch('apps.core.ai_insights.health.screenshot_parser.settings')
    @patch('apps.core.ai_insights.health.screenshot_parser._get_client')
    def test_unknown_type_returns_none(self, mock_get_client, mock_settings):
        mock_settings.OPENAI_API_KEY = 'test-key'
        mock_settings.OPENAI_VISION_MODEL = 'gpt-4o'

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"screenshot_type":"unknown"}'
        mock_response.usage = MagicMock(prompt_tokens=500, completion_tokens=10)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        from apps.core.ai_insights.health.screenshot_parser import (
            parse_health_screenshot,
        )
        result = parse_health_screenshot('base64data', 'image/jpeg')
        self.assertIsNone(result)

    @patch('apps.core.ai_insights.health.screenshot_parser.settings')
    @patch('apps.core.ai_insights.health.screenshot_parser._get_client')
    def test_markdown_fences_stripped(self, mock_get_client, mock_settings):
        mock_settings.OPENAI_API_KEY = 'test-key'
        mock_settings.OPENAI_VISION_MODEL = 'gpt-4o'

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '```json\n' + VISION_API_RESPONSE + '\n```'
        )
        mock_response.usage = MagicMock(prompt_tokens=500, completion_tokens=100)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        from apps.core.ai_insights.health.screenshot_parser import (
            parse_health_screenshot,
        )
        result = parse_health_screenshot('base64data', 'image/jpeg')
        self.assertIsNotNone(result)
        self.assertEqual(result['screenshot_type'], 'sleep')

    @patch('apps.core.ai_insights.health.screenshot_parser.settings')
    @patch('apps.core.ai_insights.health.screenshot_parser._get_client')
    def test_invalid_json_returns_none(self, mock_get_client, mock_settings):
        mock_settings.OPENAI_API_KEY = 'test-key'
        mock_settings.OPENAI_VISION_MODEL = 'gpt-4o'

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = 'This is not JSON'
        mock_response.usage = MagicMock(prompt_tokens=500, completion_tokens=10)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        from apps.core.ai_insights.health.screenshot_parser import (
            parse_health_screenshot,
        )
        result = parse_health_screenshot('base64data', 'image/jpeg')
        self.assertIsNone(result)

    @patch('apps.core.ai_insights.health.screenshot_parser.settings')
    @patch('apps.core.ai_insights.health.screenshot_parser._get_client')
    def test_api_exception_returns_none(self, mock_get_client, mock_settings):
        mock_settings.OPENAI_API_KEY = 'test-key'
        mock_settings.OPENAI_VISION_MODEL = 'gpt-4o'

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API down")
        mock_get_client.return_value = mock_client

        from apps.core.ai_insights.health.screenshot_parser import (
            parse_health_screenshot,
        )
        result = parse_health_screenshot('base64data', 'image/jpeg')
        self.assertIsNone(result)

    def test_no_api_key_returns_none(self):
        from apps.core.ai_insights.health.screenshot_parser import (
            parse_health_screenshot,
        )
        with patch('apps.core.ai_insights.health.screenshot_parser.settings') as mock_settings:
            mock_settings.OPENAI_API_KEY = None
            result = parse_health_screenshot('base64data', 'image/jpeg')
            self.assertIsNone(result)


# ── User Context Tests ──────────────────────────────────────────────


class HealthUserContextTests(TestCase):
    """Test get_health_user_context data gathering."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="healthctx@example.com", password="testpass123",
        )

    def test_returns_dict_with_expected_keys(self):
        from apps.core.ai_insights.health.user_context import (
            get_health_user_context,
        )
        ctx = get_health_user_context(self.user)
        self.assertIsInstance(ctx, dict)
        self.assertIn('activity_level', ctx)
        self.assertIn('has_weight_goal', ctx)
        self.assertIn('recent_sleep_avg_minutes', ctx)
        self.assertIn('wake_time', ctx)
        self.assertIn('health_goals', ctx)
        self.assertIn('health_facts', ctx)

    def test_defaults_for_empty_user(self):
        """User with no health data should get safe defaults."""
        from apps.core.ai_insights.health.user_context import (
            get_health_user_context,
        )
        ctx = get_health_user_context(self.user)
        self.assertIsNone(ctx['activity_level'])
        self.assertFalse(ctx['has_weight_goal'])
        self.assertIsNone(ctx['recent_sleep_avg_minutes'])
        self.assertIsNone(ctx['wake_time'])
        self.assertEqual(ctx['health_goals'], [])
        self.assertEqual(ctx['health_facts'], [])

    def test_never_raises(self):
        """Should return safe defaults even with invalid user."""
        from apps.core.ai_insights.health.user_context import (
            get_health_user_context,
        )
        # Fake user without proper DB entries
        fake_user = MagicMock()
        fake_user.id = 99999
        ctx = get_health_user_context(fake_user)
        self.assertIsInstance(ctx, dict)


# ── CoS Context Injection Tests ─────────────────────────────────────


class CosContextInjectionTests(TestCase):
    """Test that health analysis is properly injected into CoS."""

    def test_health_analysis_appears_in_injection(self):
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection,
        )
        analysis = {
            'summary_insight': 'Your sleep looks healthy.',
            'observations': [
                'Total sleep of 7h 45m is within range',
                'REM at 21% is optimal',
            ],
            'implications': ['Good recovery for your training'],
            'recommendation': 'Keep your current schedule.',
            'medical_disclaimer': MEDICAL_DISCLAIMER,
        }
        context = {'health_screenshot_analysis': analysis}
        result = format_cos_system_injection(context)

        self.assertIn('Summary:', result)
        self.assertIn('Your sleep looks healthy', result)
        self.assertIn('7h 45m', result)
        self.assertIn('Keep your current schedule', result)
        self.assertIn('REASONING', result)

    def test_no_health_analysis_no_section(self):
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection,
        )
        result = format_cos_system_injection({})
        self.assertNotIn('HEALTH SCREENSHOT ANALYSIS', result)


# ── PIE Rule Tests ──────────────────────────────────────────────────


class SleepScreenshotRuleTests(TestCase):
    """Test the SleepScreenshotAnalysisRule PIE rule."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="pierule@example.com", password="testpass123",
        )
        self.rule = SleepScreenshotAnalysisRule()

    def test_applies_to_sleep_screenshot_event(self):
        event = {
            'action': 'health_screenshot',
            'context': {'screenshot_type': 'sleep'},
        }
        self.assertTrue(self.rule.applies(self.user, event))

    def test_does_not_apply_to_non_health_event(self):
        event = {'action': 'record_created', 'module': 'health'}
        self.assertFalse(self.rule.applies(self.user, event))

    def test_does_not_apply_to_non_sleep_screenshot(self):
        event = {
            'action': 'health_screenshot',
            'context': {'screenshot_type': 'heart_rate'},
        }
        self.assertFalse(self.rule.applies(self.user, event))

    def test_evaluate_returns_insight(self):
        event = {
            'action': 'health_screenshot',
            'context': {
                'screenshot_type': 'sleep',
                'parsed_data': HEALTHY_SLEEP_PARSED,
                'user_context': {},
            },
        }
        results = self.rule.evaluate(self.user, event)
        self.assertEqual(len(results), 1)
        insight = results[0]
        self.assertIn('title', insight)
        self.assertIn('message', insight)
        self.assertIn('severity', insight)
        self.assertIn('confidence_score', insight)
        self.assertIn('dedupe_key', insight)
        self.assertEqual(insight['severity'], 'positive')

    def test_evaluate_with_deficit_returns_warning(self):
        event = {
            'action': 'health_screenshot',
            'context': {
                'screenshot_type': 'sleep',
                'parsed_data': DEFICIT_SLEEP_PARSED,
                'user_context': {},
            },
        }
        results = self.rule.evaluate(self.user, event)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['severity'], 'warning')

    def test_evaluate_empty_data_returns_empty(self):
        event = {
            'action': 'health_screenshot',
            'context': {
                'screenshot_type': 'sleep',
                'parsed_data': {},
                'user_context': {},
            },
        }
        results = self.rule.evaluate(self.user, event)
        self.assertEqual(len(results), 0)

    def test_rule_registered_in_registry(self):
        from apps.core.ai_insights.rule_registry import get_rules
        rules = get_rules()
        rule_names = [r.rule_name for r in rules]
        self.assertIn('sleep_screenshot_analysis', rule_names)


# ── Integration Test ────────────────────────────────────────────────


class HealthScreenshotIntegrationTest(TestCase):
    """End-to-end test: parsed data → analysis → CoS injection."""

    def test_full_pipeline_mock(self):
        """Simulate full pipeline from parsed data to CoS output."""
        from apps.core.ai_insights.health.sleep_analysis import (
            analyze_sleep_data,
        )
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection,
        )

        # Step 1: Analyze (parser is mocked, use pre-parsed data)
        analysis = analyze_sleep_data(
            DEFICIT_SLEEP_PARSED,
            user_context={
                'wake_time': '05:00',
                'activity_level': 'very_active',
                'has_weight_goal': True,
            },
        )

        # Step 2: Verify analysis
        self.assertIsNotNone(analysis)
        self.assertEqual(analysis['severity'], 'warning')
        self.assertTrue(len(analysis['implications']) > 0)

        # Step 3: Inject into CoS
        cos_ctx = {'health_screenshot_analysis': analysis}
        injection = format_cos_system_injection(cos_ctx)

        # Step 4: Verify CoS output
        self.assertIn('Summary:', injection)
        self.assertIn(analysis['summary_insight'], injection)
        self.assertIn(analysis['recommendation'], injection)
        self.assertIn('REASONING', injection)
