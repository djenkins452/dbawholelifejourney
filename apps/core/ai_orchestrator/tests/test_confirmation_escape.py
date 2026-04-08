"""
Tests for Confirmation Escape Logic.

When a CRUD confirmation is active and the user sends a message that is NOT
CONFIRM/CANCEL/EDIT, the system should escape confirmation mode and route
the message back to normal AI processing — not loop the prompt.
"""

from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase

from apps.ai.intent_service import ActionResult, intent_service


class ConfirmationEscapeTests(TestCase):
    """Tests for the confirmation escape behavior."""

    def setUp(self):
        from apps.users.models import User, TermsAcceptance

        self.user = User.objects.create_user(
            email='escape@test.com', password='testpass123',
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

        # Store a pending CRUD action
        intent_service.store_pending_crud_action(self.user, {
            'intent_type': 'complete_task',
            'parameters': {'task_keyword': 'Journal'},
            'original_input': 'complete my journal task',
            'confirmation_message': (
                'Completing your task: "Journal"\n\n'
                'Reply with: CONFIRM, CANCEL, or EDIT'
            ),
        })

    def tearDown(self):
        intent_service.clear_pending_crud_action(self.user)
        cache.clear()

    def test_confirm_still_works(self):
        """CONFIRM should still execute the action."""
        with patch(
            'apps.core.ai_orchestrator.execution_engine.execute_action',
        ) as mock_exec:
            mock_exec.return_value = ActionResult(
                success=True, message='Done', action_type='complete_task',
            )
            result = intent_service.handle_crud_confirmation(self.user, 'CONFIRM')
            self.assertTrue(result.success)

    def test_cancel_still_works(self):
        """CANCEL should cancel the pending action."""
        result = intent_service.handle_crud_confirmation(self.user, 'CANCEL')
        self.assertEqual(result.action_type, 'cancelled')
        self.assertIsNone(intent_service.get_pending_crud_action(self.user))

    def test_edit_still_works(self):
        """EDIT should cancel and prompt for new input."""
        result = intent_service.handle_crud_confirmation(self.user, 'EDIT')
        self.assertEqual(result.action_type, 'cancelled')
        self.assertIsNone(intent_service.get_pending_crud_action(self.user))

    def test_unrecognized_escapes_confirmation(self):
        """An unrecognized response should escape confirmation mode."""
        result = intent_service.handle_crud_confirmation(self.user, 'what task?')
        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, 'confirmation_escaped')
        self.assertIsNone(result.message)  # Caller routes to normal AI
        # Pending action should be cleared
        self.assertIsNone(intent_service.get_pending_crud_action(self.user))

    def test_question_escapes_confirmation(self):
        """A clarification question should escape confirmation mode."""
        result = intent_service.handle_crud_confirmation(
            self.user, 'which one did you mean?',
        )
        self.assertEqual(result.action_type, 'confirmation_escaped')
        self.assertIsNone(intent_service.get_pending_crud_action(self.user))

    def test_random_text_escapes_confirmation(self):
        """Random text that isn't a confirmation command should escape."""
        result = intent_service.handle_crud_confirmation(
            self.user, 'I changed my mind, log my weight instead',
        )
        self.assertEqual(result.action_type, 'confirmation_escaped')
        self.assertIsNone(intent_service.get_pending_crud_action(self.user))

    def test_expired_action_returns_expired(self):
        """An expired action should return the expired message."""
        intent_service.clear_pending_crud_action(self.user)
        result = intent_service.handle_crud_confirmation(self.user, 'CONFIRM')
        self.assertEqual(result.action_type, 'expired')

    def test_yes_still_confirms(self):
        """'yes' should still work as confirmation."""
        with patch(
            'apps.core.ai_orchestrator.execution_engine.execute_action',
        ) as mock_exec:
            mock_exec.return_value = ActionResult(
                success=True, message='Done', action_type='complete_task',
            )
            result = intent_service.handle_crud_confirmation(self.user, 'yes')
            self.assertTrue(result.success)

    def test_no_still_cancels(self):
        """'no' should still cancel."""
        result = intent_service.handle_crud_confirmation(self.user, 'no')
        self.assertEqual(result.action_type, 'cancelled')


class ConfirmationMessageWithResolvedNameTests(TestCase):
    """Tests that resolved entity names appear in confirmation messages."""

    def _build(self, intent_type, params):
        from unittest.mock import MagicMock
        from apps.core.ai_orchestrator.crud_confirmation import (
            build_crud_confirmation_message,
        )
        enriched = MagicMock()
        enriched.intent_type = intent_type
        enriched.parameters = params
        return build_crud_confirmation_message(enriched)

    def test_resolved_name_in_standard_message(self):
        params = {
            'task_keyword': 'journal',
            'resolved_name': 'Morning Journal',
        }
        msg = self._build('complete_task', params)
        self.assertIn('Morning Journal', msg)

    def test_fallback_to_task_keyword_without_resolved_name(self):
        params = {'task_keyword': 'journal'}
        msg = self._build('complete_task', params)
        self.assertIn('journal', msg)

    def test_title_takes_precedence_over_keyword(self):
        params = {'title': 'Buy Groceries', 'task_keyword': 'groceries'}
        msg = self._build('create_task', params)
        self.assertIn('Buy Groceries', msg)

    def test_resolved_name_takes_precedence_over_title(self):
        params = {
            'title': 'Buy stuff',
            'resolved_name': 'Buy Groceries From Store',
        }
        msg = self._build('mutate_task', params)
        self.assertIn('Buy Groceries From Store', msg)
