"""
Phase 8 — Self-Governance Tests.

Tests for SRI computation, Level 2 auto-escalation,
governance email triggers, and integration.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone


def _create_test_user(email='governance-test@example.com'):
    from apps.users.models import User
    return User.objects.create_user(email=email, password='testpass123')


def _create_self_error(user, level=1, category='NUMERIC',
                       trigger_code='NUMERIC_DEVIATION',
                       trigger_detail='test', was_blocked=False,
                       created_at=None):
    """Helper to create a SelfError with optional backdated timestamp."""
    from apps.core.ai_governance.models import SelfError
    err = SelfError.objects.create(
        user=user,
        level=level,
        category=category,
        trigger_code=trigger_code,
        trigger_detail=trigger_detail,
        was_blocked=was_blocked,
    )
    if created_at:
        SelfError.objects.filter(pk=err.pk).update(created_at=created_at)
        err.refresh_from_db()
    return err


# =========================================================================
# SRI COMPUTATION
# =========================================================================


class SRIComputationTests(TestCase):
    """Test compute_sri() — rolling 30-day Self-Reliability Index."""

    def setUp(self):
        self.user = _create_test_user()

    def test_sri_100_with_no_errors(self):
        """Empty SelfError table → score=100.0."""
        from apps.core.ai_governance.self_governance import compute_sri

        result = compute_sri()
        self.assertEqual(result['score'], 100.0)
        self.assertEqual(result['total_errors'], 0)

    def test_sri_penalized_by_level1_errors(self):
        """10 Level 1 errors → score = 100 - (10 * 0.5) = 95.0."""
        from apps.core.ai_governance.self_governance import compute_sri

        for i in range(10):
            _create_self_error(self.user, level=1)

        result = compute_sri()
        self.assertEqual(result['score'], 95.0)
        self.assertEqual(result['total_errors'], 10)
        self.assertEqual(result['numeric_errors'], 10)

    def test_sri_penalized_by_level3_errors(self):
        """3 Level 3 errors → score = 100 - (3 * 10) = 70.0."""
        from apps.core.ai_governance.self_governance import compute_sri

        for i in range(3):
            _create_self_error(
                self.user, level=3, category='GOVERNANCE',
                trigger_code='VALIDATOR_CRASH',
            )

        result = compute_sri()
        self.assertEqual(result['score'], 70.0)
        self.assertEqual(result['level3_count'], 3)
        self.assertEqual(result['governance_errors'], 3)

    def test_sri_floor_at_zero(self):
        """Massive error count → score=0.0, not negative."""
        from apps.core.ai_governance.self_governance import compute_sri

        for i in range(20):
            _create_self_error(
                self.user, level=3, category='GOVERNANCE',
                trigger_code='VALIDATOR_CRASH',
            )

        result = compute_sri()
        self.assertEqual(result['score'], 0.0)

    def test_sri_30_day_window_excludes_old_errors(self):
        """Errors from 31+ days ago are not counted."""
        from apps.core.ai_governance.self_governance import compute_sri

        now = timezone.now()
        # Old error — 35 days ago
        _create_self_error(
            self.user, level=3, category='GOVERNANCE',
            trigger_code='VALIDATOR_CRASH',
            created_at=now - timedelta(days=35),
        )
        # Recent error — 5 days ago
        _create_self_error(
            self.user, level=1,
            created_at=now - timedelta(days=5),
        )

        result = compute_sri(as_of=now)
        # Only the recent L1 error counts
        self.assertEqual(result['total_errors'], 1)
        self.assertEqual(result['score'], 99.5)

    def test_sri_frozen_time(self):
        """as_of parameter freezes window — same call = same result."""
        from apps.core.ai_governance.self_governance import compute_sri

        fixed_time = timezone.now()
        _create_self_error(self.user, level=2, category='STRUCTURAL',
                           trigger_code='BANNED_TERM_LEAKED',
                           was_blocked=True)

        result1 = compute_sri(as_of=fixed_time)
        result2 = compute_sri(as_of=fixed_time)
        self.assertEqual(result1['score'], result2['score'])
        self.assertEqual(result1['total_errors'], result2['total_errors'])


# =========================================================================
# LEVEL 2 AUTO-ESCALATION
# =========================================================================


class Level2AutoEscalationTests(TestCase):
    """Test repeated Level 2 → Level 3 auto-escalation."""

    def setUp(self):
        self.user = _create_test_user('escalation-test@example.com')

    def test_level2_escalates_after_5_repeats_in_7_days(self):
        """5 identical Level 2 trigger_codes in 7 days → next becomes Level 3."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.self_governance import record_self_error

        now = timezone.now()
        # Create 5 existing Level 2 errors with same trigger
        for i in range(5):
            _create_self_error(
                self.user, level=2, category='STRUCTURAL',
                trigger_code='BANNED_TERM_LEAKED',
                created_at=now - timedelta(days=i),
            )

        # 6th occurrence should auto-escalate to Level 3
        err = record_self_error(
            user=self.user,
            level=2,
            category='STRUCTURAL',
            trigger_code='BANNED_TERM_LEAKED',
            trigger_detail='Another banned term leak',
        )

        self.assertIsNotNone(err)
        self.assertEqual(err.level, SelfError.LEVEL_CRITICAL)
        self.assertTrue(err.metadata.get('auto_escalated_from') == 2)

    def test_level2_no_escalation_below_threshold(self):
        """4 repeats → stays Level 2."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.self_governance import record_self_error

        now = timezone.now()
        # Create 4 existing Level 2 errors
        for i in range(4):
            _create_self_error(
                self.user, level=2, category='STRUCTURAL',
                trigger_code='BANNED_TERM_LEAKED',
                created_at=now - timedelta(days=i),
            )

        # 5th occurrence — now exactly at threshold
        # But check_level2_auto_escalation checks count BEFORE this one
        # so 4 existing < 5 threshold → no escalation
        err = record_self_error(
            user=self.user,
            level=2,
            category='STRUCTURAL',
            trigger_code='BANNED_TERM_LEAKED',
            trigger_detail='test',
        )

        self.assertIsNotNone(err)
        self.assertEqual(err.level, SelfError.LEVEL_MODERATE)

    def test_level2_escalation_window_respects_7_days(self):
        """5 repeats but spread over 8 days → no escalation."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.self_governance import record_self_error

        now = timezone.now()
        # Create 5 errors, but some outside 7-day window
        for i in range(5):
            _create_self_error(
                self.user, level=2, category='STRUCTURAL',
                trigger_code='BANNED_TERM_LEAKED',
                # Days 6, 7, 8, 9, 10 — last 3 are outside 7-day window
                created_at=now - timedelta(days=6 + i),
            )

        err = record_self_error(
            user=self.user,
            level=2,
            category='STRUCTURAL',
            trigger_code='BANNED_TERM_LEAKED',
            trigger_detail='test',
        )

        # Only 2 of the 5 are within 7 days (days 6, 7)
        # So total count < 5 → no escalation
        self.assertIsNotNone(err)
        self.assertEqual(err.level, SelfError.LEVEL_MODERATE)


# =========================================================================
# GOVERNANCE EMAIL TRIGGERS
# =========================================================================


@override_settings(
    ADMINS=[('Test Admin', 'admin@test.com')],
    DEFAULT_FROM_EMAIL='noreply@test.com',
)
class GovernanceEmailTests(TestCase):
    """Test governance email triggers on Level 3 events."""

    def setUp(self):
        self.user = _create_test_user('email-test@example.com')

    @patch('apps.core.ai_governance.self_governance.send_mail')
    def test_level3_triggers_governance_email(self, mock_send_mail):
        """Level 3 SelfError → send_mail called to ADMINS."""
        from apps.core.ai_governance.self_governance import record_self_error

        record_self_error(
            user=self.user,
            level=3,
            category='GOVERNANCE',
            trigger_code='VALIDATOR_CRASH',
            trigger_detail='Test crash',
        )

        mock_send_mail.assert_called_once()
        call_kwargs = mock_send_mail.call_args
        self.assertIn('Critical Self-Error', call_kwargs[1]['subject'])
        self.assertIn('admin@test.com', call_kwargs[1]['recipient_list'])

    @patch('apps.core.ai_governance.self_governance.send_mail')
    def test_level2_does_not_trigger_email(self, mock_send_mail):
        """Level 2 → no email."""
        from apps.core.ai_governance.self_governance import record_self_error

        record_self_error(
            user=self.user,
            level=2,
            category='STRUCTURAL',
            trigger_code='BANNED_TERM_LEAKED',
            trigger_detail='Test term',
        )

        mock_send_mail.assert_not_called()

    @patch('apps.core.ai_governance.self_governance.send_mail')
    def test_governance_email_contains_no_technical_jargon(self, mock_send_mail):
        """Email body has no banned system terms."""
        from apps.core.ai_governance.language_rules import BANNED_TERMS
        from apps.core.ai_governance.self_governance import record_self_error

        record_self_error(
            user=self.user,
            level=3,
            category='GOVERNANCE',
            trigger_code='VALIDATOR_CRASH',
            trigger_detail='Test crash detail',
        )

        if mock_send_mail.called:
            body = mock_send_mail.call_args[1]['message'].lower()
            for term in BANNED_TERMS:
                self.assertNotIn(
                    term.lower(), body,
                    f"Governance email contains banned term: '{term}'",
                )


# =========================================================================
# INTEGRATION
# =========================================================================


@override_settings(
    ADMINS=[('Test Admin', 'admin@test.com')],
    DEFAULT_FROM_EMAIL='noreply@test.com',
)
class IntegrationTests(TestCase):
    """End-to-end integration of SelfError recording + escalation + email."""

    def setUp(self):
        self.user = _create_test_user('integration-test@example.com')

    @patch('apps.core.ai_governance.self_governance.send_mail')
    def test_record_self_error_with_auto_escalation_and_email(
        self, mock_send_mail,
    ):
        """
        End-to-end: Level 2 error that triggers escalation to Level 3
        → SelfError saved as Level 3, email sent, OpsAnomaly created.
        """
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_observability.models import OpsAnomaly
        from apps.core.ai_governance.self_governance import record_self_error

        now = timezone.now()
        # Create 5 existing Level 2 errors (at threshold)
        for i in range(5):
            _create_self_error(
                self.user, level=2, category='STRUCTURAL',
                trigger_code='BANNED_TERM_LEAKED',
                created_at=now - timedelta(days=i),
            )

        # 6th → auto-escalate to Level 3 → email + anomaly
        err = record_self_error(
            user=self.user,
            level=2,
            category='STRUCTURAL',
            trigger_code='BANNED_TERM_LEAKED',
            trigger_detail='Repeated structural violation',
            was_blocked=True,
        )

        # Verify Level 3
        self.assertEqual(err.level, SelfError.LEVEL_CRITICAL)
        self.assertEqual(err.metadata['auto_escalated_from'], 2)

        # Verify email sent
        mock_send_mail.assert_called_once()
        call_kwargs = mock_send_mail.call_args[1]
        self.assertIn('automatically escalated', call_kwargs['message'])

        # Verify OpsAnomaly
        anomaly = OpsAnomaly.objects.filter(
            anomaly_type='STRUCTURAL_VIOLATION',
            engine_name='VGE',
        ).first()
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly.severity, 'P1')
        self.assertTrue(anomaly.evidence.get('auto_escalated'))
