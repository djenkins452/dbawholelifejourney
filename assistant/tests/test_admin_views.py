"""
Tests for the admin approval views and dashboard.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from assistant.models import APPROVAL_TOKEN_EXPIRY_HOURS, ImprovementTaskModel

User = get_user_model()


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


class TestImprovementDashboard(TestCase):
    """Tests for the improvement dashboard view."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        # Create a staff user
        self.staff_user = User.objects.create_user(
            email='staff@example.com',
            password='testpass123',
            is_staff=True,
        )
        # Create a non-staff user
        self.regular_user = User.objects.create_user(
            email='user@example.com',
            password='testpass123',
            is_staff=False,
        )
        # Create test tasks
        self.task1 = ImprovementTaskModel.objects.create(
            title="Test Task 1",
            description={"objective": "Test 1"},
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="test query 1",
            suggested_fix="Add keyword 1",
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL,
        )
        self.task2 = ImprovementTaskModel.objects.create(
            title="Test Task 2",
            description={"objective": "Test 2"},
            gap_type=ImprovementTaskModel.GAP_TYPE_WRONG_INTENT,
            severity=ImprovementTaskModel.SEVERITY_HIGH,
            original_query="test query 2",
            suggested_fix="Fix intent",
            status=ImprovementTaskModel.STATUS_COMPLETED,
        )

    def test_dashboard_requires_staff_login(self):
        """Test that dashboard requires staff login."""
        url = reverse('assistant:improvement_dashboard')
        response = self.client.get(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/', response.url)

    def test_dashboard_denies_non_staff(self):
        """Test that non-staff users are denied."""
        self.client.login(email='user@example.com', password='testpass123')
        url = reverse('assistant:improvement_dashboard')
        response = self.client.get(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)

    def test_dashboard_allows_staff(self):
        """Test that staff users can access dashboard."""
        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:improvement_dashboard')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Improvement Tasks Dashboard')

    def test_dashboard_displays_tasks(self):
        """Test that dashboard displays tasks."""
        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:improvement_dashboard')
        response = self.client.get(url)

        self.assertContains(response, 'Test Task 1')
        self.assertContains(response, 'Test Task 2')

    def test_dashboard_filter_by_status(self):
        """Test filtering tasks by status."""
        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:improvement_dashboard')
        response = self.client.get(f"{url}?status=pending_approval")

        self.assertContains(response, 'Test Task 1')
        self.assertNotContains(response, 'Test Task 2')

    def test_dashboard_filter_by_severity(self):
        """Test filtering tasks by severity."""
        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:improvement_dashboard')
        response = self.client.get(f"{url}?severity=high")

        self.assertNotContains(response, 'Test Task 1')
        self.assertContains(response, 'Test Task 2')

    def test_dashboard_shows_status_badges(self):
        """Test that status badges are displayed."""
        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:improvement_dashboard')
        response = self.client.get(url)

        # Check for badge classes
        self.assertContains(response, 'badge-yellow')  # pending_approval
        self.assertContains(response, 'badge-green')   # completed


class TestDashboardApproveTask(TestCase):
    """Tests for the dashboard approve task action."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.staff_user = User.objects.create_user(
            email='staff@example.com',
            password='testpass123',
            is_staff=True,
        )
        self.task = ImprovementTaskModel.objects.create(
            title="Test Task",
            description={"objective": "Test"},
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="test query",
            suggested_fix="Add keyword",
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL,
        )

    def test_approve_requires_staff(self):
        """Test that approve action requires staff login."""
        url = reverse('assistant:dashboard_approve_task', args=[self.task.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

    def test_approve_requires_post(self):
        """Test that approve action requires POST method."""
        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:dashboard_approve_task', args=[self.task.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)  # Method not allowed

    def test_approve_success(self):
        """Test successful task approval from dashboard."""
        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:dashboard_approve_task', args=[self.task.id])
        response = self.client.post(url)

        # Should redirect to dashboard
        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ImprovementTaskModel.STATUS_APPROVED)

    def test_approve_ajax_success(self):
        """Test successful AJAX approval."""
        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:dashboard_approve_task', args=[self.task.id])
        response = self.client.post(
            url,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('approved', data['message'].lower())

    def test_approve_wrong_status(self):
        """Test that approving non-pending task fails."""
        self.task.status = ImprovementTaskModel.STATUS_COMPLETED
        self.task.save()

        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:dashboard_approve_task', args=[self.task.id])
        response = self.client.post(
            url,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])


class TestDashboardRejectTask(TestCase):
    """Tests for the dashboard reject task action."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.staff_user = User.objects.create_user(
            email='staff@example.com',
            password='testpass123',
            is_staff=True,
        )
        self.task = ImprovementTaskModel.objects.create(
            title="Test Task",
            description={"objective": "Test"},
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="test query",
            suggested_fix="Add keyword",
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL,
        )

    def test_reject_success(self):
        """Test successful task rejection from dashboard."""
        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:dashboard_reject_task', args=[self.task.id])
        response = self.client.post(url, {'reason': 'Not needed'})

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ImprovementTaskModel.STATUS_REJECTED)
        self.assertEqual(self.task.rejection_reason, 'Not needed')

    def test_reject_ajax_success(self):
        """Test successful AJAX rejection."""
        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:dashboard_reject_task', args=[self.task.id])
        response = self.client.post(
            url,
            {'reason': 'Test rejection reason'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])


class TestDashboardRollbackTask(TestCase):
    """Tests for the dashboard rollback task action."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.staff_user = User.objects.create_user(
            email='staff@example.com',
            password='testpass123',
            is_staff=True,
        )
        self.task = ImprovementTaskModel.objects.create(
            title="Test Task",
            description={"objective": "Test"},
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="test query",
            suggested_fix="Add keyword",
            status=ImprovementTaskModel.STATUS_COMPLETED,
            git_commit_before='abc1234567890abcdef1234567890abcdef1234',
        )

    def test_rollback_requires_completed_status(self):
        """Test that rollback only works on completed tasks."""
        self.task.status = ImprovementTaskModel.STATUS_PENDING_APPROVAL
        self.task.save()

        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:dashboard_rollback_task', args=[self.task.id])
        response = self.client.post(
            url,
            {'reason': 'Test rollback'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('completed', data['error'].lower())

    def test_rollback_requires_git_commit_before(self):
        """Test that rollback requires git_commit_before to be set."""
        self.task.git_commit_before = ''
        self.task.save()

        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:dashboard_rollback_task', args=[self.task.id])
        response = self.client.post(
            url,
            {'reason': 'Test rollback'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('commit', data['error'].lower())

    def test_rollback_requires_reason(self):
        """Test that rollback requires a reason."""
        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:dashboard_rollback_task', args=[self.task.id])
        response = self.client.post(
            url,
            {},  # No reason
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('reason', data['error'].lower())

    @patch('assistant.admin_views.AdminNotificationService')
    @patch('assistant.admin_views.GitProtectionService')
    def test_rollback_success(self, mock_git_service, mock_notification_service):
        """Test successful task rollback."""
        # Mock git rollback success
        mock_git_instance = mock_git_service.return_value
        mock_git_instance.rollback_to_commit.return_value.success = True

        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:dashboard_rollback_task', args=[self.task.id])
        response = self.client.post(url, {'reason': 'Found a bug'})

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ImprovementTaskModel.STATUS_ROLLED_BACK)
        self.assertEqual(self.task.rollback_reason, 'Found a bug')
        self.assertIsNotNone(self.task.rolled_back_at)

    @patch('assistant.admin_views.AdminNotificationService')
    @patch('assistant.admin_views.GitProtectionService')
    def test_rollback_ajax_success(self, mock_git_service, mock_notification_service):
        """Test successful AJAX rollback."""
        # Mock git rollback success
        mock_git_instance = mock_git_service.return_value
        mock_git_instance.rollback_to_commit.return_value.success = True

        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:dashboard_rollback_task', args=[self.task.id])
        response = self.client.post(
            url,
            {'reason': 'Found a bug'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('rollback_commit', data)
        self.assertEqual(data['rollback_commit'], 'abc12345')

    @patch('assistant.admin_views.AdminNotificationService')
    @patch('assistant.admin_views.GitProtectionService')
    def test_rollback_calls_git_service(self, mock_git_service, mock_notification_service):
        """Test rollback triggers git rollback with correct commit hash."""
        # Mock git rollback success
        mock_git_instance = mock_git_service.return_value
        mock_git_instance.rollback_to_commit.return_value.success = True

        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:dashboard_rollback_task', args=[self.task.id])
        self.client.post(url, {'reason': 'Test rollback'})

        mock_git_instance.rollback_to_commit.assert_called_once_with(
            'abc1234567890abcdef1234567890abcdef1234'
        )

    @patch('assistant.admin_views.AdminNotificationService')
    @patch('assistant.admin_views.GitProtectionService')
    def test_rollback_notifies_admin(self, mock_git_service, mock_notification_service):
        """Test rollback sends notification to admin."""
        # Mock git rollback success
        mock_git_instance = mock_git_service.return_value
        mock_git_instance.rollback_to_commit.return_value.success = True

        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:dashboard_rollback_task', args=[self.task.id])
        self.client.post(url, {'reason': 'Test rollback'})

        mock_notification_service.return_value.notify_task_error.assert_called_once()

    @patch('assistant.admin_views.GitProtectionService')
    def test_rollback_git_failure(self, mock_git_service):
        """Test rollback handles git failure gracefully."""
        # Mock git rollback failure
        mock_git_instance = mock_git_service.return_value
        mock_git_instance.rollback_to_commit.return_value.success = False
        mock_git_instance.rollback_to_commit.return_value.message = 'Git error'

        self.client.login(email='staff@example.com', password='testpass123')
        url = reverse('assistant:dashboard_rollback_task', args=[self.task.id])
        response = self.client.post(
            url,
            {'reason': 'Test rollback'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Git', data['error'])

        # Task status should not change on failure
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ImprovementTaskModel.STATUS_COMPLETED)


class TestRollbackMethod(TestCase):
    """Tests for the rollback model method."""

    def setUp(self):
        """Set up test fixtures."""
        self.task = ImprovementTaskModel.objects.create(
            title="Test Task",
            description={"objective": "Test"},
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="test query",
            suggested_fix="Add keyword",
            status=ImprovementTaskModel.STATUS_COMPLETED,
        )

    def test_rollback_method_success(self):
        """Test rollback method updates status and fields."""
        self.task.rollback(reason='Bug found')

        self.assertEqual(self.task.status, ImprovementTaskModel.STATUS_ROLLED_BACK)
        self.assertEqual(self.task.rollback_reason, 'Bug found')
        self.assertIsNotNone(self.task.rolled_back_at)

    def test_rollback_from_wrong_status_raises_error(self):
        """Test that rollback from non-completed status raises error."""
        self.task.status = ImprovementTaskModel.STATUS_PENDING_APPROVAL
        self.task.save()

        from assistant.models import TaskStatusTransitionError
        with self.assertRaises(TaskStatusTransitionError):
            self.task.rollback(reason='Test')

    def test_rollback_persists_to_database(self):
        """Test that rollback changes are saved to database."""
        self.task.rollback(reason='Bug found')

        # Fetch fresh from database
        fresh_task = ImprovementTaskModel.objects.get(id=self.task.id)
        self.assertEqual(fresh_task.status, ImprovementTaskModel.STATUS_ROLLED_BACK)
        self.assertEqual(fresh_task.rollback_reason, 'Bug found')
        self.assertIsNotNone(fresh_task.rolled_back_at)
