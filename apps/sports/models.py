"""
Sports Domain — Models

Raw data models for the Sports context domain.
GameEvent is the SINGLE SOURCE OF TRUTH for all sports data.
Signals and state are derived downstream — never duplicated here.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Sport(models.Model):
    """Top-level sport classification (Football, Basketball, Baseball)."""
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class League(models.Model):
    """A league within a sport (NFL, NBA, NCAAF, etc.)."""
    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="leagues")
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=50, unique=True)
    abbreviation = models.CharField(max_length=20)
    is_college = models.BooleanField(default=False)

    class Meta:
        ordering = ["sport__name", "name"]

    def __str__(self):
        return self.abbreviation


class Team(models.Model):
    """A team within a league."""
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name="teams")
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=100)
    abbreviation = models.CharField(max_length=10)
    external_id = models.CharField(max_length=100, blank=True, default="")
    logo_url = models.URLField(blank=True, default="")

    # Season record — updated by background sync
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    record_season = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        ordering = ["location", "name"]
        unique_together = [("league", "abbreviation")]

    def __str__(self):
        return f"{self.location} {self.name}"

    @property
    def full_name(self):
        return f"{self.location} {self.name}"

    @property
    def record(self):
        """Season record as string (e.g. '18-7'). Empty if no data."""
        if self.wins == 0 and self.losses == 0:
            return ""
        return f"{self.wins}-{self.losses}"

    @property
    def is_record_stale(self):
        """True if record is from a previous season, not the current one."""
        if not self.record_season:
            return False  # Unknown season — don't label
        from datetime import datetime
        current_year = str(datetime.now().year)
        # Handle "2023-2024" format (NBA) and "2024" format (others)
        return current_year not in self.record_season

    @property
    def record_display(self):
        """Record with season label if stale (e.g. '98-64 (2024)')."""
        if not self.record:
            return ""
        if self.is_record_stale and self.record_season:
            # Extract display year: "2024" or "2023-2024" → "2024"
            season_label = self.record_season.split("-")[-1] if "-" in self.record_season else self.record_season
            return f"{self.record} ({season_label})"
        return self.record


class GameEvent(models.Model):
    """
    A single game/match event — the ONLY raw truth source for sports data.

    All signals, state, and context are derived from this model.
    Never query this on the request path — use cached/state data instead.
    """
    STATUS_SCHEDULED = "scheduled"
    STATUS_LIVE = "live"
    STATUS_FINAL = "final"
    STATUS_POSTPONED = "postponed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_LIVE, "Live"),
        (STATUS_FINAL, "Final"),
        (STATUS_POSTPONED, "Postponed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    home_team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="home_games"
    )
    away_team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="away_games"
    )
    start_time = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED
    )
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    venue = models.CharField(max_length=200, blank=True, default="")
    external_id = models.CharField(max_length=100, blank=True, default="")

    # Baseball-only: probable starting pitchers (null for other sports)
    home_probable_pitcher = models.CharField(max_length=100, blank=True, default="")
    away_probable_pitcher = models.CharField(max_length=100, blank=True, default="")

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_time"]
        indexes = [
            models.Index(fields=["start_time", "status"]),
            models.Index(fields=["home_team", "start_time"]),
            models.Index(fields=["away_team", "start_time"]),
        ]

    def __str__(self):
        return f"{self.away_team} @ {self.home_team} ({self.start_time:%Y-%m-%d})"

    @property
    def is_live(self):
        return self.status == self.STATUS_LIVE

    @property
    def is_final(self):
        return self.status == self.STATUS_FINAL

    def get_winner(self):
        """Return winning team or None if not final/tied."""
        if not self.is_final or self.home_score is None or self.away_score is None:
            return None
        if self.home_score > self.away_score:
            return self.home_team
        elif self.away_score > self.home_score:
            return self.away_team
        return None  # Tie

    def user_team_won(self, team):
        """Check if the given team won this game."""
        winner = self.get_winner()
        return winner is not None and winner.id == team.id

    def user_team_lost(self, team):
        """Check if the given team lost this game."""
        winner = self.get_winner()
        if winner is None:
            return False
        return winner.id != team.id

    def get_opponent(self, team):
        """Return the opponent of the given team in this game."""
        if self.home_team_id == team.id:
            return self.away_team
        elif self.away_team_id == team.id:
            return self.home_team
        return None

    def get_score_display(self):
        """Return formatted score string."""
        if self.home_score is not None and self.away_score is not None:
            return f"{self.away_score}-{self.home_score}"
        return ""


class UserTeamFollow(models.Model):
    """
    User's followed teams with priority levels.

    Priority levels:
    1 = Primary (favorite team — strongest signal weight)
    2 = Secondary (follow closely)
    3 = Casual (light awareness)
    """
    PRIORITY_PRIMARY = 1
    PRIORITY_SECONDARY = 2
    PRIORITY_CASUAL = 3

    PRIORITY_CHOICES = [
        (PRIORITY_PRIMARY, "Primary"),
        (PRIORITY_SECONDARY, "Secondary"),
        (PRIORITY_CASUAL, "Casual"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="followed_teams",
    )
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="followers")
    priority = models.IntegerField(choices=PRIORITY_CHOICES, default=PRIORITY_SECONDARY)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "team")]
        ordering = ["priority", "team__location"]

    def __str__(self):
        return f"{self.user} follows {self.team} (P{self.priority})"
