"""
P0 navigation fix — background chat generation tests.

Covers the architecture that lets generation continue after the user
navigates away:

- chat_stream_bus snapshot read/write/clear + SSE framing
- run_chat_generation Celery task owns generation independent of any HTTP
  request, persists the assistant message, and reaches a terminal snapshot
  status (started/completed/failed telemetry path)
- the resume endpoint enforces ownership (403), 410s on expired jobs, and
  streams the snapshot to the owner
- the streaming POST dispatches the task and relays without creating a
  duplicate assistant message or leaving an orphan 'processing' placeholder
- disconnecting the relay does NOT interrupt the task
"""

from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import Client, TestCase, TransactionTestCase

from apps.ai import chat_stream_bus as bus
from apps.ai.models import AssistantConversation, AssistantMessage
from apps.ai.tasks import run_chat_generation
from apps.users.models import TermsAcceptance

try:
    from apps.users.models import User
except ImportError:
    from django.contrib.auth import get_user_model
    User = get_user_model()


def _make_user(email):
    user = User.objects.create_user(email=email, password='pw12345!')
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
    )
    prefs = user.preferences
    prefs.has_completed_onboarding = True
    # The streaming view gates on the Personal Assistant prerequisites
    # (check_personal_assistant_enabled): AI + consent + assistant module.
    prefs.ai_enabled = True
    prefs.ai_data_consent = True
    prefs.personal_assistant_enabled = True
    prefs.personal_assistant_consent = True
    prefs.save()
    return user


def _join_stream(response):
    """Decode a StreamingHttpResponse body into a single string."""
    chunks = []
    for c in response.streaming_content:
        chunks.append(c.decode('utf-8') if isinstance(c, bytes) else c)
    return ''.join(chunks)


class ChatStreamBusTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_new_snapshot_shape(self):
        snap = bus.new_snapshot(7, 99)
        self.assertEqual(snap['owner'], 7)
        self.assertEqual(snap['conversation_id'], 99)
        self.assertEqual(snap['status'], 'queued')
        self.assertEqual(snap['text'], '')
        self.assertEqual(snap['events'], [])

    def test_write_read_clear_roundtrip(self):
        snap = bus.new_snapshot(1, 1)
        snap['text'] = 'hello'
        bus.write('job-1', snap)
        got = bus.read('job-1')
        self.assertIsNotNone(got)
        self.assertEqual(got['text'], 'hello')
        bus.clear('job-1')
        self.assertIsNone(bus.read('job-1'))

    def test_read_unknown_returns_none(self):
        self.assertIsNone(bus.read('does-not-exist'))

    def test_format_sse_token(self):
        frame = bus.format_sse({'type': 'token', 'content': 'hi'})
        self.assertIn('event: token', frame)
        self.assertIn('"content": "hi"', frame)
        self.assertTrue(frame.endswith('\n\n'))

    def test_format_sse_done_carries_data(self):
        frame = bus.format_sse(
            {'type': 'done', 'data': {'conversation_id': 5, 'request_id': 'r'}}
        )
        self.assertIn('event: done', frame)
        self.assertIn('"conversation_id": 5', frame)

    def test_format_sse_correction_and_error(self):
        self.assertIn(
            'event: correction',
            bus.format_sse({'type': 'correction', 'content': 'fixed'}),
        )
        self.assertIn(
            'event: error',
            bus.format_sse({'type': 'error', 'error': 'boom'}),
        )

    def test_format_sse_unknown_type_is_empty(self):
        # 'quick_replies' was not surfaced by the legacy view — preserve that.
        self.assertEqual(bus.format_sse({'type': 'quick_replies'}), '')

    def test_terminal_statuses(self):
        self.assertIn('done', bus.TERMINAL_STATUSES)
        self.assertIn('failed', bus.TERMINAL_STATUSES)
        self.assertIn('interrupted', bus.TERMINAL_STATUSES)
        self.assertNotIn('processing', bus.TERMINAL_STATUSES)


class RunChatGenerationTaskTests(TestCase):
    """The task owns generation: it persists the assistant message and
    drives the snapshot to a terminal status with no HTTP request involved
    (proving generation is not coupled to a live connection)."""

    def setUp(self):
        cache.clear()
        self.user = _make_user('chat_task@test.com')

    def tearDown(self):
        cache.clear()

    @patch('apps.ai.tasks._run_chat_post_response')
    def test_task_completes_and_persists(self, _mock_post):
        from apps.ai.personal_assistant import PersonalAssistant

        assistant = PersonalAssistant(self.user)
        conversation = assistant.get_or_create_conversation()
        bus.write('job-task-1', bus.new_snapshot(self.user.id, conversation.id))

        with patch('apps.ai.personal_assistant.ai_service') as mock_ai:
            mock_ai.is_available = False  # fallback direct path, no OpenAI
            run_chat_generation(
                self.user.id, conversation.id,
                'what should I focus on', {}, 'job-task-1',
            )

        snap = bus.read('job-task-1')
        self.assertIsNotNone(snap)
        self.assertEqual(snap['status'], 'done')
        self.assertTrue(len(snap['text']) > 0)
        # done control event present
        self.assertTrue(
            any(e.get('type') == 'done' for e in snap['events']),
            'snapshot missing done event',
        )

        # Exactly one assistant message persisted, with non-empty content
        # (no orphan 'processing' placeholder left behind).
        amsgs = AssistantMessage.objects.filter(
            conversation=conversation, role='assistant',
        )
        self.assertEqual(amsgs.count(), 1)
        msg = amsgs.first()
        self.assertTrue(msg.content.strip())
        self.assertNotEqual(msg.metadata.get('status'), 'processing')

    @patch('apps.ai.tasks._run_chat_post_response')
    def test_task_failure_marks_snapshot_failed(self, _mock_post):
        bus.write('job-fail', bus.new_snapshot(self.user.id, 1))
        with patch(
            'apps.ai.personal_assistant.PersonalAssistant.send_message_stream',
            side_effect=RuntimeError('kaboom'),
        ):
            run_chat_generation(
                self.user.id, 1, 'trigger error', {}, 'job-fail',
            )
        snap = bus.read('job-fail')
        self.assertEqual(snap['status'], 'failed')
        self.assertTrue(any(e.get('type') == 'error' for e in snap['events']))

    @patch('apps.ai.tasks._run_chat_post_response')
    def test_missing_user_marks_failed(self, _mock_post):
        bus.write('job-nouser', bus.new_snapshot(999999, 1))
        run_chat_generation(999999, 1, 'hi', {}, 'job-nouser')
        snap = bus.read('job-nouser')
        self.assertEqual(snap['status'], 'failed')


class ChatResumeViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _make_user('resume_owner@test.com')
        self.other = _make_user('resume_other@test.com')

    def tearDown(self):
        cache.clear()

    def test_resume_forbidden_for_non_owner(self):
        snap = bus.new_snapshot(self.user.id, 1)
        snap['status'] = 'processing'
        bus.write('job-own', snap)

        client = Client()
        client.force_login(self.other)
        resp = client.get('/assistant/api/chat/stream/resume/job-own/')
        self.assertEqual(resp.status_code, 403)

    def test_resume_expired_returns_410(self):
        client = Client()
        client.force_login(self.user)
        resp = client.get('/assistant/api/chat/stream/resume/missing-job/')
        self.assertEqual(resp.status_code, 410)

    def test_resume_owner_streams_snapshot(self):
        snap = bus.new_snapshot(self.user.id, 1)
        snap['text'] = 'partial answer so far'
        snap['events'] = [
            {'type': 'done', 'data': {'conversation_id': 1, 'request_id': 'r'}}
        ]
        snap['status'] = 'done'
        bus.write('job-done', snap)

        client = Client()
        client.force_login(self.user)
        resp = client.get('/assistant/api/chat/stream/resume/job-done/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/event-stream', resp['Content-Type'])
        body = _join_stream(resp)
        self.assertIn('event: job', body)
        self.assertIn('partial answer so far', body)
        self.assertIn('event: done', body)

    def test_resume_requires_authentication(self):
        resp = Client().get('/assistant/api/chat/stream/resume/whatever/')
        self.assertIn(resp.status_code, (302, 403))


class ChatStreamPostIntegrationTests(TransactionTestCase):
    """End-to-end (eager): POST dispatches the task and relays its output.

    Uses TransactionTestCase, not TestCase: dispatching the task via .delay()
    fires Celery's task_postrun, whose Django fixup closes the DB connection.
    That would break TestCase's single class-level transaction; without an
    enclosing atomic block, Django simply reconnects on the next query.
    """

    def setUp(self):
        cache.clear()
        self.user = _make_user('chat_post@test.com')

    def tearDown(self):
        cache.clear()

    @patch('apps.ai.tasks._run_chat_post_response')
    def test_post_streams_job_token_done(self, _mock_post):
        client = Client()
        client.force_login(self.user)
        with patch('apps.ai.personal_assistant.ai_service') as mock_ai:
            mock_ai.is_available = False
            resp = client.post(
                '/assistant/api/chat/stream/',
                data={'message': 'give me a quick plan', 'page_context': {}},
                content_type='application/json',
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn('text/event-stream', resp['Content-Type'])
            body = _join_stream(resp)

        self.assertIn('event: job', body)
        self.assertIn('event: done', body)

    @patch('apps.ai.tasks._run_chat_post_response')
    def test_post_creates_single_assistant_message(self, _mock_post):
        """No duplicate assistant messages, no orphan processing placeholder."""
        client = Client()
        client.force_login(self.user)
        with patch('apps.ai.personal_assistant.ai_service') as mock_ai:
            mock_ai.is_available = False
            resp = client.post(
                '/assistant/api/chat/stream/',
                data={'message': 'one reply only', 'page_context': {}},
                content_type='application/json',
            )
            _join_stream(resp)  # drain

        conv = AssistantConversation.get_or_create_active(self.user)
        amsgs = AssistantMessage.objects.filter(
            conversation=conv, role='assistant',
        )
        self.assertEqual(amsgs.count(), 1)
        self.assertTrue(amsgs.first().content.strip())

    @patch('apps.ai.tasks._run_chat_post_response')
    def test_disconnect_does_not_interrupt_persistence(self, _mock_post):
        """Abandoning the relay (not draining streaming_content) must not
        stop the task — the assistant message is still persisted because the
        task ran to completion independently during dispatch (eager)."""
        client = Client()
        client.force_login(self.user)
        with patch('apps.ai.personal_assistant.ai_service') as mock_ai:
            mock_ai.is_available = False
            resp = client.post(
                '/assistant/api/chat/stream/',
                data={'message': 'abandoned relay', 'page_context': {}},
                content_type='application/json',
            )
            # Intentionally do NOT consume resp.streaming_content (simulate
            # the client navigating away the instant the response starts).
            resp.close()

        conv = AssistantConversation.get_or_create_active(self.user)
        msg = AssistantMessage.objects.filter(
            conversation=conv, role='assistant',
        ).order_by('-created_at').first()
        self.assertIsNotNone(msg)
        self.assertTrue(msg.content.strip())
        self.assertNotEqual(msg.metadata.get('status'), 'processing')

    def test_empty_message_rejected(self):
        client = Client()
        client.force_login(self.user)
        resp = client.post(
            '/assistant/api/chat/stream/',
            data={'message': '   ', 'page_context': {}},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
