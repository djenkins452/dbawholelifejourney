"""
Git Protection Service for safe code modifications.

Provides Git snapshot and rollback capabilities for the Personal Assistant
improvement workflow.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class GitResult:
    """Result of a Git operation."""
    success: bool
    message: str
    commit_hash: Optional[str] = None
    output: Optional[str] = None


class GitProtectionService:
    """
    Service for creating Git commits before and after changes,
    enabling rollback if improvements fail.
    """

    def __init__(self, repo_path: Optional[str] = None):
        """
        Initialize the Git protection service.

        Args:
            repo_path: Path to the Git repository. Defaults to current directory.
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()

    def _run_git_command(self, *args: str) -> subprocess.CompletedProcess:
        """
        Run a Git command in the repository.

        Args:
            *args: Git command arguments.

        Returns:
            CompletedProcess with stdout, stderr, and returncode.
        """
        return subprocess.run(
            ['git', *args],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )

    def has_uncommitted_changes(self) -> bool:
        """
        Check if the working directory has uncommitted changes.

        Returns:
            True if there are uncommitted changes, False otherwise.
        """
        result = self._run_git_command('status', '--porcelain')
        return bool(result.stdout.strip())

    def get_current_commit_hash(self) -> Optional[str]:
        """
        Get the current HEAD commit hash.

        Returns:
            The current commit hash, or None if not in a Git repository.
        """
        result = self._run_git_command('rev-parse', 'HEAD')
        if result.returncode == 0:
            return result.stdout.strip()
        return None

    def create_snapshot(self, task_id: int) -> GitResult:
        """
        Create a snapshot commit before making changes.

        Stages all changes and commits with a standardized message.

        Args:
            task_id: The improvement task ID for the commit message.

        Returns:
            GitResult with success status and commit hash.
        """
        # Safety check: refuse if there are uncommitted changes
        if self.has_uncommitted_changes():
            return GitResult(
                success=False,
                message="Working directory has uncommitted changes. "
                        "Please commit or stash changes before creating a snapshot."
            )

        # Get current commit hash as reference
        current_hash = self.get_current_commit_hash()

        return GitResult(
            success=True,
            message=f"Snapshot reference captured at {current_hash[:8] if current_hash else 'unknown'}",
            commit_hash=current_hash
        )

    def commit_changes(self, task_id: int, task_title: str, files: Optional[list[str]] = None) -> GitResult:
        """
        Commit changes after a successful improvement.

        Args:
            task_id: The improvement task ID.
            task_title: The title of the improvement task.
            files: Optional list of specific files to commit. If None, commits all changes.

        Returns:
            GitResult with success status and new commit hash.
        """
        # Stage files
        if files:
            for file in files:
                result = self._run_git_command('add', file)
                if result.returncode != 0:
                    return GitResult(
                        success=False,
                        message=f"Failed to stage file {file}: {result.stderr}"
                    )
        else:
            result = self._run_git_command('add', '-A')
            if result.returncode != 0:
                return GitResult(
                    success=False,
                    message=f"Failed to stage changes: {result.stderr}"
                )

        # Check if there are staged changes
        status_result = self._run_git_command('diff', '--cached', '--quiet')
        if status_result.returncode == 0:
            return GitResult(
                success=False,
                message="No changes to commit"
            )

        # Create commit
        commit_message = f"AUTO-IMPROVE {task_title} (Task {task_id})"
        result = self._run_git_command('commit', '-m', commit_message)

        if result.returncode != 0:
            return GitResult(
                success=False,
                message=f"Failed to commit: {result.stderr}"
            )

        # Get new commit hash
        new_hash = self.get_current_commit_hash()

        return GitResult(
            success=True,
            message="Changes committed successfully",
            commit_hash=new_hash,
            output=result.stdout
        )

    def rollback_to_commit(self, commit_hash: str) -> GitResult:
        """
        Rollback to a specific commit.

        Uses git reset --hard to revert all changes.

        Args:
            commit_hash: The commit hash to rollback to.

        Returns:
            GitResult with success status.
        """
        if not commit_hash:
            return GitResult(
                success=False,
                message="No commit hash provided for rollback"
            )

        result = self._run_git_command('reset', '--hard', commit_hash)

        if result.returncode != 0:
            return GitResult(
                success=False,
                message=f"Failed to rollback: {result.stderr}"
            )

        return GitResult(
            success=True,
            message=f"Successfully rolled back to {commit_hash[:8]}",
            commit_hash=commit_hash,
            output=result.stdout
        )

    def get_file_diff(self, file_path: Optional[str] = None, staged: bool = False) -> Optional[str]:
        """
        Get the diff for a file or all files.

        Args:
            file_path: Optional specific file to get diff for.
            staged: If True, show staged changes. If False, show unstaged changes.

        Returns:
            The diff output, or None if no changes.
        """
        args = ['diff']
        if staged:
            args.append('--cached')
        if file_path:
            args.extend(['--', file_path])

        result = self._run_git_command(*args)

        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
        return None

    def get_commit_diff(self, commit_hash: str) -> Optional[str]:
        """
        Get the diff for a specific commit.

        Args:
            commit_hash: The commit to show diff for.

        Returns:
            The diff output, or None if error.
        """
        result = self._run_git_command('show', '--stat', commit_hash)

        if result.returncode == 0:
            return result.stdout
        return None
