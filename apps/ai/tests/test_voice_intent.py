# ==============================================================================
# File: test_voice_intent.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for set_cos_name intent definition and routing
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-18
# ==============================================================================
"""
Tests for the set_cos_name voice intent.

Covers:
- Intent tool definition structure and inclusion in ALL_INTENT_TOOLS
- Intent handler routing (set_cos_name -> 'settings')
- ActionHandler.handle_set_cos_name execution and result
"""

from django.test import TestCase

from apps.ai.intents import ALL_INTENT_TOOLS, INTENT_HANDLERS
from apps.ai.intents.settings_intents import SETTINGS_INTENT_TOOLS
from apps.users.models import User


class SetCosNameIntentDefinitionTests(TestCase):
    """Tests for set_cos_name intent tool definition and routing."""

    def test_settings_intent_tools_import(self):
        """SETTINGS_INTENT_TOOLS imports correctly and is a non-empty list."""
        self.assertIsInstance(SETTINGS_INTENT_TOOLS, list)
        self.assertGreater(len(SETTINGS_INTENT_TOOLS), 0)

    def test_set_cos_name_in_all_intent_tools(self):
        """set_cos_name function exists in ALL_INTENT_TOOLS."""
        names = [
            tool['function']['name']
            for tool in ALL_INTENT_TOOLS
            if tool.get('type') == 'function'
        ]
        self.assertIn('set_cos_name', names)

    def test_set_cos_name_in_intent_handlers(self):
        """INTENT_HANDLERS maps set_cos_name to 'settings'."""
        self.assertIn('set_cos_name', INTENT_HANDLERS)
        self.assertEqual(INTENT_HANDLERS['set_cos_name'], 'settings')

    def test_set_cos_name_tool_definition_structure(self):
        """set_cos_name tool has correct OpenAI function-calling structure."""
        tool = None
        for t in ALL_INTENT_TOOLS:
            if (
                t.get('type') == 'function'
                and t.get('function', {}).get('name') == 'set_cos_name'
            ):
                tool = t
                break

        self.assertIsNotNone(tool, "set_cos_name tool not found in ALL_INTENT_TOOLS")

        # Top-level type
        self.assertEqual(tool['type'], 'function')

        # Function block
        func = tool['function']
        self.assertIn('name', func)
        self.assertIn('description', func)
        self.assertIn('parameters', func)

        # Parameters block
        params = func['parameters']
        self.assertEqual(params['type'], 'object')
        self.assertIn('properties', params)
        self.assertIn('name', params['properties'])
        self.assertEqual(params['properties']['name']['type'], 'string')

        # Required fields
        self.assertIn('required', params)
        self.assertIn('name', params['required'])


class HandleSetCosNameTests(TestCase):
    """Tests for ActionHandler.handle_set_cos_name execution."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test-cos@example.com',
            password='testpass123',
            first_name='Test',
        )
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.save()

        from apps.ai.action_handlers import ActionHandler
        self.handler = ActionHandler(self.user)

    def test_handle_set_cos_name_sets_name(self):
        """Calling handle_set_cos_name updates cos_display_name on preferences."""
        self.handler.handle_set_cos_name(name='Jarvis')

        self.user.preferences.refresh_from_db()
        self.assertEqual(self.user.preferences.cos_display_name, 'Jarvis')

    def test_handle_set_cos_name_returns_success(self):
        """handle_set_cos_name returns an ActionResult with success=True."""
        result = self.handler.handle_set_cos_name(name='Friday')

        self.assertTrue(result.success)
        self.assertEqual(result.action_type, 'set_cos_name')
        self.assertIn('Friday', result.message)

    def test_handle_set_cos_name_empty_resets_to_default(self):
        """Passing empty name resets get_cos_name() to 'Chief of Staff'."""
        # Set a custom name first
        self.user.preferences.cos_display_name = 'Max'
        self.user.preferences.save(update_fields=['cos_display_name'])

        result = self.handler.handle_set_cos_name(name='')

        self.assertTrue(result.success)
        self.user.preferences.refresh_from_db()
        self.assertEqual(self.user.preferences.get_cos_name(), 'Chief of Staff')

    def test_handle_set_cos_name_created_object_contains_names(self):
        """ActionResult.created_object includes old_name and new_name."""
        self.user.preferences.cos_display_name = 'OldBot'
        self.user.preferences.save(update_fields=['cos_display_name'])

        result = self.handler.handle_set_cos_name(name='NewBot')

        self.assertIsNotNone(result.created_object)
        self.assertEqual(result.created_object['old_name'], 'OldBot')
        self.assertEqual(result.created_object['new_name'], 'NewBot')
