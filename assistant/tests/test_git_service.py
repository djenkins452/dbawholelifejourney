"""
Tests for the Git Protection Service.
"""

import subprocess
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

from assistant.git_service import GitProtectionService, GitResult


class TestGitProtectionService(TestCase):
    """Tests for GitProtectionService."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = GitProtectionService('/test/repo')

    @patch.object(GitProtectionService, '_run_git_command')
    def test_has_uncommitted_changes_true(self, mock_run):
        """Test detecting uncommitted changes."""
        mock_run.return_value = MagicMock(
            stdout=' M modified_file.py\n',
            returncode=0
        )

        result = self.service.has_uncommitted_changes()

        self.assertTrue(result)
        mock_run.assert_called_once_with('status', '--porcelain')

    @patch.object(GitProtectionService, '_run_git_command')
    def test_has_uncommitted_changes_false(self, mock_run):
        """Test clean working directory."""
        mock_run.return_value = MagicMock(
            stdout='',
            returncode=0
        )

        result = self.service.has_uncommitted_changes()

        self.assertFalse(result)

    @patch.object(GitProtectionService, '_run_git_command')
    def test_get_current_commit_hash_success(self, mock_run):
        """Test getting current commit hash."""
        mock_run.return_value = MagicMock(
            stdout='abc123def456\n',
            returncode=0
        )

        result = self.service.get_current_commit_hash()

        self.assertEqual(result, 'abc123def456')
        mock_run.assert_called_once_with('rev-parse', 'HEAD')

    @patch.object(GitProtectionService, '_run_git_command')
    def test_get_current_commit_hash_not_git_repo(self, mock_run):
        """Test getting hash when not in a Git repo."""
        mock_run.return_value = MagicMock(
            stdout='',
            returncode=128
        )

        result = self.service.get_current_commit_hash()

        self.assertIsNone(result)

    @patch.object(GitProtectionService, 'get_current_commit_hash')
    @patch.object(GitProtectionService, 'has_uncommitted_changes')
    def test_create_snapshot_success(self, mock_has_changes, mock_get_hash):
        """Test creating a snapshot with clean working directory."""
        mock_has_changes.return_value = False
        mock_get_hash.return_value = 'abc123def456'

        result = self.service.create_snapshot(task_id=42)

        self.assertTrue(result.success)
        self.assertIn('abc123de', result.message)
        self.assertEqual(result.commit_hash, 'abc123def456')

    @patch.object(GitProtectionService, 'has_uncommitted_changes')
    def test_create_snapshot_uncommitted_changes(self, mock_has_changes):
        """Test snapshot fails with uncommitted changes."""
        mock_has_changes.return_value = True

        result = self.service.create_snapshot(task_id=42)

        self.assertFalse(result.success)
        self.assertIn('uncommitted changes', result.message)

    @patch.object(GitProtectionService, 'get_current_commit_hash')
    @patch.object(GitProtectionService, '_run_git_command')
    def test_commit_changes_success(self, mock_run, mock_get_hash):
        """Test successful commit."""
        # Set up mock responses
        mock_run.side_effect = [
            MagicMock(returncode=0),  # git add -A
            MagicMock(returncode=1),  # git diff --cached --quiet (changes exist)
            MagicMock(returncode=0, stdout='Committed', stderr=''),  # git commit
        ]
        mock_get_hash.return_value = 'new123hash'

        result = self.service.commit_changes(
            task_id=42,
            task_title='Add feature X'
        )

        self.assertTrue(result.success)
        self.assertEqual(result.commit_hash, 'new123hash')

    @patch.object(GitProtectionService, '_run_git_command')
    def test_commit_changes_no_changes(self, mock_run):
        """Test commit when there are no changes."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # git add -A
            MagicMock(returncode=0),  # git diff --cached --quiet (no changes)
        ]

        result = self.service.commit_changes(
            task_id=42,
            task_title='Add feature X'
        )

        self.assertFalse(result.success)
        self.assertIn('No changes', result.message)

    @patch.object(GitProtectionService, 'get_current_commit_hash')
    @patch.object(GitProtectionService, '_run_git_command')
    def test_commit_changes_specific_files(self, mock_run, mock_get_hash):
        """Test committing specific files."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # git add file1
            MagicMock(returncode=0),  # git add file2
            MagicMock(returncode=1),  # git diff --cached --quiet
            MagicMock(returncode=0, stdout='Committed', stderr=''),  # git commit
        ]
        mock_get_hash.return_value = 'new123hash'

        result = self.service.commit_changes(
            task_id=42,
            task_title='Add feature X',
            files=['file1.py', 'file2.py']
        )

        self.assertTrue(result.success)
        # Verify specific files were added
        add_calls = [call for call in mock_run.call_args_list if call[0][0] == 'add']
        self.assertEqual(len(add_calls), 2)

    @patch.object(GitProtectionService, '_run_git_command')
    def test_commit_changes_stage_failure(self, mock_run):
        """Test commit when staging fails."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr='fatal: pathspec error'
        )

        result = self.service.commit_changes(
            task_id=42,
            task_title='Add feature X',
            files=['nonexistent.py']
        )

        self.assertFalse(result.success)
        self.assertIn('Failed to stage', result.message)

    @patch.object(GitProtectionService, '_run_git_command')
    def test_rollback_to_commit_success(self, mock_run):
        """Test successful rollback."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='HEAD is now at abc123',
            stderr=''
        )

        result = self.service.rollback_to_commit('abc123def456')

        self.assertTrue(result.success)
        self.assertIn('abc123de', result.message)
        mock_run.assert_called_once_with('reset', '--hard', 'abc123def456')

    @patch.object(GitProtectionService, '_run_git_command')
    def test_rollback_to_commit_failure(self, mock_run):
        """Test rollback failure."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr='fatal: invalid commit'
        )

        result = self.service.rollback_to_commit('invalid')

        self.assertFalse(result.success)
        self.assertIn('Failed to rollback', result.message)

    def test_rollback_to_commit_no_hash(self):
        """Test rollback with no hash provided."""
        result = self.service.rollback_to_commit('')

        self.assertFalse(result.success)
        self.assertIn('No commit hash', result.message)

    @patch.object(GitProtectionService, '_run_git_command')
    def test_get_file_diff_all_files(self, mock_run):
        """Test getting diff for all files."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='diff --git a/file.py\n+added line'
        )

        result = self.service.get_file_diff()

        self.assertIn('added line', result)
        mock_run.assert_called_once_with('diff')

    @patch.object(GitProtectionService, '_run_git_command')
    def test_get_file_diff_specific_file(self, mock_run):
        """Test getting diff for specific file."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='diff --git a/test.py\n+new code'
        )

        result = self.service.get_file_diff(file_path='test.py')

        self.assertIn('new code', result)
        mock_run.assert_called_once_with('diff', '--', 'test.py')

    @patch.object(GitProtectionService, '_run_git_command')
    def test_get_file_diff_staged(self, mock_run):
        """Test getting staged diff."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='diff --git staged changes'
        )

        result = self.service.get_file_diff(staged=True)

        mock_run.assert_called_once_with('diff', '--cached')

    @patch.object(GitProtectionService, '_run_git_command')
    def test_get_file_diff_no_changes(self, mock_run):
        """Test diff when there are no changes."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=''
        )

        result = self.service.get_file_diff()

        self.assertIsNone(result)

    @patch.object(GitProtectionService, '_run_git_command')
    def test_get_commit_diff_success(self, mock_run):
        """Test getting diff for a specific commit."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='commit abc123\n2 files changed'
        )

        result = self.service.get_commit_diff('abc123')

        self.assertIn('2 files changed', result)
        mock_run.assert_called_once_with('show', '--stat', 'abc123')

    @patch.object(GitProtectionService, '_run_git_command')
    def test_get_commit_diff_invalid_commit(self, mock_run):
        """Test getting diff for invalid commit."""
        mock_run.return_value = MagicMock(
            returncode=128,
            stdout=''
        )

        result = self.service.get_commit_diff('invalid')

        self.assertIsNone(result)


class TestGitResult(TestCase):
    """Tests for GitResult dataclass."""

    def test_git_result_defaults(self):
        """Test GitResult default values."""
        result = GitResult(success=True, message='Test')

        self.assertTrue(result.success)
        self.assertEqual(result.message, 'Test')
        self.assertIsNone(result.commit_hash)
        self.assertIsNone(result.output)

    def test_git_result_all_fields(self):
        """Test GitResult with all fields."""
        result = GitResult(
            success=True,
            message='Committed',
            commit_hash='abc123',
            output='1 file changed'
        )

        self.assertTrue(result.success)
        self.assertEqual(result.commit_hash, 'abc123')
        self.assertEqual(result.output, '1 file changed')
