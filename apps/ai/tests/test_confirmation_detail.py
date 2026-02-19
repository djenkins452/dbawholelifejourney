# ==============================================================================
# File: test_confirmation_detail.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for ActionResult.confirmation_detail field and
#              ActionHandler._build_confirmation helper
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-18
# ==============================================================================

from django.test import TestCase

from apps.ai.intent_service import ActionResult
from apps.ai.action_handlers import ActionHandler
from apps.users.models import User


class TestActionResultConfirmationDetail(TestCase):
    """Tests for the confirmation_detail field on ActionResult."""

    def test_action_result_has_confirmation_detail_field(self):
        """ActionResult dataclass should have a confirmation_detail attribute."""
        result = ActionResult(success=True, message="Test")
        self.assertTrue(hasattr(result, 'confirmation_detail'))

    def test_action_result_confirmation_detail_defaults_to_none(self):
        """confirmation_detail should default to None when not provided."""
        result = ActionResult(success=True, message="Logged something")
        self.assertIsNone(result.confirmation_detail)

    def test_action_result_with_confirmation_detail(self):
        """ActionResult should accept a full confirmation_detail dict."""
        detail = {
            'what': '72 BPM (resting)',
            'where': 'Health > Heart Rate',
            'trend': 'up 3 BPM from last week',
            'risk': 'elevated resting heart rate',
        }
        result = ActionResult(
            success=True,
            message="Logged heart rate",
            confirmation_detail=detail,
        )
        self.assertEqual(result.confirmation_detail, detail)
        self.assertEqual(result.confirmation_detail['what'], '72 BPM (resting)')
        self.assertEqual(result.confirmation_detail['where'], 'Health > Heart Rate')
        self.assertEqual(result.confirmation_detail['trend'], 'up 3 BPM from last week')
        self.assertEqual(result.confirmation_detail['risk'], 'elevated resting heart rate')

    def test_confirmation_detail_without_optional_fields(self):
        """confirmation_detail should work with only what and where (no trend, no risk)."""
        detail = {
            'what': '120/80 mmHg',
            'where': 'Health > Blood Pressure',
        }
        result = ActionResult(
            success=True,
            message="Logged blood pressure",
            confirmation_detail=detail,
        )
        self.assertEqual(result.confirmation_detail['what'], '120/80 mmHg')
        self.assertEqual(result.confirmation_detail['where'], 'Health > Blood Pressure')
        self.assertNotIn('trend', result.confirmation_detail)
        self.assertNotIn('risk', result.confirmation_detail)


class TestBuildConfirmationHelper(TestCase):
    """Tests for ActionHandler._build_confirmation helper method."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
        )
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.save()
        self.handler = ActionHandler(self.user)

    def test_build_confirmation_helper_exists(self):
        """ActionHandler should have a _build_confirmation method."""
        self.assertTrue(hasattr(self.handler, '_build_confirmation'))
        self.assertTrue(callable(self.handler._build_confirmation))

    def test_build_confirmation_returns_dict(self):
        """_build_confirmation should return a dict with what, where, trend, risk keys."""
        result = self.handler._build_confirmation(
            what='180 lbs',
            where='Health > Weight',
            trend='down 2 lbs this week',
            risk='approaching target',
        )
        self.assertIsInstance(result, dict)
        self.assertEqual(result['what'], '180 lbs')
        self.assertEqual(result['where'], 'Health > Weight')
        self.assertEqual(result['trend'], 'down 2 lbs this week')
        self.assertEqual(result['risk'], 'approaching target')
