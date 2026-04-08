"""
Phase 6.7 — Chat Execution Isolation + Input Persistence tests.

Covers:
- Idempotency in-flight marker (mark/is/clear)
- Context-required guard in orchestrator.enrich_and_execute
- Hard intent lock recorded in AssistantMessage.metadata
- send_message_stream guaranteed persistence on client disconnect
  (GeneratorExit) via the try/finally safety net
- Lifecycle metadata (request_id, status, stream_interrupted) on
  AssistantMessage
"""

from unittest.mock import MagicMock, patch

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase

from apps.ai.idempotency import (
    clear_in_flight,
    is_in_flight,
    mark_in_flight,
)
from apps.ai.models import AssistantConversation, AssistantMessage
from apps.users.models import TermsAcceptance

try:
    from apps.users.models import User
except ImportError:
    from django.contrib.auth import get_user_model
    User = get_user_model()


def _make_user(email):
    """Create a test user with onboarding + terms accepted."""
    user = User.objects.create_user(email=email, password='pw12345!')
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class InFlightIdempotencyTests(TestCase):
    """Tests for mark_in_flight / is_in_flight / clear_in_flight."""

    def setUp(self):
        cache.clear()

    def test_mark_and_retrieve(self):
        mark_in_flight(42, 'hello world', 'req-abc')
        marker = is_in_flight(42, 'hello world')
        self.assertIsNotNone(marker)
        self.assertEqual(marker['request_id'], 'req-abc')
        self.assertEqual(marker['status'], 'processing')

    def test_clear_removes_marker(self):
        mark_in_flight(42, 'log weight 185', 'req-xyz')
        self.assertIsNotNone(is_in_flight(42, 'log weight 185'))
        clear_in_flight(42, 'log weight 185')
        self.assertIsNone(is_in_flight(42, 'log weight 185'))

    def test_different_users_isolated(self):
        mark_in_flight(1, 'same message', 'req-1')
        mark_in_flight(2, 'same message', 'req-2')
        self.assertEqual(is_in_flight(1, 'same message')['request_id'], 'req-1')
        self.assertEqual(is_in_flight(2, 'same message')['request_id'], 'req-2')

    def test_different_messages_isolated(self):
        mark_in_flight(7, 'create task A', 'req-A')
        mark_in_flight(7, 'create task B', 'req-B')
        self.assertEqual(is_in_flight(7, 'create task A')['request_id'], 'req-A')
        self.assertEqual(is_in_flight(7, 'create task B')['request_id'], 'req-B')

    def test_is_in_flight_returns_none_when_unmarked(self):
        self.assertIsNone(is_in_flight(99, 'never sent'))

    def test_case_and_whitespace_normalized(self):
        mark_in_flight(5, '  Hello World  ', 'req-norm')
        # Same message with different casing / spacing should collide
        self.assertIsNotNone(is_in_flight(5, 'hello world'))
        self.assertIsNotNone(is_in_flight(5, 'HELLO WORLD'))


class ContextRequiredGuardTests(TestCase):
    """Tests for the context-required guard in enrich_and_execute."""

    def test_context_required_constant_includes_expected_intents(self):
        from apps.core.ai_orchestrator.action_policy import (
            CONTEXT_REQUIRED_INTENTS,
            requires_page_context,
        )
        # Sanity: the set is non-empty and the helper works.
        self.assertGreater(len(CONTEXT_REQUIRED_INTENTS), 0)
        self.assertTrue(requires_page_context('add_to_list'))
        self.assertTrue(requires_page_context('save_note'))
        self.assertFalse(requires_page_context('create_task'))
        self.assertFalse(requires_page_context('log_weight'))

    def test_missing_page_context_returns_context_required_error(self):
        """Phase 6.7: context-required intent without page_context must
        return the 'context lost' error, never execute silently."""
        from apps.core.ai_orchestrator.orchestrator import (
            OrchestratorResult,
            enrich_and_execute,
        )

        user = _make_user('ctx_guard@test.com')

        orch_result = OrchestratorResult(
            success=True, original_input='save this',
            page_context=None,  # <-- user navigated away
        )

        intent_result = MagicMock()
        intent_result.intent_type = 'add_to_list'
        intent_result.parameters = {'item': 'eggs'}

        results = enrich_and_execute(user, [intent_result], orch_result)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertEqual(results[0].error, 'context_required')
        self.assertIn('lost the context', results[0].message)

    def test_present_page_context_does_not_trigger_guard(self):
        """Phase 6.7: when context was captured, the guard must not fire."""
        from apps.core.ai_orchestrator.orchestrator import (
            OrchestratorResult,
            enrich_and_execute,
        )

        user = _make_user('ctx_ok@test.com')

        orch_result = OrchestratorResult(
            success=True, original_input='save this',
            page_context={
                'module': 'journal',
                'url': '/journal/123/',
                'help_context_id': 'JOURNAL_ENTRY',
            },
        )

        intent_result = MagicMock()
        intent_result.intent_type = 'add_to_list'
        intent_result.parameters = {'item': 'eggs'}

        # With context present, guard must NOT fire. The downstream
        # pipeline may still fail for unrelated reasons, but the error
        # must NOT be 'context_required'.
        with patch(
            'apps.core.ai_orchestrator.execution_engine.execute_action'
        ) as mock_exec:
            mock_exec.return_value = MagicMock(
                success=True, message='Added.',
                action_type='add_to_list',
                error=None, confirmation_detail=None,
            )
            results = enrich_and_execute(
                user, [intent_result], orch_result,
            )
        for r in results:
            self.assertNotEqual(r.error, 'context_required')

    def test_non_context_required_intent_works_without_context(self):
        """Phase 6.7: non-context-required intents proceed normally
        even when page_context is absent."""
        from apps.core.ai_orchestrator.orchestrator import (
            OrchestratorResult,
            enrich_and_execute,
        )

        user = _make_user('no_ctx_needed@test.com')

        orch_result = OrchestratorResult(
            success=True, original_input='log weight 185',
            page_context=None,
        )

        intent_result = MagicMock()
        intent_result.intent_type = 'log_weight'
        intent_result.parameters = {'weight': '185'}

        results = enrich_and_execute(user, [intent_result], orch_result)
        # log_weight is not in CONTEXT_REQUIRED_INTENTS so the guard
        # must not produce a context_required error. (It will produce
        # a crud_confirmation_required result, which is expected.)
        for r in results:
            self.assertNotEqual(r.error, 'context_required')


class StreamDisconnectPersistenceTests(TestCase):
    """Verifies that send_message_stream's try/finally safety net
    persists assistant_msg state even when the generator is closed early
    (simulating a client disconnect). This is the core of Phase 6.7."""

    def setUp(self):
        cache.clear()
        self.user = _make_user('disconnect@test.com')

    def tearDown(self):
        cache.clear()

    def _close_generator_after_first_yield(self, gen):
        """Consume one event from the generator, then close it early
        (raises GeneratorExit inside the generator body)."""
        try:
            next(gen)
        except StopIteration:
            pass
        gen.close()

    def test_client_disconnect_still_persists_assistant_message(self):
        """When the client disconnects mid-stream, the assistant_msg
        row must still carry request_id + status + stream_interrupted."""
        from apps.ai.personal_assistant import PersonalAssistant

        assistant = PersonalAssistant(self.user)
        conversation = assistant.get_or_create_conversation()

        # Patch AI service to short-circuit to a direct response that
        # exercises the try/finally path without hitting OpenAI.
        with patch('apps.ai.personal_assistant.ai_service') as mock_ai:
            mock_ai.is_available = False  # forces fallback direct path

            gen = assistant.send_message_stream(
                message='test disconnect message',
                conversation=conversation,
                page_context={'url': '/dashboard/'},
            )
            # Simulate client disconnect after first token
            self._close_generator_after_first_yield(gen)

        # After close, reload the assistant message — its metadata must
        # record the lifecycle state.
        msgs = AssistantMessage.objects.filter(
            conversation=conversation, role='assistant',
        ).order_by('-created_at')
        self.assertGreater(msgs.count(), 0)
        msg = msgs.first()
        self.assertIsNotNone(msg.metadata)
        self.assertIn('request_id', msg.metadata)
        self.assertIn('status', msg.metadata)
        # status should be 'completed' (with stream_interrupted=True)
        # or 'failed' — either way, NOT 'processing' (the finally ran).
        self.assertIn(
            msg.metadata.get('status'),
            ('completed', 'failed'),
        )

    def test_successful_stream_marks_status_completed(self):
        """Happy path: no disconnect, status should be 'completed' and
        stream_interrupted should be False."""
        from apps.ai.personal_assistant import PersonalAssistant

        assistant = PersonalAssistant(self.user)
        conversation = assistant.get_or_create_conversation()

        with patch('apps.ai.personal_assistant.ai_service') as mock_ai:
            mock_ai.is_available = False

            gen = assistant.send_message_stream(
                message='happy path message',
                conversation=conversation,
                page_context={'url': '/dashboard/'},
            )
            # Drain the generator fully
            for _ in gen:
                pass

        msg = AssistantMessage.objects.filter(
            conversation=conversation, role='assistant',
        ).order_by('-created_at').first()
        self.assertIsNotNone(msg)
        self.assertIsNotNone(msg.metadata)
        self.assertEqual(msg.metadata.get('status'), 'completed')
        self.assertFalse(msg.metadata.get('stream_interrupted', True))
        self.assertIn('request_id', msg.metadata)


class DuplicateRequestSuppressionTests(TestCase):
    """Phase 6.7 + 6.8: a second in-flight request for the same
    (user, message) must return a STRUCTURED duplicate payload (not a
    plain "still working on it" string) so the frontend can render a
    dedicated card with the original message + a recovery action."""

    def setUp(self):
        cache.clear()
        self.user = _make_user('dup_suppress@test.com')

    def tearDown(self):
        cache.clear()

    def test_inflight_marker_suppresses_duplicate(self):
        from apps.ai.personal_assistant import PersonalAssistant

        # Pre-mark an in-flight request from an earlier call
        mark_in_flight(self.user.id, 'duplicate check', 'old-request-id')

        assistant = PersonalAssistant(self.user)
        conversation = assistant.get_or_create_conversation()

        with patch('apps.ai.personal_assistant.ai_service') as mock_ai:
            mock_ai.is_available = False
            gen = assistant.send_message_stream(
                message='duplicate check',
                conversation=conversation,
            )
            events = list(gen)

        done_events = [
            e for e in events
            if isinstance(e, dict) and e.get('type') == 'done'
        ]
        self.assertEqual(len(done_events), 1)
        self.assertEqual(
            done_events[0]['data'].get('status'), 'processing',
        )
        self.assertEqual(
            done_events[0]['data'].get('request_id'), 'old-request-id',
        )

    def test_duplicate_payload_is_structured(self):
        """Phase 6.8: the duplicate-suppression event must be a
        'duplicate_pending' type carrying original_message, request_id,
        status, and pending_seconds_ago."""
        from apps.ai.personal_assistant import PersonalAssistant

        mark_in_flight(self.user.id, 'check the diff', 'inflight-xyz')

        assistant = PersonalAssistant(self.user)
        conversation = assistant.get_or_create_conversation()

        with patch('apps.ai.personal_assistant.ai_service') as mock_ai:
            mock_ai.is_available = False
            events = list(assistant.send_message_stream(
                message='check the diff',
                conversation=conversation,
            ))

        dup_events = [
            e for e in events
            if isinstance(e, dict) and e.get('type') == 'duplicate_pending'
        ]
        self.assertEqual(len(dup_events), 1)
        payload = dup_events[0]['data']
        self.assertTrue(payload.get('duplicate_suppressed'))
        self.assertEqual(payload.get('status'), 'processing')
        self.assertEqual(payload.get('request_id'), 'inflight-xyz')
        self.assertEqual(payload.get('original_message'), 'check the diff')
        self.assertIn('pending_seconds_ago', payload)
        self.assertIsInstance(payload['pending_seconds_ago'], int)
        self.assertGreaterEqual(payload['pending_seconds_ago'], 0)
        self.assertIn('submitted_at_ms', payload)

    def test_no_vague_text_fallback_in_duplicate_path(self):
        """Phase 6.8: the duplicate path must NOT yield a free-text
        token event with the old vague 'Still working on it' message."""
        from apps.ai.personal_assistant import PersonalAssistant

        mark_in_flight(self.user.id, 'no vague text', 'inflight-1')
        assistant = PersonalAssistant(self.user)
        conversation = assistant.get_or_create_conversation()

        with patch('apps.ai.personal_assistant.ai_service') as mock_ai:
            mock_ai.is_available = False
            events = list(assistant.send_message_stream(
                message='no vague text',
                conversation=conversation,
            ))

        token_events = [
            e for e in events
            if isinstance(e, dict) and e.get('type') == 'token'
        ]
        # The duplicate-suppression branch must NOT emit any token
        # events — only duplicate_pending + done.
        for tok in token_events:
            self.assertNotIn(
                'Still working',
                tok.get('content', ''),
            )
        # Affirmatively: there should be zero token events.
        self.assertEqual(
            len(token_events), 0,
            'Duplicate path emitted token events instead of '
            'a structured duplicate_pending event',
        )


class InFlightMarkerSchemaTests(TestCase):
    """Phase 6.8: the in-flight marker carries original_message and
    submitted_at_ms so the duplicate-pending card can echo the request
    text and render 'submitted Xs ago'."""

    def setUp(self):
        cache.clear()

    def test_marker_carries_original_message(self):
        mark_in_flight(11, 'log my workout', 'req-workout')
        marker = is_in_flight(11, 'log my workout')
        self.assertEqual(marker['original_message'], 'log my workout')

    def test_marker_carries_submitted_at_ms(self):
        import time
        before = int(time.time() * 1000)
        mark_in_flight(12, 'add a task', 'req-task')
        after = int(time.time() * 1000)
        marker = is_in_flight(12, 'add a task')
        self.assertIn('submitted_at_ms', marker)
        self.assertGreaterEqual(marker['submitted_at_ms'], before)
        self.assertLessEqual(marker['submitted_at_ms'], after)

    def test_rapid_resubmissions_overwrite_marker(self):
        """Multiple rapid submissions for the same (user, message)
        should converge on the most recent marker — not stack or
        deadlock — so the duplicate card always shows the latest
        submitted_at."""
        import time
        mark_in_flight(13, 'rapid send', 'req-1')
        first = is_in_flight(13, 'rapid send')
        time.sleep(0.01)
        mark_in_flight(13, 'rapid send', 'req-2')
        time.sleep(0.01)
        mark_in_flight(13, 'rapid send', 'req-3')
        latest = is_in_flight(13, 'rapid send')
        self.assertEqual(latest['request_id'], 'req-3')
        self.assertGreaterEqual(
            latest['submitted_at_ms'], first['submitted_at_ms'],
        )


class LifecycleHistorySurfaceTests(TestCase):
    """Phase 6.8: the history endpoint must surface the lifecycle
    metadata (request_id, status, stream_interrupted) so the frontend
    can render the correct status badge for every assistant message."""

    def setUp(self):
        self.user = _make_user('lifecycle_history@test.com')

    def test_history_payload_includes_lifecycle_for_assistant_msgs(self):
        from django.test import Client
        conv = AssistantConversation.objects.create(user=self.user)
        AssistantMessage.objects.create(
            conversation=conv, role='user', content='hi',
            message_type='text',
        )
        AssistantMessage.objects.create(
            conversation=conv, role='assistant',
            content='Hello back.',
            message_type='text',
            metadata={
                'request_id': 'lifecycle-req-1',
                'status': 'completed',
                'stream_interrupted': True,
                'intent_locked': False,
            },
        )

        client = Client()
        client.force_login(self.user)
        resp = client.get('/assistant/api/history/')
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload.get('success'))
        # Find the assistant message and verify the lifecycle dict
        assistant_msgs = [
            m for m in payload['messages'] if m['role'] == 'assistant'
        ]
        self.assertGreater(len(assistant_msgs), 0)
        target = next(
            (m for m in assistant_msgs
             if (m.get('lifecycle') or {}).get('request_id') == 'lifecycle-req-1'),
            None,
        )
        self.assertIsNotNone(
            target,
            'Assistant message lifecycle metadata not surfaced in history',
        )
        lc = target['lifecycle']
        self.assertEqual(lc['status'], 'completed')
        self.assertTrue(lc['stream_interrupted'])

    def test_history_payload_omits_lifecycle_for_user_msgs(self):
        """User messages should not carry a lifecycle dict (it's an
        assistant-only concept)."""
        from django.test import Client
        conv = AssistantConversation.objects.create(user=self.user)
        AssistantMessage.objects.create(
            conversation=conv, role='user', content='another',
            message_type='text',
        )
        client = Client()
        client.force_login(self.user)
        resp = client.get('/assistant/api/history/')
        payload = resp.json()
        for m in payload['messages']:
            if m['role'] == 'user':
                self.assertNotIn('lifecycle', m)
