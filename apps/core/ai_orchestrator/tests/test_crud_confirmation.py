"""
Tests for the CRUD Confirmation Gate.

Tests deterministic confirmation parsing, idempotency protection,
confirmation expiry, and the global write-operation gate.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.core.ai_orchestrator.crud_confirmation import (
    PASSTHROUGH_INTENTS,
    build_crud_confirmation_message,
    parse_confirmation_response,
    requires_confirmation,
)


class ParseConfirmationTests(TestCase):
    """Tests for deterministic confirmation response parsing."""

    def test_confirm_keyword(self):
        self.assertEqual(parse_confirmation_response('CONFIRM'), 'confirm')

    def test_confirm_with_trailing_text(self):
        self.assertEqual(parse_confirmation_response('CONFIRM please'), 'confirm')

    def test_yes_uppercase(self):
        self.assertEqual(parse_confirmation_response('YES'), 'confirm')

    def test_yes_lowercase(self):
        self.assertEqual(parse_confirmation_response('yes'), 'confirm')

    def test_y_shorthand(self):
        self.assertEqual(parse_confirmation_response('Y'), 'confirm')

    def test_cancel_keyword(self):
        self.assertEqual(parse_confirmation_response('CANCEL'), 'cancel')

    def test_cancel_with_trailing_text(self):
        self.assertEqual(parse_confirmation_response('CANCEL that'), 'cancel')

    def test_no_uppercase(self):
        self.assertEqual(parse_confirmation_response('NO'), 'cancel')

    def test_no_lowercase(self):
        self.assertEqual(parse_confirmation_response('no'), 'cancel')

    def test_n_shorthand(self):
        self.assertEqual(parse_confirmation_response('N'), 'cancel')

    def test_edit_keyword(self):
        self.assertEqual(parse_confirmation_response('EDIT'), 'edit')

    def test_modify_keyword(self):
        self.assertEqual(parse_confirmation_response('MODIFY'), 'edit')

    def test_change_keyword(self):
        self.assertEqual(parse_confirmation_response('CHANGE'), 'edit')

    def test_unrecognized_returns_none(self):
        self.assertIsNone(parse_confirmation_response('I want something else'))

    def test_empty_returns_none(self):
        self.assertIsNone(parse_confirmation_response(''))

    def test_whitespace_handling(self):
        self.assertEqual(parse_confirmation_response('  CONFIRM  '), 'confirm')

    def test_mixed_case(self):
        self.assertEqual(parse_confirmation_response('Confirm'), 'confirm')
        self.assertEqual(parse_confirmation_response('Cancel'), 'cancel')
        self.assertEqual(parse_confirmation_response('Edit'), 'edit')


class RequiresConfirmationTests(TestCase):
    """Tests for the confirmation gate scope."""

    def test_write_intents_require_confirmation(self):
        """All write intents should require confirmation."""
        write_intents = [
            'create_task', 'create_event', 'log_weight', 'mutate_task',
            'take_medicine', 'log_prayer', 'create_goal', 'log_habit',
            'log_workout', 'complete_task', 'skip_task',
            'undo_last_action', 'email_medicine_list',
        ]
        for intent in write_intents:
            self.assertTrue(
                requires_confirmation(intent),
                f"{intent} should require confirmation",
            )

    def test_read_intents_pass_through(self):
        """Read/control intents should NOT require confirmation."""
        for intent in PASSTHROUGH_INTENTS:
            self.assertFalse(
                requires_confirmation(intent),
                f"{intent} should NOT require confirmation",
            )

    def test_no_action_passes_through(self):
        self.assertFalse(requires_confirmation('no_action'))

    def test_learning_mode_passes_through(self):
        self.assertFalse(requires_confirmation('enter_learning_mode'))
        self.assertFalse(requires_confirmation('exit_learning_mode'))


class ConfirmationMessageBuilderTests(TestCase):
    """Tests for the confirmation message builder."""

    def test_standard_create_task_message(self):
        enriched = MagicMock()
        enriched.intent_type = 'create_task'
        enriched.parameters = {'title': 'Grocery Run', 'scheduled_time': '15:00'}

        msg = build_crud_confirmation_message(enriched)
        self.assertIn('Grocery Run', msg)
        self.assertIn('CONFIRM', msg)
        self.assertIn('CANCEL', msg)

    def test_log_weight_message(self):
        enriched = MagicMock()
        enriched.intent_type = 'log_weight'
        enriched.parameters = {'weight': '185'}

        msg = build_crud_confirmation_message(enriched)
        self.assertIn('185', msg)
        self.assertIn('CONFIRM', msg)

    def test_reschedule_message_includes_from_to(self):
        from apps.core.ai_orchestrator.activity_reconciliation import (
            ReconciliationDecision,
            ReconciliationResult,
        )

        enriched = MagicMock()
        enriched.intent_type = 'mutate_task'
        enriched.parameters = {'new_scheduled_time': '13:30'}

        recon = ReconciliationResult(
            decision=ReconciliationDecision.RESCHEDULE,
            original_intent='create_task',
            matched_object={'model': 'Task', 'id': 42, 'title': 'Workout', 'time': '06:15:00'},
        )

        msg = build_crud_confirmation_message(enriched, recon)
        self.assertIn('Workout', msg)
        self.assertIn('from', msg.lower())
        self.assertIn('to', msg.lower())
        self.assertIn('CONFIRM', msg)

    def test_skip_message(self):
        from apps.core.ai_orchestrator.activity_reconciliation import (
            ReconciliationDecision,
            ReconciliationResult,
        )

        enriched = MagicMock()
        enriched.intent_type = 'create_task'
        enriched.parameters = {}

        recon = ReconciliationResult(
            decision=ReconciliationDecision.SKIP,
            original_intent='create_task',
            skip_message='You already have "Workout" scheduled at 6:15 AM.',
        )

        msg = build_crud_confirmation_message(enriched, recon)
        self.assertIn('already have', msg)
        self.assertIn('CONFIRM', msg)

    def test_confirm_ambiguous_message(self):
        from apps.core.ai_orchestrator.activity_reconciliation import (
            ReconciliationDecision,
            ReconciliationResult,
        )

        enriched = MagicMock()
        enriched.intent_type = 'create_task'
        enriched.parameters = {}

        recon = ReconciliationResult(
            decision=ReconciliationDecision.CONFIRM,
            original_intent='create_task',
            confirm_message='I found a possible match: "Workout".',
            candidates=[
                {'id': 1, 'title': 'Morning Workout'},
                {'id': 2, 'title': 'Evening Workout'},
            ],
        )

        msg = build_crud_confirmation_message(enriched, recon)
        self.assertIn('Morning Workout', msg)
        self.assertIn('Evening Workout', msg)
        self.assertIn('CONFIRM', msg)


class HandleCrudConfirmationTests(TestCase):
    """Tests for the CRUD confirmation handler on IntentService."""

    def setUp(self):
        from apps.ai.intent_service import intent_service
        self.intent_service = intent_service
        self.user = MagicMock()
        self.user.id = 99

    def _store_pending(self, **overrides):
        """Helper to store a pending CRUD action."""
        data = {
            'intent_type': 'create_task',
            'parameters': {'title': 'Test Task'},
            'original_intent': 'create_task',
            'original_input': 'create a test task',
            'recon_decision': 'create',
            'recon_context': None,
            'confirmation_message': 'Adding a task: "Test Task"\n\nReply with: CONFIRM, CANCEL, or EDIT',
        }
        data.update(overrides)
        self.intent_service.store_pending_crud_action(self.user, data)

    @patch('apps.core.ai_orchestrator.execution_engine.execute_action')
    def test_confirm_executes_action(self, mock_execute):
        mock_execute.return_value = MagicMock(
            success=True, message='Task created.', action_type='create_task',
        )
        self._store_pending()

        result = self.intent_service.handle_crud_confirmation(self.user, 'CONFIRM')
        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        mock_execute.assert_called_once()
        # Pending should be cleared
        self.assertIsNone(self.intent_service.get_pending_crud_action(self.user))

    def test_cancel_clears_pending(self):
        self._store_pending()

        result = self.intent_service.handle_crud_confirmation(self.user, 'CANCEL')
        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, 'cancelled')
        self.assertIsNone(self.intent_service.get_pending_crud_action(self.user))

    def test_edit_clears_pending_with_reprompt(self):
        self._store_pending()

        result = self.intent_service.handle_crud_confirmation(self.user, 'EDIT')
        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, 'cancelled')
        self.assertIn('instead', result.message)
        self.assertIsNone(self.intent_service.get_pending_crud_action(self.user))

    def test_unrecognized_escapes_confirmation(self):
        self._store_pending()

        result = self.intent_service.handle_crud_confirmation(self.user, 'something random')
        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, 'confirmation_escaped')
        # Pending should be cleared (escape cancels it)
        self.assertIsNone(self.intent_service.get_pending_crud_action(self.user))

    def test_expired_action_returns_expiry_message(self):
        # Don't store anything — simulates expiry
        result = self.intent_service.handle_crud_confirmation(self.user, 'CONFIRM')
        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, 'expired')
        self.assertIn('expired', result.message)

    @patch('apps.core.ai_orchestrator.execution_engine.execute_action')
    def test_idempotency_double_confirm(self, mock_execute):
        """Second confirm should return 'already completed', not execute again."""
        mock_execute.return_value = MagicMock(
            success=True, message='Done.', action_type='create_task',
        )
        self._store_pending()

        # First confirm
        self.intent_service.handle_crud_confirmation(self.user, 'CONFIRM')

        # Store again but mark as executed
        self._store_pending()
        pending = self.intent_service.get_pending_crud_action(self.user)
        pending['executed'] = True
        from django.core.cache import cache
        cache.set(f"pending_crud_{self.user.id}", pending, 300)

        # Second confirm
        result = self.intent_service.handle_crud_confirmation(self.user, 'CONFIRM')
        self.assertEqual(result.action_type, 'idempotent_skip')
        self.assertIn('already completed', result.message)

    def test_uuid_action_id_generated(self):
        """Stored pending action should have a UUID action_id."""
        self._store_pending()
        pending = self.intent_service.get_pending_crud_action(self.user)
        self.assertIn('action_id', pending)
        self.assertIsNotNone(pending['action_id'])
        # Should be a UUID format (36 chars with hyphens)
        self.assertEqual(len(pending['action_id']), 36)

    def test_executed_flag_set_to_false(self):
        """Stored pending action should have executed=False."""
        self._store_pending()
        pending = self.intent_service.get_pending_crud_action(self.user)
        self.assertFalse(pending['executed'])

    def tearDown(self):
        """Clean up cached pending actions."""
        self.intent_service.clear_pending_crud_action(self.user)


class ParseOptionResponseTests(TestCase):
    """Tests for A/B/C option key parsing in confirmations."""

    def setUp(self):
        self.options = [
            {'key': 'A', 'label': 'Sounds good', 'action': 'confirm'},
            {'key': 'B', 'label': 'Never mind', 'action': 'cancel'},
            {'key': 'C', 'label': 'Change something', 'action': 'edit'},
        ]

    def test_letter_a_maps_to_confirm(self):
        result = parse_confirmation_response('A', options=self.options)
        self.assertEqual(result, 'confirm')

    def test_letter_b_maps_to_cancel(self):
        result = parse_confirmation_response('B', options=self.options)
        self.assertEqual(result, 'cancel')

    def test_letter_c_maps_to_edit(self):
        result = parse_confirmation_response('C', options=self.options)
        self.assertEqual(result, 'edit')

    def test_lowercase_letter(self):
        result = parse_confirmation_response('a', options=self.options)
        self.assertEqual(result, 'confirm')

    def test_letter_with_whitespace(self):
        result = parse_confirmation_response('  b  ', options=self.options)
        self.assertEqual(result, 'cancel')

    def test_legacy_confirm_still_works_with_options(self):
        """CONFIRM keyword should still work even when options are present."""
        result = parse_confirmation_response('CONFIRM', options=self.options)
        self.assertEqual(result, 'confirm')

    def test_legacy_cancel_still_works_with_options(self):
        result = parse_confirmation_response('CANCEL', options=self.options)
        self.assertEqual(result, 'cancel')

    def test_unrecognized_with_options(self):
        result = parse_confirmation_response('something else', options=self.options)
        self.assertIsNone(result)

    def test_no_options_fallback_to_legacy(self):
        """When no options provided, should use legacy parsing."""
        result = parse_confirmation_response('A', options=None)
        # Without options, single letter 'A' may not match legacy keywords
        # This tests that the function doesn't crash
        self.assertIsNone(result)

    def test_empty_options_fallback(self):
        result = parse_confirmation_response('CONFIRM', options=[])
        self.assertEqual(result, 'confirm')


class StructuredConfirmationBuilderTests(TestCase):
    """Tests for the build_structured_confirmation function."""

    def test_returns_tuple_of_text_and_options(self):
        from apps.core.ai_orchestrator.crud_confirmation import (
            build_structured_confirmation,
        )
        enriched = MagicMock()
        enriched.intent_type = 'create_task'
        enriched.parameters = {'title': 'Workout'}

        msg, options = build_structured_confirmation(enriched)
        self.assertIsInstance(msg, str)
        self.assertIsInstance(options, list)
        self.assertGreater(len(options), 0)

    def test_options_have_required_keys(self):
        from apps.core.ai_orchestrator.crud_confirmation import (
            build_structured_confirmation,
        )
        enriched = MagicMock()
        enriched.intent_type = 'log_weight'
        enriched.parameters = {'weight': '185'}

        _, options = build_structured_confirmation(enriched)
        for opt in options:
            self.assertIn('key', opt)
            self.assertIn('label', opt)
            self.assertIn('action', opt)

    def test_suggestion_marks_is_suggested(self):
        from apps.core.ai_orchestrator.crud_confirmation import (
            build_structured_confirmation,
        )
        enriched = MagicMock()
        enriched.intent_type = 'log_heart_rate'
        enriched.parameters = {'bpm': 72}

        suggestion = {
            'suggested_action': 'cancel',
            'confidence': 0.80,
            'sample_size': 8,
        }
        _, options = build_structured_confirmation(
            enriched, decision_suggestion=suggestion
        )
        # Cancel option should be marked is_suggested
        cancel_opt = next(o for o in options if o['action'] == 'cancel')
        self.assertTrue(cancel_opt.get('is_suggested', False))
