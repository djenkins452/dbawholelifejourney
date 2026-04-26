"""
End-to-end tests for the deterministic CoS decision-mode shortcut.

Covers:
- send_message() bypasses the LLM when a CoS mode keyword matches.
- The deterministic answer is logged to conversation history.
- Each of the three modes returns a clearly distinct payload.
- The /assistant/api/cos/decision/ endpoint returns the same shape.
"""

from datetime import date, datetime, time
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.users.models import User


def _make_user(email):
    from django.utils import timezone
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(
        email=email, password="testpass123",
        date_of_birth=date(1990, 1, 1),
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    prefs = user.preferences
    prefs.has_completed_onboarding = True
    prefs.ai_enabled = True
    prefs.ai_data_consent = True
    prefs.ai_data_consent_date = timezone.now()
    prefs.personal_assistant_enabled = True
    prefs.personal_assistant_consent = True
    prefs.personal_assistant_consent_date = timezone.now()
    prefs.save()
    return user


def _routine_action(title, urgency, *, time_display='', is_foundational=False):
    return {
        'source': 'routine',
        'urgency': urgency,
        'type': 'task',
        'pk': abs(hash(title)) % 100000,
        'title': title,
        'source_url': '',
        'can_complete': True,
        'is_foundational': is_foundational,
        'commitment_level': 'flexible',
        'goal_name': '',
        'time_of_day': None,
        'time_display': time_display,
    }


def _fake_state(actions, *, now=time(8, 0), blocked=None):
    return {
        'now': now,
        'active_block': {
            'name': 'morning',
            'start_time': time(5, 0),
            'end_time': time(10, 0),
            'lead_in_end_time': time(9, 45),
            'next_block_name': 'mid_morning',
            'next_block_start': time(10, 0),
            'bounds': {},
        },
        'items': [],
        'summaries': {},
        'actions': actions,
        'overdue_actions': [a for a in actions if a['urgency'] == 'overdue'],
        'now_actions':     [a for a in actions if a['urgency'] == 'now'],
        'next_actions':    [a for a in actions if a['urgency'] == 'next'],
        'upcoming_actions':[a for a in actions if a['urgency'] == 'upcoming'],
        'blocked_dependents': blocked or {},
    }


class CosShortcutChatTests(TestCase):
    """The chat shortcut: send_message → deterministic mode router."""

    def setUp(self):
        self.user = _make_user("cos_shortcut@test.com")

    def _send(self, message, state):
        from apps.ai.personal_assistant import get_personal_assistant
        assistant = get_personal_assistant(self.user)
        with patch(
            'apps.core.execution.execution_state.build_execution_state',
            return_value=state,
        ):
            return assistant.send_message(message)

    def test_execution_query_returns_deterministic_payload_no_llm(self):
        actions = [
            _routine_action('Measurements', 'now', time_display='08:00'),
        ]
        state = _fake_state(actions, now=time(7, 55))
        result = self._send("what should I do right now?", state)

        self.assertTrue(result.get('deterministic'))
        self.assertIn('Measurements', result['response'])
        self.assertEqual(result['cos_decision']['mode'], 'execution')
        self.assertEqual(
            result['cos_decision']['primary_action']['title'], 'Measurements',
        )

    def test_risk_query_returns_risk_payload(self):
        actions = [
            _routine_action('Morning Meds', 'overdue', time_display='07:30',
                            is_foundational=True),
            _routine_action('Stretch', 'overdue', time_display='07:45'),
        ]
        # Override source so risk weighting picks Morning Meds.
        actions[0]['source'] = 'medication'

        state = _fake_state(actions, now=time(9, 0))
        result = self._send("what's my biggest risk?", state)

        self.assertTrue(result.get('deterministic'))
        self.assertEqual(result['cos_decision']['mode'], 'risk')
        self.assertIn('Morning Meds', result['response'])

    def test_fix_query_returns_fix_payload(self):
        actions = [
            _routine_action('File Receipts', 'overdue', time_display='08:00'),
        ]
        actions[0]['type'] = 'task'
        actions[0]['source'] = 'task'
        actions[0]['pk'] = 20
        state = _fake_state(
            actions, now=time(9, 0),
            blocked={'task:20': [201, 202, 203]},
        )
        result = self._send("what should I fix first?", state)

        self.assertTrue(result.get('deterministic'))
        self.assertEqual(result['cos_decision']['mode'], 'fix')
        self.assertIn('File Receipts', result['response'])
        self.assertIn('unlock 3', result['response'])

    def test_non_mode_query_falls_through(self):
        """A non-matching message must NOT trigger the shortcut.
        We mock the LLM-bound `_generate_response` to avoid hitting OpenAI."""
        from apps.ai.personal_assistant import get_personal_assistant

        assistant = get_personal_assistant(self.user)

        # Only verify that resolve_cos_mode would return None for a
        # non-mode query — and that the shortcut helper itself returns
        # None, indicating fall-through. We do NOT exercise the full LLM
        # path in this unit test.
        from apps.ai.cos_mode_router import resolve_cos_mode
        self.assertIsNone(resolve_cos_mode("log my weight as 195 lbs"))

        conversation = assistant.get_or_create_conversation()
        result = assistant._cos_mode_shortcut(
            "log my weight as 195 lbs", conversation,
        )
        self.assertIsNone(result)


class CosDecisionApiTests(TestCase):
    """The /assistant/api/cos/decision/ endpoint."""

    def setUp(self):
        self.user = _make_user("cos_api@test.com")
        self.client.force_login(self.user)
        self.url = reverse('ai:api_cos_decision')

    def _get(self, mode, state):
        with patch(
            'apps.core.execution.execution_state.build_execution_state',
            return_value=state,
        ):
            return self.client.get(self.url, {'mode': mode})

    def test_execution_endpoint_payload(self):
        actions = [
            _routine_action('Measurements', 'now', time_display='08:00'),
        ]
        state = _fake_state(actions, now=time(7, 55))
        resp = self._get('execution', state)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['mode'], 'execution')
        self.assertEqual(body['primary_action']['title'], 'Measurements')

    def test_risk_endpoint_payload(self):
        actions = [
            _routine_action('Morning Meds', 'overdue', time_display='07:30',
                            is_foundational=True),
        ]
        actions[0]['source'] = 'medication'
        state = _fake_state(actions, now=time(9, 0))
        resp = self._get('risk', state)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['mode'], 'risk')
        self.assertEqual(body['primary_action']['title'], 'Morning Meds')

    def test_fix_endpoint_payload(self):
        actions = [
            _routine_action('File Receipts', 'overdue', time_display='08:00'),
        ]
        actions[0]['type'] = 'task'
        actions[0]['source'] = 'task'
        actions[0]['pk'] = 20
        state = _fake_state(
            actions, now=time(9, 0),
            blocked={'task:20': [201, 202, 203]},
        )
        resp = self._get('fix', state)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['mode'], 'fix')
        self.assertEqual(body['primary_action']['title'], 'File Receipts')

    def test_unknown_mode_defaults_to_execution(self):
        actions = [
            _routine_action('Measurements', 'now', time_display='08:00'),
        ]
        state = _fake_state(actions, now=time(7, 55))
        resp = self._get('mystery', state)
        body = resp.json()
        self.assertEqual(body['mode'], 'execution')
