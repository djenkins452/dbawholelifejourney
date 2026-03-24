"""
Sports Domain — Time Normalization

Uniform relevance model for game timing signals.
All signals must respect these windows regardless of sport.

Windows:
- active_window: Game is currently live
- starting_soon_window: Game starts within 60 minutes
- today_window: Game is scheduled for today (user's local date)
- upcoming_window: Game is within next 48 hours
"""
from datetime import timedelta

from django.utils import timezone

# Window thresholds
STARTING_SOON_MINUTES = 60
UPCOMING_HOURS = 48


class GameTimeWindow:
    """Classify a game's temporal relevance for signal generation."""

    ACTIVE = "active"
    STARTING_SOON = "starting_soon"
    TODAY = "today"
    UPCOMING = "upcoming"
    PAST = "past"
    FUTURE = "future"

    def __init__(self, game_event, now=None):
        self.game = game_event
        self.now = now or timezone.now()

    @property
    def window(self):
        """Determine which time window this game falls into."""
        if self.game.status == "live":
            return self.ACTIVE

        if self.game.status == "final":
            return self.PAST

        if self.game.status in ("postponed", "cancelled"):
            return self.FUTURE  # Treat as non-relevant

        # Scheduled games — classify by time
        delta = self.game.start_time - self.now
        minutes_until = delta.total_seconds() / 60

        if minutes_until < 0:
            # Start time passed but not marked live/final yet
            return self.ACTIVE if minutes_until > -180 else self.PAST

        if minutes_until <= STARTING_SOON_MINUTES:
            return self.STARTING_SOON

        if self._is_today():
            return self.TODAY

        if delta <= timedelta(hours=UPCOMING_HOURS):
            return self.UPCOMING

        return self.FUTURE

    @property
    def is_relevant(self):
        """Whether this game is relevant for signal generation right now."""
        return self.window in (self.ACTIVE, self.STARTING_SOON, self.TODAY, self.UPCOMING, self.PAST)

    @property
    def is_actionable(self):
        """Whether this game warrants immediate attention signals."""
        return self.window in (self.ACTIVE, self.STARTING_SOON)

    def _is_today(self):
        """Check if game starts on the same calendar date as now (user timezone)."""
        return self.game.start_time.date() == self.now.date()
