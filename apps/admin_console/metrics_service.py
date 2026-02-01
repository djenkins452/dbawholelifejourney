# ==============================================================================
# File: apps/admin_console/metrics_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Service module for gathering project metrics and statistics
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-05
# Last Updated: 2026-01-05 (Added GitHub API support for production)
# ==============================================================================
"""
Project Metrics Service

Provides comprehensive metrics about the codebase, git history, and project statistics.
Used by the Project Metrics Report view in the admin console.

Supports two modes:
1. Local git commands (development) - when .git directory is available
2. GitHub API (production) - when deployed without git history
"""

import logging
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytz
import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache timeout for GitHub API data (1 hour)
GITHUB_CACHE_TIMEOUT = 3600


@dataclass
class FileMetrics:
    """Metrics about files in the codebase."""
    python_files: int = 0
    python_lines: int = 0
    html_files: int = 0
    html_lines: int = 0
    javascript_files: int = 0
    css_files: int = 0
    markdown_files: int = 0
    test_files: int = 0
    migration_files: int = 0
    total_size_mb: float = 0.0


@dataclass
class CodeMetrics:
    """Metrics about code structure."""
    django_models: int = 0
    view_functions: int = 0
    url_routes: int = 0
    python_classes: int = 0
    python_functions: int = 0
    test_methods: int = 0
    dependencies: int = 0
    unique_imports: int = 0
    todo_comments: int = 0
    django_apps: int = 0
    app_names: list = field(default_factory=list)


@dataclass
class GitMetrics:
    """Metrics about git history."""
    total_commits: int = 0
    total_insertions: int = 0
    total_deletions: int = 0
    net_lines_added: int = 0
    unique_days_with_commits: int = 0
    first_commit_date: Optional[str] = None
    last_commit_date: Optional[str] = None
    project_age_days: int = 0
    avg_commits_per_day: float = 0.0

    # Today's stats
    commits_today: int = 0
    lines_added_today: int = 0
    lines_deleted_today: int = 0
    first_commit_today: Optional[str] = None
    last_commit_today: Optional[str] = None
    coding_hours_today: float = 0.0

    # Commit breakdown
    feature_commits: int = 0
    bugfix_commits: int = 0
    refactor_commits: int = 0
    ai_assisted_commits: int = 0

    # Most productive days
    most_productive_days: list = field(default_factory=list)

    # Commits by day of week
    commits_by_day: dict = field(default_factory=dict)

    # Peak coding hours
    peak_hours: list = field(default_factory=list)

    # Data source indicator
    data_source: str = "local"  # "local" or "github"


@dataclass
class ProjectMetrics:
    """Complete project metrics."""
    file_metrics: FileMetrics = field(default_factory=FileMetrics)
    code_metrics: CodeMetrics = field(default_factory=CodeMetrics)
    git_metrics: GitMetrics = field(default_factory=GitMetrics)
    generated_at: Optional[datetime] = None


class GitHubMetricsService:
    """Service for fetching git metrics from GitHub API."""

    def __init__(self, owner: str, repo: str, token: Optional[str] = None, user_timezone: Optional[str] = None):
        """
        Initialize the GitHub metrics service.

        Args:
            owner: GitHub repository owner (username or org)
            repo: Repository name
            token: Optional GitHub personal access token for higher rate limits
            user_timezone: User's timezone string (e.g., 'America/New_York')
        """
        self.owner = owner
        self.repo = repo
        self.token = token
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "WLJ-Metrics-Service"
        }
        if token:
            self.headers["Authorization"] = f"token {token}"

        # Set up timezone for date conversions
        if user_timezone:
            try:
                self.tz = pytz.timezone(user_timezone)
            except pytz.UnknownTimeZoneError:
                self.tz = pytz.UTC
        else:
            self.tz = pytz.UTC

    def _make_request(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make a request to the GitHub API."""
        url = f"{self.base_url}/{endpoint}" if endpoint else self.base_url
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.warning(f"GitHub API request failed: {e}")
            return None

    def _get_all_commits(self, since: Optional[datetime] = None, per_page: int = 100) -> list:
        """Fetch all commits, handling pagination."""
        cache_key = f"github_commits_{self.owner}_{self.repo}"
        if since:
            cache_key += f"_{since.isoformat()}"

        cached = cache.get(cache_key)
        if cached:
            return cached

        commits = []
        page = 1
        params = {"per_page": per_page}
        if since:
            params["since"] = since.isoformat()

        while True:
            params["page"] = page
            data = self._make_request("commits", params)
            if not data:
                break
            commits.extend(data)
            if len(data) < per_page:
                break
            page += 1
            # Safety limit to avoid too many API calls
            if page > 50:
                break

        cache.set(cache_key, commits, GITHUB_CACHE_TIMEOUT)
        return commits

    def get_git_metrics(self) -> GitMetrics:
        """Fetch git metrics from GitHub API."""
        metrics = GitMetrics(data_source="github")

        # Get repository info
        repo_info = self._make_request("")
        if repo_info:
            metrics.total_size_mb = repo_info.get("size", 0) / 1024  # KB to MB

        # Get all commits
        commits = self._get_all_commits()
        metrics.total_commits = len(commits)

        if not commits:
            return metrics

        # Parse commit dates and convert to user's timezone
        commit_dates = []
        commit_messages = []
        for commit in commits:
            commit_data = commit.get("commit", {})
            author_data = commit_data.get("author", {})
            date_str = author_data.get("date", "")
            message = commit_data.get("message", "")

            if date_str:
                try:
                    # Parse UTC time from GitHub API
                    dt_utc = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    # Convert to user's timezone
                    dt_local = dt_utc.astimezone(self.tz)
                    commit_dates.append(dt_local)
                except ValueError:
                    pass

            commit_messages.append(message.lower())

        if commit_dates:
            # Sort dates
            commit_dates.sort()

            # First and last commit
            metrics.first_commit_date = commit_dates[0].strftime("%Y-%m-%d")
            metrics.last_commit_date = commit_dates[-1].strftime("%Y-%m-%d")

            # Project age
            age_delta = commit_dates[-1] - commit_dates[0]
            metrics.project_age_days = age_delta.days + 1
            if metrics.project_age_days > 0:
                metrics.avg_commits_per_day = round(
                    metrics.total_commits / metrics.project_age_days, 1
                )

            # Unique days with commits
            unique_days = set(dt.strftime("%Y-%m-%d") for dt in commit_dates)
            metrics.unique_days_with_commits = len(unique_days)

            # Today's commits (in user's timezone)
            now_local = datetime.now(self.tz)
            today = now_local.date()
            today_commits = [dt for dt in commit_dates if dt.date() == today]
            metrics.commits_today = len(today_commits)

            if today_commits:
                metrics.first_commit_today = today_commits[0].strftime("%Y-%m-%d %H:%M:%S")
                metrics.last_commit_today = today_commits[-1].strftime("%Y-%m-%d %H:%M:%S")
                # Calculate coding hours
                if len(today_commits) > 1:
                    diff = (today_commits[-1] - today_commits[0]).total_seconds() / 3600
                    metrics.coding_hours_today = round(diff, 1)

            # Most productive days
            day_counts = Counter(dt.strftime("%Y-%m-%d") for dt in commit_dates)
            for date, count in day_counts.most_common(5):
                metrics.most_productive_days.append({
                    "date": date,
                    "commits": count
                })

            # Commits by day of week
            weekday_counts = Counter(dt.strftime("%A") for dt in commit_dates)
            # Sort by count descending
            for day, count in weekday_counts.most_common():
                metrics.commits_by_day[day] = count

            # Peak coding hours
            hour_counts = Counter(dt.hour for dt in commit_dates)
            for hour, count in hour_counts.most_common(5):
                if hour < 12:
                    hour_str = f"{hour} AM" if hour > 0 else "12 AM"
                elif hour == 12:
                    hour_str = "12 PM"
                else:
                    hour_str = f"{hour - 12} PM"
                metrics.peak_hours.append({
                    "hour": hour_str,
                    "commits": count
                })

        # Analyze commit messages for types
        for msg in commit_messages:
            if any(kw in msg for kw in ["add", "feature", "implement", "new"]):
                metrics.feature_commits += 1
            if any(kw in msg for kw in ["fix", "bug", "patch", "resolve"]):
                metrics.bugfix_commits += 1
            if any(kw in msg for kw in ["refactor", "clean", "improve", "optimize"]):
                metrics.refactor_commits += 1
            if any(kw in msg for kw in ["claude", "ai", "generated", "co-authored-by: claude"]):
                metrics.ai_assisted_commits += 1

        # Get contributor stats for insertions/deletions (requires additional API call)
        stats = self._make_request("stats/contributors")
        if stats:
            total_additions = 0
            total_deletions = 0
            for contributor in stats:
                for week in contributor.get("weeks", []):
                    total_additions += week.get("a", 0)
                    total_deletions += week.get("d", 0)
            metrics.total_insertions = total_additions
            metrics.total_deletions = total_deletions
            metrics.net_lines_added = total_additions - total_deletions

        return metrics


class MetricsService:
    """Service for gathering project metrics."""

    def __init__(self, project_root: Optional[str] = None, user_timezone: Optional[str] = None):
        """
        Initialize the metrics service.

        Args:
            project_root: Path to the project root. If None, uses current directory.
            user_timezone: User's timezone string (e.g., 'America/New_York')
        """
        if project_root:
            self.project_root = Path(project_root)
        else:
            # Try to find project root by looking for manage.py
            self.project_root = self._find_project_root()

        # Check if we have local git access
        self.has_local_git = self._check_local_git()

        # Store user timezone for git metrics
        self.user_timezone = user_timezone

    def _find_project_root(self) -> Path:
        """Find the project root by looking for manage.py."""
        return Path(settings.BASE_DIR)

    def _check_local_git(self) -> bool:
        """Check if local git repository is available."""
        git_dir = self.project_root / ".git"
        return git_dir.exists()

    def _run_command(self, command: str, cwd: Optional[Path] = None) -> str:
        """
        Run a shell command and return output.

        Args:
            command: The command to run
            cwd: Working directory (defaults to project root)

        Returns:
            Command output as string, or empty string on error
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=cwd or self.project_root,
                timeout=30
            )
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return ""

    def _count_files(self, pattern: str, exclude_dirs: list = None) -> int:
        """Count files matching a pattern, excluding certain directories."""
        exclude_dirs = exclude_dirs or ['.venv', 'venv', 'node_modules', '__pycache__']
        exclude_args = ' '.join(f'-not -path "*/{d}/*"' for d in exclude_dirs)
        cmd = f'find . -name "{pattern}" {exclude_args} 2>/dev/null | wc -l'
        result = self._run_command(cmd)
        try:
            return int(result)
        except ValueError:
            return 0

    def _count_lines_in_files(self, pattern: str, exclude_dirs: list = None) -> int:
        """Count total lines in files matching a pattern."""
        exclude_dirs = exclude_dirs or ['.venv', 'venv', 'node_modules', '__pycache__']
        exclude_args = ' '.join(f'-not -path "*/{d}/*"' for d in exclude_dirs)
        cmd = f'find . -name "{pattern}" {exclude_args} -exec cat {{}} \\; 2>/dev/null | wc -l'
        result = self._run_command(cmd)
        try:
            return int(result)
        except ValueError:
            return 0

    def _grep_count(self, pattern: str, file_pattern: str = "*.py") -> int:
        """Count occurrences of a pattern in files."""
        cmd = f'grep -r "{pattern}" --include="{file_pattern}" -h 2>/dev/null | wc -l'
        result = self._run_command(cmd)
        try:
            return int(result)
        except ValueError:
            return 0

    def get_file_metrics(self) -> FileMetrics:
        """Gather file-related metrics."""
        metrics = FileMetrics()

        # Python files
        metrics.python_files = self._count_files("*.py")
        metrics.python_lines = self._count_lines_in_files("*.py")

        # HTML files
        metrics.html_files = self._count_files("*.html")
        metrics.html_lines = self._count_lines_in_files("*.html")

        # JavaScript and CSS
        metrics.javascript_files = self._count_files("*.js")
        metrics.css_files = self._count_files("*.css")

        # Markdown
        metrics.markdown_files = self._count_files("*.md")

        # Test files
        metrics.test_files = self._count_files("*test*.py")

        # Migrations (excluding __init__.py)
        cmd = 'find . -path "*/migrations/*.py" -not -name "__init__.py" -not -path "*/.venv/*" 2>/dev/null | wc -l'
        result = self._run_command(cmd)
        try:
            metrics.migration_files = int(result)
        except ValueError:
            metrics.migration_files = 0

        # Total project size
        result = self._run_command('du -sm . 2>/dev/null | cut -f1')
        try:
            metrics.total_size_mb = float(result)
        except ValueError:
            metrics.total_size_mb = 0.0

        return metrics

    def get_code_metrics(self) -> CodeMetrics:
        """Gather code structure metrics."""
        metrics = CodeMetrics()

        # Django models
        metrics.django_models = self._grep_count("class.*models.Model")

        # View functions (in views.py files)
        cmd = 'find . -name "views.py" -not -path "*/.venv/*" -exec grep -c "def " {} + 2>/dev/null | awk -F: \'{sum+=$2} END {print sum}\''
        result = self._run_command(cmd)
        try:
            metrics.view_functions = int(result) if result else 0
        except ValueError:
            metrics.view_functions = 0

        # URL routes
        metrics.url_routes = self._grep_count('path\\(', "urls.py")

        # Python classes and functions
        metrics.python_classes = self._grep_count("class ")
        metrics.python_functions = self._grep_count("def ")

        # Test methods
        metrics.test_methods = self._grep_count("def test_")

        # Dependencies from requirements.txt
        req_file = self.project_root / "requirements.txt"
        if req_file.exists():
            try:
                with open(req_file) as f:
                    lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                    metrics.dependencies = len(lines)
            except IOError:
                metrics.dependencies = 0

        # Unique imports
        cmd = 'find . -name "*.py" -not -path "*/.venv/*" -exec grep -h "^import\\|^from" {} \\; 2>/dev/null | sort -u | wc -l'
        result = self._run_command(cmd)
        try:
            metrics.unique_imports = int(result)
        except ValueError:
            metrics.unique_imports = 0

        # TODO comments
        metrics.todo_comments = self._grep_count("TODO\\|FIXME\\|XXX\\|HACK")

        # Django apps
        apps_dir = self.project_root / "apps"
        if apps_dir.exists():
            app_dirs = [d for d in apps_dir.iterdir() if d.is_dir() and not d.name.startswith('_')]
            metrics.django_apps = len(app_dirs)
            metrics.app_names = sorted([d.name for d in app_dirs if d.name != '__pycache__'])

        return metrics

    def get_git_metrics_local(self) -> GitMetrics:
        """Gather git history metrics from local git repository."""
        metrics = GitMetrics(data_source="local")

        # Total commits
        result = self._run_command('git log --oneline 2>/dev/null | wc -l')
        try:
            metrics.total_commits = int(result)
        except ValueError:
            metrics.total_commits = 0

        # Insertions and deletions
        result = self._run_command(
            'git log --numstat --pretty="" 2>/dev/null | '
            'awk \'{ins+=$1; del+=$2} END {print ins, del}\''
        )
        try:
            parts = result.split()
            if len(parts) >= 2:
                metrics.total_insertions = int(parts[0])
                metrics.total_deletions = int(parts[1])
                metrics.net_lines_added = metrics.total_insertions - metrics.total_deletions
        except (ValueError, IndexError):
            pass

        # Unique days with commits
        result = self._run_command('git log --format="%ad" --date=short 2>/dev/null | sort -u | wc -l')
        try:
            metrics.unique_days_with_commits = int(result)
        except ValueError:
            metrics.unique_days_with_commits = 0

        # First and last commit dates
        result = self._run_command('git log --format="%ai" 2>/dev/null | tail -1')
        if result:
            metrics.first_commit_date = result.split()[0] if result else None

        result = self._run_command('git log --format="%ai" 2>/dev/null | head -1')
        if result:
            metrics.last_commit_date = result.split()[0] if result else None

        # Calculate project age
        if metrics.first_commit_date and metrics.last_commit_date:
            try:
                first = datetime.strptime(metrics.first_commit_date, "%Y-%m-%d")
                last = datetime.strptime(metrics.last_commit_date, "%Y-%m-%d")
                metrics.project_age_days = (last - first).days + 1
                if metrics.project_age_days > 0:
                    metrics.avg_commits_per_day = metrics.total_commits / metrics.project_age_days
            except ValueError:
                pass

        # Today's stats
        result = self._run_command('git log --oneline --since="midnight" 2>/dev/null | wc -l')
        try:
            metrics.commits_today = int(result)
        except ValueError:
            metrics.commits_today = 0

        # Lines changed today
        result = self._run_command(
            'git log --format="" --numstat --since="midnight" 2>/dev/null | '
            'awk \'{ins+=$1; del+=$2} END {print ins, del}\''
        )
        try:
            parts = result.split()
            if len(parts) >= 2:
                metrics.lines_added_today = int(parts[0])
                metrics.lines_deleted_today = int(parts[1])
        except (ValueError, IndexError):
            pass

        # First and last commit today
        result = self._run_command('git log --format="%ai" --since="midnight" 2>/dev/null | tail -1')
        if result:
            metrics.first_commit_today = ' '.join(result.split()[:2]) if result else None

        result = self._run_command('git log --format="%ai" --since="midnight" 2>/dev/null | head -1')
        if result:
            metrics.last_commit_today = ' '.join(result.split()[:2]) if result else None

        # Calculate coding hours today
        if metrics.first_commit_today and metrics.last_commit_today:
            try:
                first_time = metrics.first_commit_today.split()[1] if ' ' in metrics.first_commit_today else None
                last_time = metrics.last_commit_today.split()[1] if ' ' in metrics.last_commit_today else None
                if first_time and last_time:
                    first_dt = datetime.strptime(first_time, "%H:%M:%S")
                    last_dt = datetime.strptime(last_time, "%H:%M:%S")
                    diff = (last_dt - first_dt).total_seconds() / 3600
                    metrics.coding_hours_today = round(abs(diff), 1)
            except ValueError:
                pass

        # Commit breakdown by type
        result = self._run_command('git log --pretty=format:"%s" 2>/dev/null | grep -i "add\\|feature\\|implement" | wc -l')
        try:
            metrics.feature_commits = int(result)
        except ValueError:
            metrics.feature_commits = 0

        result = self._run_command('git log --pretty=format:"%s" 2>/dev/null | grep -i "fix\\|bug" | wc -l')
        try:
            metrics.bugfix_commits = int(result)
        except ValueError:
            metrics.bugfix_commits = 0

        result = self._run_command('git log --pretty=format:"%s" 2>/dev/null | grep -i "refactor\\|clean\\|improve" | wc -l')
        try:
            metrics.refactor_commits = int(result)
        except ValueError:
            metrics.refactor_commits = 0

        result = self._run_command('git log --oneline 2>/dev/null | grep -i "Claude\\|AI\\|Generated" | wc -l')
        try:
            metrics.ai_assisted_commits = int(result)
        except ValueError:
            metrics.ai_assisted_commits = 0

        # Most productive days
        result = self._run_command('git log --format="%ad" --date=short 2>/dev/null | uniq -c | sort -rn | head -5')
        if result:
            for line in result.strip().split('\n'):
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        metrics.most_productive_days.append({
                            'date': parts[1],
                            'commits': int(parts[0])
                        })
                    except (ValueError, IndexError):
                        pass

        # Commits by day of week
        result = self._run_command('git log --format="%ad" --date=format:"%A" 2>/dev/null | sort | uniq -c | sort -rn')
        if result:
            for line in result.strip().split('\n'):
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        metrics.commits_by_day[parts[1]] = int(parts[0])
                    except (ValueError, IndexError):
                        pass

        # Peak coding hours
        result = self._run_command('git log --format="%ad" --date=format:"%H" 2>/dev/null | sort | uniq -c | sort -rn | head -5')
        if result:
            for line in result.strip().split('\n'):
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        hour = int(parts[1])
                        hour_str = f"{hour}:00"
                        if hour < 12:
                            hour_str = f"{hour} AM" if hour > 0 else "12 AM"
                        elif hour == 12:
                            hour_str = "12 PM"
                        else:
                            hour_str = f"{hour - 12} PM"
                        metrics.peak_hours.append({
                            'hour': hour_str,
                            'commits': int(parts[0])
                        })
                    except (ValueError, IndexError):
                        pass

        return metrics

    def get_git_metrics(self) -> GitMetrics:
        """
        Get git metrics from the best available source.

        Uses local git if available, otherwise falls back to GitHub API.
        """
        if self.has_local_git:
            return self.get_git_metrics_local()

        # Fall back to GitHub API
        github_owner = getattr(settings, 'GITHUB_REPO_OWNER', 'djenkins452')
        github_repo = getattr(settings, 'GITHUB_REPO_NAME', 'dbawholelifejourney')
        github_token = getattr(settings, 'GITHUB_API_TOKEN', None)

        github_service = GitHubMetricsService(
            owner=github_owner,
            repo=github_repo,
            token=github_token,
            user_timezone=self.user_timezone
        )
        return github_service.get_git_metrics()

    def get_all_metrics(self) -> ProjectMetrics:
        """Gather all project metrics."""
        return ProjectMetrics(
            file_metrics=self.get_file_metrics(),
            code_metrics=self.get_code_metrics(),
            git_metrics=self.get_git_metrics(),
            generated_at=datetime.now()
        )


def get_project_metrics(user_timezone: Optional[str] = None) -> ProjectMetrics:
    """
    Convenience function to get all project metrics.

    Args:
        user_timezone: User's timezone string (e.g., 'America/New_York')

    Returns:
        ProjectMetrics instance with all gathered data
    """
    service = MetricsService(user_timezone=user_timezone)
    return service.get_all_metrics()
