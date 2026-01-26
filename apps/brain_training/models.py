"""
Brain Training Models

Core data models for the Brain Training module:
- Game: Catalog of available brain training games
- Challenge: Individual puzzle instances with encrypted solutions
- GameSession: User attempt at a challenge (tracks performance)
- DailyStats: Aggregated daily statistics per user per game
- WeeklyStats: Aggregated weekly statistics for trending
"""

import hashlib
import json
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Game(TimeStampedModel):
    """
    Catalog of available brain training games.

    Each game has a unique slug, display info, and configuration.
    """

    CATEGORY_LOGIC = 'logic'
    CATEGORY_MATH = 'math'
    CATEGORY_VISUAL = 'visual'
    CATEGORY_LANGUAGE = 'language'
    CATEGORY_MEMORY = 'memory'

    CATEGORY_CHOICES = [
        (CATEGORY_LOGIC, 'Logic'),
        (CATEGORY_MATH, 'Math Logic'),
        (CATEGORY_VISUAL, 'Visual Logic'),
        (CATEGORY_LANGUAGE, 'Language'),
        (CATEGORY_MEMORY, 'Memory'),
    ]

    slug = models.SlugField(
        max_length=50,
        unique=True,
        help_text="Unique identifier (sudoku, kenken, nonogram, word_ladder, memory_matrix)",
    )
    name = models.CharField(
        max_length=100,
        help_text="Display name",
    )
    description = models.TextField(
        blank=True,
        help_text="Brief description of the game",
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        help_text="Primary cognitive skill category",
    )

    # Display configuration
    icon_svg = models.TextField(
        blank=True,
        help_text="SVG icon for the game tile",
    )
    color_primary = models.CharField(
        max_length=7,
        default="#6366f1",
        help_text="Primary theme color (hex)",
    )
    color_secondary = models.CharField(
        max_length=7,
        default="#818cf8",
        help_text="Secondary theme color (hex)",
    )

    # Game configuration
    difficulty_levels = models.JSONField(
        default=list,
        help_text="Available difficulty levels ['easy', 'medium', 'hard', 'expert']",
    )
    default_difficulty = models.CharField(
        max_length=20,
        default='medium',
        help_text="Default difficulty for new players",
    )

    # Feature flags
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this game is available to users",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order in the hub (lower = first)",
    )

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = "Brain Training Game"
        verbose_name_plural = "Brain Training Games"

    def __str__(self):
        return self.name


class Challenge(TimeStampedModel):
    """
    Individual puzzle/challenge instance.

    Contains the puzzle data and encrypted solution. Solutions are hashed
    to prevent client-side inspection while allowing server verification.
    """

    DIFFICULTY_EASY = 'easy'
    DIFFICULTY_MEDIUM = 'medium'
    DIFFICULTY_HARD = 'hard'
    DIFFICULTY_EXPERT = 'expert'

    DIFFICULTY_CHOICES = [
        (DIFFICULTY_EASY, 'Easy'),
        (DIFFICULTY_MEDIUM, 'Medium'),
        (DIFFICULTY_HARD, 'Hard'),
        (DIFFICULTY_EXPERT, 'Expert'),
    ]

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name='challenges',
    )

    # Challenge identification
    challenge_id = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Unique hash identifier for this challenge",
    )

    # Difficulty
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default=DIFFICULTY_MEDIUM,
        db_index=True,
    )

    # Puzzle data (JSON format varies by game type)
    puzzle_data = models.JSONField(
        help_text="Puzzle configuration (grid, clues, etc.) - safe to send to client",
    )

    # Solution - stored hashed, never sent to client
    # The actual solution is stored in solution_data for server-side verification
    solution_hash = models.CharField(
        max_length=64,
        help_text="SHA-256 hash of the solution for integrity checks",
    )
    solution_data = models.JSONField(
        help_text="Actual solution data for server-side verification",
    )

    # Metrics for this specific puzzle
    average_time_seconds = models.PositiveIntegerField(
        default=0,
        help_text="Average completion time across all users",
    )
    completion_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of successful completions",
    )
    attempt_count = models.PositiveIntegerField(
        default=0,
        help_text="Total number of attempts",
    )

    # Pre-generation flag
    is_pregenerated = models.BooleanField(
        default=False,
        help_text="Whether this was pre-generated (vs on-demand)",
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['game', 'difficulty']),
            models.Index(fields=['game', 'difficulty', 'created_at']),
        ]
        verbose_name = "Challenge"
        verbose_name_plural = "Challenges"

    def __str__(self):
        return f"{self.game.name} - {self.get_difficulty_display()} ({self.challenge_id[:8]})"

    @staticmethod
    def generate_challenge_id(game_slug: str, puzzle_data: dict) -> str:
        """Generate a unique challenge ID from game and puzzle data."""
        data_str = f"{game_slug}:{json.dumps(puzzle_data, sort_keys=True)}"
        return hashlib.sha256(data_str.encode()).hexdigest()

    @staticmethod
    def hash_solution(solution_data: dict) -> str:
        """Hash solution data for storage."""
        data_str = json.dumps(solution_data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()

    def verify_solution(self, submitted_solution: dict) -> bool:
        """
        Verify a submitted solution against the stored solution.

        Uses constant-time comparison to prevent timing attacks.
        """
        import hmac
        submitted_hash = self.hash_solution(submitted_solution)
        return hmac.compare_digest(submitted_hash, self.solution_hash)

    def update_metrics(self, time_seconds: int, completed: bool):
        """Update aggregate metrics after a session completes."""
        self.attempt_count += 1
        if completed:
            self.completion_count += 1
            # Update running average
            if self.average_time_seconds == 0:
                self.average_time_seconds = time_seconds
            else:
                # Weighted moving average
                total_time = self.average_time_seconds * (self.completion_count - 1) + time_seconds
                self.average_time_seconds = total_time // self.completion_count
        self.save(update_fields=['attempt_count', 'completion_count', 'average_time_seconds', 'updated_at'])


class GameSession(TimeStampedModel):
    """
    User's attempt at a challenge.

    Tracks timing, mistakes, hints, and completion status.
    This is the core engagement/analytics model.
    """

    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_ABANDONED = 'abandoned'
    STATUS_TIMEOUT = 'timeout'

    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_ABANDONED, 'Abandoned'),
        (STATUS_TIMEOUT, 'Timed Out'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='brain_training_sessions',
    )
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name='sessions',
    )

    # Session timing
    started_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the user started this challenge",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user completed (or abandoned) the challenge",
    )
    time_spent_seconds = models.PositiveIntegerField(
        default=0,
        help_text="Total active time spent on this challenge",
    )

    # Performance tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_IN_PROGRESS,
        db_index=True,
    )
    mistakes = models.PositiveIntegerField(
        default=0,
        help_text="Number of incorrect inputs",
    )
    hints_used = models.PositiveIntegerField(
        default=0,
        help_text="Number of hints requested",
    )

    # Score calculation (0-100 base score, can be higher with bonuses)
    score = models.PositiveIntegerField(
        default=0,
        help_text="Calculated score based on time, mistakes, hints",
    )

    # Progress state (for resuming)
    current_state = models.JSONField(
        default=dict,
        blank=True,
        help_text="Current puzzle state for resuming",
    )

    # Device/platform info
    platform = models.CharField(
        max_length=20,
        blank=True,
        help_text="ios, android, web",
    )

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'challenge', '-started_at']),
            models.Index(fields=['user', 'started_at']),
        ]
        verbose_name = "Game Session"
        verbose_name_plural = "Game Sessions"

    def __str__(self):
        return f"{self.user.email} - {self.challenge.game.name} ({self.status})"

    @property
    def game(self):
        """Convenience accessor for the game."""
        return self.challenge.game

    @property
    def difficulty(self):
        """Convenience accessor for difficulty."""
        return self.challenge.difficulty

    def complete(self, time_spent: int, mistakes: int = 0, hints_used: int = 0):
        """
        Mark session as completed and calculate score.
        """
        self.status = self.STATUS_COMPLETED
        self.completed_at = timezone.now()
        self.time_spent_seconds = time_spent
        self.mistakes = mistakes
        self.hints_used = hints_used
        self.score = self._calculate_score()
        self.save()

        # Update challenge metrics
        self.challenge.update_metrics(time_spent, completed=True)

    def abandon(self, time_spent: int = 0):
        """Mark session as abandoned."""
        self.status = self.STATUS_ABANDONED
        self.completed_at = timezone.now()
        if time_spent:
            self.time_spent_seconds = time_spent
        self.save()

        # Update challenge attempt count
        self.challenge.update_metrics(0, completed=False)

    def _calculate_score(self) -> int:
        """
        Calculate score based on difficulty, time, mistakes, and hints.

        Base score: 100 points
        Time bonus: +20 points if under average time
        Mistake penalty: -5 per mistake (max -30)
        Hint penalty: -10 per hint (max -30)
        Difficulty multiplier: easy=1.0, medium=1.2, hard=1.5, expert=2.0
        """
        base_score = 100

        # Time bonus (up to +20)
        avg_time = self.challenge.average_time_seconds or 120  # Default 2 min
        if self.time_spent_seconds < avg_time:
            time_ratio = self.time_spent_seconds / avg_time
            base_score += int(20 * (1 - time_ratio))

        # Mistake penalty (-5 each, max -30)
        base_score -= min(self.mistakes * 5, 30)

        # Hint penalty (-10 each, max -30)
        base_score -= min(self.hints_used * 10, 30)

        # Difficulty multiplier
        multipliers = {
            'easy': 1.0,
            'medium': 1.2,
            'hard': 1.5,
            'expert': 2.0,
        }
        multiplier = multipliers.get(self.challenge.difficulty, 1.0)

        return max(0, int(base_score * multiplier))


class DailyStats(TimeStampedModel):
    """
    Aggregated daily statistics per user per game.

    Updated after each session completion. Used for progress tracking
    and improvement calculations.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='brain_training_daily_stats',
    )
    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name='daily_stats',
    )
    date = models.DateField(
        db_index=True,
        help_text="The date these stats are for",
    )

    # Session counts
    sessions_started = models.PositiveIntegerField(default=0)
    sessions_completed = models.PositiveIntegerField(default=0)

    # Time tracking
    total_time_seconds = models.PositiveIntegerField(default=0)
    best_time_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Best (lowest) completion time of the day",
    )

    # Performance
    total_score = models.PositiveIntegerField(default=0)
    best_score = models.PositiveIntegerField(default=0)
    total_mistakes = models.PositiveIntegerField(default=0)
    total_hints = models.PositiveIntegerField(default=0)

    # Difficulty breakdown
    easy_completed = models.PositiveIntegerField(default=0)
    medium_completed = models.PositiveIntegerField(default=0)
    hard_completed = models.PositiveIntegerField(default=0)
    expert_completed = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-date']
        unique_together = ['user', 'game', 'date']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['user', 'game', 'date']),
        ]
        verbose_name = "Daily Stats"
        verbose_name_plural = "Daily Stats"

    def __str__(self):
        return f"{self.user.email} - {self.game.name} - {self.date}"

    @property
    def average_time_seconds(self):
        """Average completion time for the day."""
        if self.sessions_completed == 0:
            return 0
        return self.total_time_seconds // self.sessions_completed

    @property
    def average_score(self):
        """Average score for the day."""
        if self.sessions_completed == 0:
            return 0
        return self.total_score // self.sessions_completed

    @property
    def average_mistakes(self):
        """Average mistakes per session."""
        if self.sessions_completed == 0:
            return 0
        return round(self.total_mistakes / self.sessions_completed, 1)

    @classmethod
    def get_or_create_for_session(cls, session: GameSession):
        """Get or create daily stats record for a session's date."""
        session_date = session.started_at.date()
        stats, created = cls.objects.get_or_create(
            user=session.user,
            game=session.challenge.game,
            date=session_date,
        )
        return stats

    def record_session(self, session: GameSession):
        """Record a completed session's stats."""
        if session.status != GameSession.STATUS_COMPLETED:
            return

        self.sessions_completed += 1
        self.total_time_seconds += session.time_spent_seconds
        self.total_score += session.score
        self.total_mistakes += session.mistakes
        self.total_hints += session.hints_used

        # Update best time
        if self.best_time_seconds is None or session.time_spent_seconds < self.best_time_seconds:
            self.best_time_seconds = session.time_spent_seconds

        # Update best score
        if session.score > self.best_score:
            self.best_score = session.score

        # Update difficulty counts
        difficulty = session.challenge.difficulty
        if difficulty == Challenge.DIFFICULTY_EASY:
            self.easy_completed += 1
        elif difficulty == Challenge.DIFFICULTY_MEDIUM:
            self.medium_completed += 1
        elif difficulty == Challenge.DIFFICULTY_HARD:
            self.hard_completed += 1
        elif difficulty == Challenge.DIFFICULTY_EXPERT:
            self.expert_completed += 1

        self.save()


class UserGameStats(TimeStampedModel):
    """
    Lifetime statistics per user per game.

    Provides quick access to totals without aggregating daily stats.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='brain_training_game_stats',
    )
    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name='user_stats',
    )

    # Totals
    total_sessions = models.PositiveIntegerField(default=0)
    total_completed = models.PositiveIntegerField(default=0)
    total_time_seconds = models.PositiveIntegerField(default=0)
    total_score = models.PositiveIntegerField(default=0)

    # Bests
    best_score = models.PositiveIntegerField(default=0)
    best_time_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    # Streaks
    current_streak = models.PositiveIntegerField(
        default=0,
        help_text="Current consecutive days played",
    )
    longest_streak = models.PositiveIntegerField(
        default=0,
        help_text="Longest consecutive days played",
    )
    last_played_date = models.DateField(
        null=True,
        blank=True,
        help_text="Last date this game was played",
    )

    # Preferred difficulty (most played)
    preferred_difficulty = models.CharField(
        max_length=20,
        default='medium',
        help_text="User's most-played difficulty level",
    )

    class Meta:
        unique_together = ['user', 'game']
        verbose_name = "User Game Stats"
        verbose_name_plural = "User Game Stats"

    def __str__(self):
        return f"{self.user.email} - {self.game.name} Stats"

    @property
    def average_score(self):
        if self.total_completed == 0:
            return 0
        return self.total_score // self.total_completed

    @property
    def average_time_seconds(self):
        if self.total_completed == 0:
            return 0
        return self.total_time_seconds // self.total_completed

    @property
    def completion_rate(self):
        """Percentage of started sessions that were completed."""
        if self.total_sessions == 0:
            return 0
        return round((self.total_completed / self.total_sessions) * 100, 1)

    def update_streak(self, played_date):
        """Update streak based on play date."""
        if self.last_played_date is None:
            self.current_streak = 1
        elif played_date == self.last_played_date:
            # Same day, no change
            pass
        elif (played_date - self.last_played_date).days == 1:
            # Consecutive day
            self.current_streak += 1
        else:
            # Streak broken
            self.current_streak = 1

        # Update longest streak
        if self.current_streak > self.longest_streak:
            self.longest_streak = self.current_streak

        self.last_played_date = played_date
        self.save(update_fields=['current_streak', 'longest_streak', 'last_played_date', 'updated_at'])


class UserOverallStats(TimeStampedModel):
    """
    Overall brain training statistics for a user across all games.

    Single record per user. Updated after each session.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='brain_training_overall_stats',
    )

    # Totals
    total_sessions = models.PositiveIntegerField(default=0)
    total_completed = models.PositiveIntegerField(default=0)
    total_time_seconds = models.PositiveIntegerField(default=0)

    # Streaks (any game)
    current_streak = models.PositiveIntegerField(
        default=0,
        help_text="Current consecutive days with any brain training",
    )
    longest_streak = models.PositiveIntegerField(
        default=0,
        help_text="Longest consecutive days with any brain training",
    )
    last_played_date = models.DateField(
        null=True,
        blank=True,
    )

    # Favorite game (most completed)
    favorite_game = models.ForeignKey(
        Game,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        help_text="Most-played game",
    )

    class Meta:
        verbose_name = "User Overall Stats"
        verbose_name_plural = "User Overall Stats"

    def __str__(self):
        return f"{self.user.email} - Brain Training Overall Stats"

    @property
    def total_minutes_trained(self):
        return self.total_time_seconds // 60

    def update_streak(self, played_date):
        """Update streak based on play date."""
        if self.last_played_date is None:
            self.current_streak = 1
        elif played_date == self.last_played_date:
            pass
        elif (played_date - self.last_played_date).days == 1:
            self.current_streak += 1
        else:
            self.current_streak = 1

        if self.current_streak > self.longest_streak:
            self.longest_streak = self.current_streak

        self.last_played_date = played_date
        self.save(update_fields=['current_streak', 'longest_streak', 'last_played_date', 'updated_at'])


class ChallengeQueue(models.Model):
    """
    Pre-fetched challenge queue for instant loading.

    Maintains a queue of challenges per user per game for instant serve.
    Refilled in background when queue drops below threshold.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='brain_training_queue',
    )
    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name='queues',
    )
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name='queue_entries',
    )

    # Queue position and status
    position = models.PositiveIntegerField(
        default=0,
        help_text="Position in queue (0 = next up)",
    )
    added_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ['user', 'game', 'position']
        indexes = [
            models.Index(fields=['user', 'game', 'position']),
        ]
        verbose_name = "Challenge Queue"
        verbose_name_plural = "Challenge Queues"

    def __str__(self):
        return f"{self.user.email} - {self.game.name} Queue #{self.position}"

    @classmethod
    def get_next(cls, user, game):
        """Get and remove the next challenge from the queue."""
        entry = cls.objects.filter(
            user=user,
            game=game,
        ).order_by('position').first()

        if entry:
            challenge = entry.challenge
            entry.delete()
            # Reorder remaining entries
            cls.objects.filter(
                user=user,
                game=game,
            ).update(position=models.F('position') - 1)
            return challenge
        return None

    @classmethod
    def queue_size(cls, user, game):
        """Get current queue size for a user/game combo."""
        return cls.objects.filter(user=user, game=game).count()

    @classmethod
    def add_to_queue(cls, user, game, challenges):
        """Add challenges to the end of the queue."""
        current_max = cls.objects.filter(
            user=user, game=game
        ).aggregate(max_pos=models.Max('position'))['max_pos'] or -1

        entries = []
        for i, challenge in enumerate(challenges):
            entries.append(cls(
                user=user,
                game=game,
                challenge=challenge,
                position=current_max + 1 + i,
            ))
        cls.objects.bulk_create(entries)
