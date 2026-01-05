"""
Tests for the admin approval views.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from assistant.models import APPROVAL_TOKEN_EXPIRY_HOURS, ImprovementTaskModel


class TestApproveTaskView(TestCase):
    """Tests for the approve_task view."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.task = ImprovementTaskModel.objects.create(
            title="Test Task",
            description={"objective": "Test"},
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="test query",
            suggested_fix="Add keyword",
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL,
        )
        self.token = self.task.generate_approval_token()

    def test_approve_task_success(self):
        """Test successful task approval."""
        url = reverse('assistant:approve_task', args=[self.task.id, self.token])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Task Approved')

        # Verify task was approved
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ImprovementTaskModel.STATUS_APPROVED)
        self.assertIsNotNone(self.task.approved_at)

    def test_approve_task_clears_token(self):
        """Test that approval clears the token (one-time use)."""
        url = reverse('assistant:approve_task', args=[self.task.id, self.token])
        self.client.get(url)

        self.task.refresh_from_db()
        self.assertEqual(self.task.approval_token, '')
        self.assertIsNone(self.task.approval_token_created_at)

    def test_approve_task_invalid_token(self):
        """Test that invalid token returns error."""
        url = reverse('assistant:approve_task', args=[self.task.id, 'invalid_token'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Invalid or expired', status_code=400)

        # Verify task was not approved
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ImprovementTaskModel.STATUS_PENDING_APPROVAL)

    def test_approve_task_expired_token(self):
        """Test that expired token returns error."""
        # Set token creation time to past expiry
        self.task.approval_token_created_at = timezone.now() - timedelta(hours=APPROVAL_TOKEN_EXPIRY_HOURS + 1)
        self.task.save()

        url = reverse('assistant:approve_task', args=[self.task.id, self.token])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'expired', status_code=400)

    def test_approve_task_wrong_status(self):
        """Test that approving non-pending task returns error."""
        self.task.status = ImprovementTaskModel.STATUS_APPROVED
        self.task.save()

        url = reverse('assistant:approve_task', args=[self.task.id, self.token])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'not pending approval', status_code=400)

    def test_approve_task_not_found(self):
        """Test that non-existent task returns 404."""
        import uuid
        fake_id = uuid.uuid4()
        url = reverse('assistant:approve_task', args=[fake_id, self.token])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_approve_task_already_used_token(self):
        """Test that reusing a token after approval fails."""
        url = reverse('assistant:approve_task', args=[self.task.id, self.token])

        # First approval
        response1 = self.client.get(url)
        self.assertEqual(response1.status_code, 200)

        # Second attempt with same token
        response2 = self.client.get(url)
        self.assertEqual(response2.status_code, 400)


class TestRejectTaskView(TestCase):
    """Tests for the reject_task view."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.task = ImprovementTaskModel.objects.create(
            title="Test Task",
            description={"objective": "Test"},
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="test query",
            suggested_fix="Add keyword",
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL,
        )
        self.token = self.task.generate_approval_token()

    def test_reject_task_success(self):
        """Test successful task rejection."""
        url = reverse('assistant:reject_task', args=[self.task.id, self.token])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Task Rejected')

        # Verify task was rejected
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ImprovementTaskModel.STATUS_REJECTED)
        self.assertIsNotNone(self.task.rejected_at)

    def test_reject_task_with_reason(self):
        """Test rejection with reason parameter."""
        reason = "Not needed at this time"
        url = reverse('assistant:reject_task', args=[self.task.id, self.token])
        response = self.client.get(f"{url}?reason={reason}")

        self.assertEqual(response.status_code, 200)

        self.task.refresh_from_db()
        self.assertEqual(self.task.rejection_reason, reason)

    def test_reject_task_clears_token(self):
        """Test that rejection clears the token (one-time use)."""
        url = reverse('assistant:reject_task', args=[self.task.id, self.token])
        self.client.get(url)

        self.task.refresh_from_db()
        self.assertEqual(self.task.approval_token, '')

    def test_reject_task_invalid_token(self):
        """Test that invalid token returns error."""
        url = reverse('assistant:reject_task', args=[self.task.id, 'invalid_token'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 400)

        # Verify task was not rejected
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ImprovementTaskModel.STATUS_PENDING_APPROVAL)

    def test_reject_task_wrong_status(self):
        """Test that rejecting non-pending task returns error."""
        self.task.status = ImprovementTaskModel.STATUS_COMPLETED
        self.task.save()

        url = reverse('assistant:reject_task', args=[self.task.id, self.token])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 400)


class TestTokenValidation(TestCase):
    """Tests for token generation and validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.task = ImprovementTaskModel.objects.create(
            title="Test Task",
            description={"objective": "Test"},
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="test query",
            suggested_fix="Add keyword",
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL,
        )

    def test_generate_token(self):
        """Test token generation."""
        token = self.task.generate_approval_token()

        self.assertIsNotNone(token)
        self.assertTrue(len(token) > 20)  # Should be reasonably long
        self.assertEqual(self.task.approval_token, token)
        self.assertIsNotNone(self.task.approval_token_created_at)

    def test_token_is_unique(self):
        """Test that tokens are unique."""
        token1 = self.task.generate_approval_token()
        token2 = self.task.generate_approval_token()

        self.assertNotEqual(token1, token2)

    def test_is_token_valid_correct_token(self):
        """Test token validation with correct token."""
        token = self.task.generate_approval_token()

        self.assertTrue(self.task.is_token_valid(token))

    def test_is_token_valid_wrong_token(self):
        """Test token validation with wrong token."""
        self.task.generate_approval_token()

        self.assertFalse(self.task.is_token_valid('wrong_token'))

    def test_is_token_valid_no_token_set(self):
        """Test token validation when no token is set."""
        self.assertFalse(self.task.is_token_valid('any_token'))

    def test_is_token_valid_expired(self):
        """Test token validation with expired token."""
        token = self.task.generate_approval_token()
        self.task.approval_token_created_at = timezone.now() - timedelta(hours=25)
        self.task.save()

        self.assertFalse(self.task.is_token_valid(token))

    def test_clear_approval_token(self):
        """Test clearing approval token."""
        self.task.generate_approval_token()
        self.task.clear_approval_token()

        self.assertEqual(self.task.approval_token, '')
        self.assertIsNone(self.task.approval_token_created_at)


class TestApprovalMethods(TestCase):
    """Tests for approve and reject helper methods."""

    def setUp(self):
        """Set up test fixtures."""
        self.task = ImprovementTaskModel.objects.create(
            title="Test Task",
            description={"objective": "Test"},
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="test query",
            suggested_fix="Add keyword",
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL,
        )
        self.task.generate_approval_token()

    def test_approve_method(self):
        """Test approve method."""
        self.task.approve()

        self.assertEqual(self.task.status, ImprovementTaskModel.STATUS_APPROVED)
        self.assertIsNotNone(self.task.approved_at)
        self.assertEqual(self.task.approval_token, '')

    def test_reject_method(self):
        """Test reject method."""
        reason = "Test rejection"
        self.task.reject(reason=reason)

        self.assertEqual(self.task.status, ImprovementTaskModel.STATUS_REJECTED)
        self.assertIsNotNone(self.task.rejected_at)
        self.assertEqual(self.task.rejection_reason, reason)
        self.assertEqual(self.task.approval_token, '')

    def test_reject_method_default_reason(self):
        """Test reject method with default reason."""
        self.task.reject()

        self.assertEqual(self.task.status, ImprovementTaskModel.STATUS_REJECTED)
        self.assertEqual(self.task.rejection_reason, '')
