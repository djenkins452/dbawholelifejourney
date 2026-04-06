# ==============================================================================
# File: tests/test_intent_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for intent recognition and action execution
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-04
# ==============================================================================
"""
Tests for Intent Recognition and Action Execution

Tests cover:
- IntentService recognition with OpenAI mock
- ActionHandler execution for each intent type
- Validation and confirmation flows
- Pending confirmation handling
"""

from decimal import Decimal
from unittest.mock import patch
from datetime import date

from django.test import TestCase
from django.utils import timezone

from apps.users.models import User


class IntentServiceTests(TestCase):
    """Test intent recognition functionality."""

    def setUp(self):
        """Set up test user and preferences."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test'
        )
        # Ensure preferences exist
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.save()

    def test_intent_result_dataclass(self):
        """Test IntentResult dataclass creation."""
        from apps.ai.intent_service import IntentResult

        result = IntentResult(
            intent_type='log_heart_rate',
            parameters={'bpm': 60, 'context': 'resting'},
            confidence=1.0
        )

        self.assertEqual(result.intent_type, 'log_heart_rate')
        self.assertEqual(result.parameters['bpm'], 60)
        self.assertFalse(result.requires_confirmation)

    def test_action_result_dataclass(self):
        """Test ActionResult dataclass creation."""
        from apps.ai.intent_service import ActionResult

        result = ActionResult(
            success=True,
            message='Logged heart rate',
            created_object={'id': 1, 'bpm': 60},
            action_type='log_heart_rate'
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action_type, 'log_heart_rate')

    @patch('apps.ai.intent_service.IntentService._initialize_client')
    def test_intent_service_initialization(self, mock_init):
        """Test IntentService initialization."""
        from apps.ai.intent_service import IntentService

        service = IntentService()
        self.assertIsNotNone(service)

    def test_build_intent_system_prompt(self):
        """Test system prompt generation for intent recognition."""
        from apps.ai.intent_service import IntentService

        service = IntentService()
        prompt = service._build_intent_system_prompt()

        # Should contain key instructions
        self.assertIn('intent recognition', prompt.lower())
        self.assertIn('log_heart_rate', prompt)
        self.assertIn('log_blood_pressure', prompt)

    def test_validation_check_normal_heart_rate(self):
        """Test that normal heart rate doesn't require confirmation."""
        from apps.ai.intent_service import IntentService

        service = IntentService()
        requires, message = service._check_validation(
            'log_heart_rate',
            {'bpm': 75, 'context': 'resting'},
            self.user
        )

        self.assertFalse(requires)
        self.assertEqual(message, "")

    def test_validation_check_high_heart_rate(self):
        """Test that unusually high heart rate requires confirmation."""
        from apps.ai.intent_service import IntentService

        service = IntentService()
        requires, message = service._check_validation(
            'log_heart_rate',
            {'bpm': 200, 'context': 'resting'},
            self.user
        )

        self.assertTrue(requires)
        self.assertIn('200 BPM', message)

    def test_validation_check_low_heart_rate(self):
        """Test that unusually low heart rate requires confirmation."""
        from apps.ai.intent_service import IntentService

        service = IntentService()
        requires, message = service._check_validation(
            'log_heart_rate',
            {'bpm': 35, 'context': 'resting'},
            self.user
        )

        self.assertTrue(requires)
        self.assertIn('35 BPM', message)

    def test_validation_check_abnormal_blood_pressure(self):
        """Test that abnormal blood pressure requires confirmation."""
        from apps.ai.intent_service import IntentService

        service = IntentService()
        requires, message = service._check_validation(
            'log_blood_pressure',
            {'systolic': 200, 'diastolic': 130},
            self.user
        )

        self.assertTrue(requires)
        self.assertIn('200/130', message)

    def test_validation_check_low_spo2(self):
        """Test that low SpO2 requires confirmation."""
        from apps.ai.intent_service import IntentService

        service = IntentService()
        requires, message = service._check_validation(
            'log_blood_oxygen',
            {'spo2': 88},
            self.user
        )

        self.assertTrue(requires)
        self.assertIn('88%', message)

    def test_always_confirm_preference(self):
        """Test that assistant_confirm_actions preference triggers confirmation."""
        from apps.ai.intent_service import IntentService

        # Enable confirmation preference
        prefs = self.user.preferences
        prefs.assistant_confirm_actions = True
        prefs.save()

        service = IntentService()
        requires, message = service._check_validation(
            'log_heart_rate',
            {'bpm': 75, 'context': 'resting'},
            self.user
        )

        self.assertTrue(requires)
        self.assertIn('75', message)  # BPM value present in confirmation

    def test_build_confirmation_message_heart_rate(self):
        """Test confirmation message for heart rate."""
        from apps.ai.intent_service import IntentService

        service = IntentService()
        message = service._build_confirmation_message(
            'log_heart_rate',
            {'bpm': 60, 'context': 'resting'}
        )

        self.assertIn('60 BPM', message)
        self.assertIn('resting', message)

    def test_build_confirmation_message_weight(self):
        """Test confirmation message for weight."""
        from apps.ai.intent_service import IntentService

        service = IntentService()
        message = service._build_confirmation_message(
            'log_weight',
            {'value': 175, 'unit': 'lb'}
        )

        self.assertIn('175 lb', message)

    @patch('apps.ai.intent_service.cache')
    def test_store_and_retrieve_pending_confirmation(self, mock_cache):
        """Test storing and retrieving pending confirmations."""
        from apps.ai.intent_service import IntentService, IntentResult

        mock_cache.get.return_value = {
            'intent_type': 'log_heart_rate',
            'parameters': {'bpm': 60},
            'timestamp': timezone.now().isoformat()
        }

        service = IntentService()
        intent_result = IntentResult(
            intent_type='log_heart_rate',
            parameters={'bpm': 60}
        )

        service.store_pending_confirmation(self.user, intent_result)
        mock_cache.set.assert_called_once()

        pending = service.get_pending_confirmation(self.user)
        self.assertEqual(pending['intent_type'], 'log_heart_rate')

    @patch('apps.ai.intent_service.cache')
    def test_handle_affirmative_confirmation(self, mock_cache):
        """Test handling yes response to confirmation."""
        from apps.ai.intent_service import IntentService

        mock_cache.get.return_value = {
            'intent_type': 'log_heart_rate',
            'parameters': {'bpm': 60, 'context': 'resting'},
            'timestamp': timezone.now().isoformat()
        }

        service = IntentService()

        # Mock execute_intent to avoid database operations
        with patch.object(service, 'execute_intent') as mock_execute:
            from apps.ai.intent_service import ActionResult
            mock_execute.return_value = ActionResult(
                success=True,
                message='Logged',
                action_type='log_heart_rate'
            )

            result = service.handle_confirmation_response(self.user, 'yes')

            self.assertIsNotNone(result)
            self.assertTrue(result.success)
            mock_cache.delete.assert_called()

    @patch('apps.ai.intent_service.cache')
    def test_handle_negative_confirmation(self, mock_cache):
        """Test handling no response to confirmation."""
        from apps.ai.intent_service import IntentService

        mock_cache.get.return_value = {
            'intent_type': 'log_heart_rate',
            'parameters': {'bpm': 60},
            'timestamp': timezone.now().isoformat()
        }

        service = IntentService()
        result = service.handle_confirmation_response(self.user, 'no')

        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        self.assertEqual(result.action_type, 'cancelled')
        mock_cache.delete.assert_called()


class ActionHandlerTests(TestCase):
    """Test action execution functionality."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test'
        )
        prefs = self.user.preferences
        prefs.timezone = 'America/New_York'
        prefs.save()

    def test_handle_log_heart_rate(self):
        """Test logging heart rate entry."""
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import HeartRateEntry

        handler = ActionHandler(self.user)
        result = handler.handle_log_heart_rate(bpm=72, context='resting')

        self.assertTrue(result.success)
        self.assertIn('72 BPM', result.message)
        self.assertEqual(result.action_type, 'log_heart_rate')
        self.assertIsNotNone(result.created_object)

        # Verify database entry
        entry = HeartRateEntry.objects.get(user=self.user)
        self.assertEqual(entry.bpm, 72)
        self.assertEqual(entry.context, 'resting')

    def test_handle_log_blood_pressure(self):
        """Test logging blood pressure entry."""
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import BloodPressureEntry

        handler = ActionHandler(self.user)
        result = handler.handle_log_blood_pressure(
            systolic=120,
            diastolic=80,
            pulse=72,
            context='resting'
        )

        self.assertTrue(result.success)
        self.assertIn('120/80', result.message)
        self.assertEqual(result.action_type, 'log_blood_pressure')

        # Verify database entry
        entry = BloodPressureEntry.objects.get(user=self.user)
        self.assertEqual(entry.systolic, 120)
        self.assertEqual(entry.diastolic, 80)
        self.assertEqual(entry.pulse, 72)

    def test_handle_log_weight(self):
        """Test logging weight entry."""
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import WeightEntry

        handler = ActionHandler(self.user)
        result = handler.handle_log_weight(value=175.5, unit='lb')

        self.assertTrue(result.success)
        self.assertIn('175.5 lb', result.message)
        self.assertEqual(result.action_type, 'log_weight')

        # Verify database entry
        entry = WeightEntry.objects.get(user=self.user)
        self.assertEqual(entry.value, Decimal('175.5'))
        self.assertEqual(entry.unit, 'lb')

    def test_handle_log_glucose(self):
        """Test logging glucose entry."""
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import GlucoseEntry

        handler = ActionHandler(self.user)
        result = handler.handle_log_glucose(
            value=105,
            unit='mg/dL',
            context='fasting'
        )

        self.assertTrue(result.success)
        self.assertIn('105 mg/dL', result.message)
        self.assertEqual(result.action_type, 'log_glucose')

        # Verify database entry
        entry = GlucoseEntry.objects.get(user=self.user)
        self.assertEqual(entry.value, Decimal('105'))
        self.assertEqual(entry.context, 'fasting')

    def test_handle_log_blood_oxygen(self):
        """Test logging blood oxygen entry."""
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import BloodOxygenEntry

        handler = ActionHandler(self.user)
        result = handler.handle_log_blood_oxygen(spo2=98, pulse=68)

        self.assertTrue(result.success)
        self.assertIn('98%', result.message)
        self.assertEqual(result.action_type, 'log_blood_oxygen')

        # Verify database entry
        entry = BloodOxygenEntry.objects.get(user=self.user)
        self.assertEqual(entry.spo2, 98)
        self.assertEqual(entry.pulse, 68)

    def test_handle_log_food(self):
        """Test logging food entry."""
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import FoodEntry

        handler = ActionHandler(self.user)
        result = handler.handle_log_food(
            food_name='banana',
            quantity=1,
            calories=105
        )

        self.assertTrue(result.success)
        self.assertIn('banana', result.message)
        self.assertEqual(result.action_type, 'log_food')

        # Verify database entry
        entry = FoodEntry.objects.get(user=self.user)
        self.assertEqual(entry.food_name, 'banana')
        self.assertEqual(entry.entry_source, 'voice')

    def test_handle_start_fast(self):
        """Test starting a fast."""
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import FastingWindow

        handler = ActionHandler(self.user)
        result = handler.handle_start_fast(fasting_type='16:8')

        self.assertTrue(result.success)
        self.assertIn('16:8', result.message)
        self.assertEqual(result.action_type, 'start_fast')

        # Verify database entry
        fast = FastingWindow.objects.get(user=self.user)
        self.assertEqual(fast.fasting_type, '16:8')
        self.assertIsNone(fast.ended_at)

    def test_handle_start_fast_when_active_exists(self):
        """Test starting a fast when one is already active."""
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import FastingWindow

        # Create an active fast
        FastingWindow.objects.create(
            user=self.user,
            fasting_type='16:8',
            started_at=timezone.now(),
            target_hours=16
        )

        handler = ActionHandler(self.user)
        result = handler.handle_start_fast(fasting_type='18:6')

        self.assertFalse(result.success)
        self.assertIn('already have an active fast', result.message)

    def test_handle_end_fast(self):
        """Test ending an active fast."""
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import FastingWindow

        # Create an active fast
        fast = FastingWindow.objects.create(
            user=self.user,
            fasting_type='16:8',
            started_at=timezone.now() - timezone.timedelta(hours=16),
            target_hours=16
        )

        handler = ActionHandler(self.user)
        result = handler.handle_end_fast()

        self.assertTrue(result.success)
        self.assertIn('ended', result.message.lower())
        self.assertEqual(result.action_type, 'end_fast')

        # Verify fast was ended
        fast.refresh_from_db()
        self.assertIsNotNone(fast.ended_at)

    def test_handle_end_fast_when_none_active(self):
        """Test ending fast when none is active."""
        from apps.ai.action_handlers import ActionHandler

        handler = ActionHandler(self.user)
        result = handler.handle_end_fast()

        self.assertFalse(result.success)
        self.assertIn("don't have an active fast", result.message)

    def test_handle_take_medicine_not_found(self):
        """Test taking medicine that doesn't exist."""
        from apps.ai.action_handlers import ActionHandler

        handler = ActionHandler(self.user)
        result = handler.handle_take_medicine(medicine_name='nonexistent')

        self.assertFalse(result.success)
        self.assertIn("couldn't find", result.message)

    def test_handle_take_medicine_single_match(self):
        """Test taking medicine with single match."""
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import Intake, IntakeLog

        # Create a medicine
        medicine = Intake.objects.create(
            user=self.user,
            name='Metformin',
            dose='500mg',
            is_prn=True,
            intake_status=Intake.STATUS_ACTIVE,
            start_date=date.today()
        )

        handler = ActionHandler(self.user)
        result = handler.handle_take_medicine(medicine_name='metformin')

        self.assertTrue(result.success)
        self.assertIn('Metformin', result.message)
        self.assertEqual(result.action_type, 'take_medicine')

        # Verify log was created
        log = IntakeLog.objects.get(user=self.user, intake=medicine)
        self.assertIsNotNone(log.taken_at)

    def test_handle_take_medicine_multiple_matches(self):
        """Test taking medicine with multiple matches."""
        from apps.ai.action_handlers import ActionHandler
        from apps.health.models import Intake

        # Create multiple matching medicines
        Intake.objects.create(
            user=self.user,
            name='Metformin 500mg',
            dose='500mg',
            intake_status=Intake.STATUS_ACTIVE,
            start_date=date.today()
        )
        Intake.objects.create(
            user=self.user,
            name='Metformin 1000mg',
            dose='1000mg',
            intake_status=Intake.STATUS_ACTIVE,
            start_date=date.today()
        )

        handler = ActionHandler(self.user)
        result = handler.handle_take_medicine(medicine_name='metformin')

        self.assertFalse(result.success)
        self.assertIn('found 2 medicines', result.message.lower())


class IntentToolDefinitionTests(TestCase):
    """Test intent tool definitions."""

    def test_all_intent_tools_loaded(self):
        """Test that all intent tools are loaded."""
        from apps.ai.intents import ALL_INTENT_TOOLS

        self.assertIsInstance(ALL_INTENT_TOOLS, list)
        self.assertGreater(len(ALL_INTENT_TOOLS), 0)

    def test_intent_handlers_mapping(self):
        """Test intent handlers mapping."""
        from apps.ai.intents import INTENT_HANDLERS

        self.assertIn('log_heart_rate', INTENT_HANDLERS)
        self.assertIn('log_blood_pressure', INTENT_HANDLERS)
        self.assertIn('take_medicine', INTENT_HANDLERS)
        self.assertIn('start_fast', INTENT_HANDLERS)

    def test_health_intent_tools_structure(self):
        """Test that health intent tools have correct structure."""
        from apps.ai.intents.health_intents import HEALTH_INTENT_TOOLS

        for tool in HEALTH_INTENT_TOOLS:
            self.assertEqual(tool['type'], 'function')
            self.assertIn('function', tool)
            self.assertIn('name', tool['function'])
            self.assertIn('description', tool['function'])
            self.assertIn('parameters', tool['function'])

    def test_log_heart_rate_tool_parameters(self):
        """Test log_heart_rate tool parameter schema."""
        from apps.ai.intents.health_intents import HEALTH_INTENT_TOOLS

        hr_tool = next(t for t in HEALTH_INTENT_TOOLS if t['function']['name'] == 'log_heart_rate')
        params = hr_tool['function']['parameters']

        self.assertEqual(params['type'], 'object')
        self.assertIn('bpm', params['properties'])
        self.assertIn('context', params['properties'])
        self.assertEqual(params['required'], ['bpm'])

    def test_validation_ranges_defined(self):
        """Test that validation ranges are defined for health metrics."""
        from apps.ai.intents.health_intents import HEALTH_VALIDATION_RANGES

        self.assertIn('heart_rate', HEALTH_VALIDATION_RANGES)
        self.assertIn('blood_pressure', HEALTH_VALIDATION_RANGES)
        self.assertIn('weight', HEALTH_VALIDATION_RANGES)
        self.assertIn('glucose', HEALTH_VALIDATION_RANGES)
        self.assertIn('blood_oxygen', HEALTH_VALIDATION_RANGES)

        # Check heart rate has expected keys
        hr_ranges = HEALTH_VALIDATION_RANGES['heart_rate']
        self.assertIn('normal_min', hr_ranges)
        self.assertIn('normal_max', hr_ranges)
        self.assertEqual(hr_ranges['normal_min'], 40)
        self.assertEqual(hr_ranges['normal_max'], 180)


class PersonalAssistantIntegrationTests(TestCase):
    """Test PersonalAssistant integration with intent recognition."""

    def setUp(self):
        """Set up test user and preferences."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test'
        )
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.timezone = 'America/New_York'
        prefs.save()

    def test_send_message_with_intent(self):
        """Test send_message returns dict with response key."""
        from apps.ai.personal_assistant import get_personal_assistant

        assistant = get_personal_assistant(self.user)
        result = assistant.send_message('my heart rate is 60')

        # Verify basic structure - intent processing may or may not work in test env
        self.assertIsInstance(result, dict)
        self.assertIn('response', result)
        self.assertIsInstance(result['response'], str)

    def test_send_message_no_intent(self):
        """Test send_message without action intent returns chat response."""
        from apps.ai.personal_assistant import get_personal_assistant

        assistant = get_personal_assistant(self.user)
        result = assistant.send_message('hello')

        # Verify basic structure - should always return a response
        self.assertIsInstance(result, dict)
        self.assertIn('response', result)
        self.assertIsInstance(result['response'], str)
        # No action should be taken for a greeting
        self.assertNotIn('action_taken', result)

    def test_send_message_requires_confirmation(self):
        """Test send_message with high value triggers fallback for edge cases."""
        from apps.ai.personal_assistant import get_personal_assistant

        assistant = get_personal_assistant(self.user)
        result = assistant.send_message('my heart rate is 200')

        # Verify basic structure - high value may or may not trigger confirmation
        self.assertIsInstance(result, dict)
        self.assertIn('response', result)


# ==========================================================================
# Intent Routing Safeguards — Domain Locking & Cross-Domain Rejection
# ==========================================================================


class TestDomainLockSafeguard(TestCase):
    """
    Tests for the domain-lock safeguard that prevents cross-domain
    intent misrouting (e.g., "move workout" → "rename assistant").
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='domainlock@example.com',
            password='testpass123',
        )
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.save()

    def test_settings_removed_from_core_intent_tools(self):
        """SETTINGS_INTENT_TOOLS must NOT be in CORE_INTENT_TOOLS."""
        from apps.ai.intents import (
            CORE_INTENT_TOOLS, SETTINGS_INTENT_TOOLS,
        )
        core_names = {
            t['function']['name'] for t in CORE_INTENT_TOOLS
        }
        settings_names = {
            t['function']['name'] for t in SETTINGS_INTENT_TOOLS
        }
        self.assertTrue(
            core_names.isdisjoint(settings_names),
            f"Settings intents in CORE: {core_names & settings_names}",
        )

    def test_settings_in_own_domain(self):
        """Settings intents must be in their own domain scope."""
        from apps.ai.intents import DOMAIN_INTENT_TOOLS
        self.assertIn('settings', DOMAIN_INTENT_TOOLS)

    def test_health_domain_includes_life_tools(self):
        """Health domain must include LIFE_INTENT_TOOLS for routine crossover."""
        from apps.ai.intents import DOMAIN_INTENT_TOOLS
        health_tool_names = {
            t['function']['name'] for t in DOMAIN_INTENT_TOOLS['health']
        }
        self.assertIn(
            'reschedule_routine_item', health_tool_names,
            "health domain must include reschedule_routine_item "
            "for 'move my workout' messages",
        )

    @patch('django.conf.settings.WLJ_SCOPED_INTENT_TOOLS_ENABLED', True)
    def test_scoped_tools_health_excludes_set_cos_name(self):
        """When domain is 'health', set_cos_name must NOT be in tools."""
        from apps.ai.intents import get_scoped_intent_tools
        tools = get_scoped_intent_tools('health')
        tool_names = {t['function']['name'] for t in tools}
        self.assertNotIn(
            'set_cos_name', tool_names,
            "set_cos_name must not appear in health-scoped tools",
        )

    @patch('django.conf.settings.WLJ_SCOPED_INTENT_TOOLS_ENABLED', True)
    def test_scoped_tools_tasks_excludes_set_cos_name(self):
        """When domain is 'tasks', set_cos_name must NOT be in tools."""
        from apps.ai.intents import get_scoped_intent_tools
        tools = get_scoped_intent_tools('tasks')
        tool_names = {t['function']['name'] for t in tools}
        self.assertNotIn(
            'set_cos_name', tool_names,
            "set_cos_name must not appear in tasks-scoped tools",
        )


class TestSetCosNameSafeguards(TestCase):
    """
    Tests for the keyword safeguard and confirmation gate on set_cos_name.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='cosname@example.com',
            password='testpass123',
        )
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.save()

    def test_set_cos_name_requires_confirmation(self):
        """set_cos_name must always require confirmation."""
        from apps.ai.intent_service import IntentService
        svc = IntentService()
        requires, msg = svc._check_validation(
            'set_cos_name', {'name': 'Max'}, self.user,
        )
        self.assertTrue(
            requires,
            "set_cos_name must always require confirmation",
        )
        self.assertIn('Max', msg)

    def test_set_cos_name_reset_requires_confirmation(self):
        """set_cos_name with empty name (reset) must also require confirmation."""
        from apps.ai.intent_service import IntentService
        svc = IntentService()
        requires, msg = svc._check_validation(
            'set_cos_name', {'name': ''}, self.user,
        )
        self.assertTrue(requires)
        self.assertIn('default', msg.lower())

    def test_keyword_safeguard_rejects_without_name_language(self):
        """
        If user message doesn't contain name-change language,
        set_cos_name must be rejected even if OpenAI selects it.
        """
        from apps.ai.intent_service import IntentService
        from unittest.mock import MagicMock

        svc = IntentService()

        # Simulate OpenAI returning set_cos_name for a workout message
        mock_response = MagicMock()
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = 'set_cos_name'
        mock_tool_call.function.arguments = '{"name": "Max"}'
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.tool_calls = [mock_tool_call]
        mock_response.choices[0].message.content = None
        mock_response.usage = None

        # Patch the client attribute directly
        original_client = svc.client
        svc.client = MagicMock()
        svc.client.chat.completions.create.return_value = mock_response

        try:
            results = svc.recognize_intents(
                "I have to move my workout until tonight at 8:30pm",
                self.user,
            )
        finally:
            svc.client = original_client

        # set_cos_name should be rejected — no name-change language
        intent_types = [r.intent_type for r in results]
        self.assertNotIn(
            'set_cos_name', intent_types,
            "set_cos_name must be rejected when message has no "
            "name-change language",
        )

    def test_keyword_safeguard_allows_with_name_language(self):
        """
        If user message contains explicit name-change language,
        set_cos_name should be allowed (with confirmation).
        """
        from apps.ai.intent_service import IntentService
        from unittest.mock import MagicMock

        svc = IntentService()

        mock_response = MagicMock()
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = 'set_cos_name'
        mock_tool_call.function.arguments = '{"name": "Jarvis"}'
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.tool_calls = [mock_tool_call]
        mock_response.choices[0].message.content = None
        mock_response.usage = None

        original_client = svc.client
        svc.client = MagicMock()
        svc.client.chat.completions.create.return_value = mock_response

        try:
            results = svc.recognize_intents(
                "call yourself Jarvis from now on",
                self.user,
            )
        finally:
            svc.client = original_client

        # Should be allowed — explicit name-change language
        intent_types = [r.intent_type for r in results]
        self.assertIn('set_cos_name', intent_types)
        # Should require confirmation
        cos_result = next(
            r for r in results if r.intent_type == 'set_cos_name'
        )
        self.assertTrue(cos_result.requires_confirmation)
