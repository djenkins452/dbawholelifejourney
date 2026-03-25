"""
Sports Domain — Provider Adapter Layer

Abstract interface for sports data providers.
All external data flows through adapter → normalization → DB.
External APIs NEVER shape internal models.

Includes FixtureSportsProvider for development/testing.
"""
import logging
from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


class NormalizedTeam:
    """Normalized team data from any provider."""
    __slots__ = ("external_id", "name", "location", "abbreviation", "league_slug", "logo_url")

    def __init__(self, external_id, name, location, abbreviation, league_slug, logo_url=""):
        self.external_id = external_id
        self.name = name
        self.location = location
        self.abbreviation = abbreviation
        self.league_slug = league_slug
        self.logo_url = logo_url


class NormalizedGame:
    """Normalized game data from any provider."""
    __slots__ = (
        "external_id", "home_team_external_id", "away_team_external_id",
        "start_time", "status", "home_score", "away_score", "venue",
        "home_probable_pitcher", "away_probable_pitcher",
    )

    def __init__(
        self, external_id, home_team_external_id, away_team_external_id,
        start_time, status="scheduled", home_score=None, away_score=None, venue="",
        home_probable_pitcher="", away_probable_pitcher="",
    ):
        self.external_id = external_id
        self.home_team_external_id = home_team_external_id
        self.away_team_external_id = away_team_external_id
        self.start_time = start_time
        self.status = status
        self.home_score = home_score
        self.away_score = away_score
        self.venue = venue
        self.home_probable_pitcher = home_probable_pitcher
        self.away_probable_pitcher = away_probable_pitcher


class NormalizedStanding:
    """Normalized standings entry from any provider."""
    __slots__ = ("team_external_id", "wins", "losses", "ties", "win_pct", "rank")

    def __init__(self, team_external_id, wins, losses, ties=0, win_pct=0.0, rank=None):
        self.team_external_id = team_external_id
        self.wins = wins
        self.losses = losses
        self.ties = ties
        self.win_pct = win_pct
        self.rank = rank


class BaseSportsProvider(ABC):
    """Abstract interface for sports data providers."""

    @abstractmethod
    def fetch_teams(self, league_slug: str) -> list[NormalizedTeam]:
        """Fetch all teams for a given league."""

    @abstractmethod
    def fetch_games(
        self, team_external_ids: list[str], date_from: date, date_to: date
    ) -> list[NormalizedGame]:
        """Fetch games for specified teams within a date range."""

    @abstractmethod
    def fetch_standings(self, league_slug: str) -> list[NormalizedStanding]:
        """Fetch current standings for a league."""

    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider identifier."""


class FixtureSportsProvider(BaseSportsProvider):
    """
    Development/test provider that returns fixture data.

    No external API calls — data is generated programmatically.
    Used for Phase 1-3 development before real API integration.
    """

    def provider_name(self) -> str:
        return "fixture"

    def fetch_teams(self, league_slug: str) -> list[NormalizedTeam]:
        """Return fixture teams for the given league."""
        teams = _FIXTURE_TEAMS.get(league_slug, [])
        return [
            NormalizedTeam(
                external_id=f"fixture_{league_slug}_{t['abbr']}",
                name=t["name"],
                location=t["location"],
                abbreviation=t["abbr"],
                league_slug=league_slug,
            )
            for t in teams
        ]

    def fetch_games(
        self, team_external_ids: list[str], date_from: date, date_to: date
    ) -> list[NormalizedGame]:
        """Fixture provider returns no games — use management command to seed."""
        return []

    def fetch_standings(self, league_slug: str) -> list[NormalizedStanding]:
        """Fixture provider returns no standings."""
        return []


def get_provider(provider_name: Optional[str] = None) -> BaseSportsProvider:
    """Factory function to get the configured sports provider.

    Reads SPORTS_PROVIDER env var (or Django setting) to select provider:
    - "api_sports" → ApiSportsProvider (real API data)
    - anything else → FixtureSportsProvider (dev/test)

    Requires SPORTS_API_KEY for api_sports provider.
    """
    import os
    from django.conf import settings

    name = provider_name or getattr(settings, "SPORTS_PROVIDER", None) or os.environ.get("SPORTS_PROVIDER", "")

    if name == "espn":
        from apps.sports.services.providers.espn_provider import EspnSportsProvider
        return EspnSportsProvider()

    if name == "api_sports":
        api_key = getattr(settings, "SPORTS_API_KEY", None) or os.environ.get("SPORTS_API_KEY", "")
        if not api_key:
            logger.warning("SPORTS_PROVIDER=api_sports but SPORTS_API_KEY not set — falling back to fixture")
            return FixtureSportsProvider()
        from apps.sports.services.providers.api_sports_provider import ApiSportsProvider
        return ApiSportsProvider()

    return FixtureSportsProvider()


# ──────────────────────────────────────────────
# Fixture team data for seeding
# ──────────────────────────────────────────────

_FIXTURE_TEAMS = {
    "nfl": [
        {"name": "Chiefs", "location": "Kansas City", "abbr": "KC"},
        {"name": "49ers", "location": "San Francisco", "abbr": "SF"},
        {"name": "Eagles", "location": "Philadelphia", "abbr": "PHI"},
        {"name": "Bills", "location": "Buffalo", "abbr": "BUF"},
        {"name": "Cowboys", "location": "Dallas", "abbr": "DAL"},
        {"name": "Ravens", "location": "Baltimore", "abbr": "BAL"},
        {"name": "Lions", "location": "Detroit", "abbr": "DET"},
        {"name": "Packers", "location": "Green Bay", "abbr": "GB"},
    ],
    "nba": [
        {"name": "Celtics", "location": "Boston", "abbr": "BOS"},
        {"name": "Nuggets", "location": "Denver", "abbr": "DEN"},
        {"name": "Lakers", "location": "Los Angeles", "abbr": "LAL"},
        {"name": "Warriors", "location": "Golden State", "abbr": "GSW"},
        {"name": "Bucks", "location": "Milwaukee", "abbr": "MIL"},
        {"name": "Thunder", "location": "Oklahoma City", "abbr": "OKC"},
        {"name": "Mavericks", "location": "Dallas", "abbr": "DAL"},
        {"name": "76ers", "location": "Philadelphia", "abbr": "PHI"},
    ],
    "mlb": [
        {"name": "Rangers", "location": "Texas", "abbr": "TEX"},
        {"name": "Dodgers", "location": "Los Angeles", "abbr": "LAD"},
        {"name": "Braves", "location": "Atlanta", "abbr": "ATL"},
        {"name": "Yankees", "location": "New York", "abbr": "NYY"},
        {"name": "Astros", "location": "Houston", "abbr": "HOU"},
        {"name": "Phillies", "location": "Philadelphia", "abbr": "PHI"},
        {"name": "Orioles", "location": "Baltimore", "abbr": "BAL"},
        {"name": "Diamondbacks", "location": "Arizona", "abbr": "ARI"},
    ],
    "ncaaf": [
        {"name": "Crimson Tide", "location": "Alabama", "abbr": "ALA"},
        {"name": "Bulldogs", "location": "Georgia", "abbr": "UGA"},
        {"name": "Wolverines", "location": "Michigan", "abbr": "MICH"},
        {"name": "Buckeyes", "location": "Ohio State", "abbr": "OSU"},
        {"name": "Longhorns", "location": "Texas", "abbr": "TEX"},
        {"name": "Tigers", "location": "Clemson", "abbr": "CLEM"},
    ],
    "ncaab": [
        {"name": "Jayhawks", "location": "Kansas", "abbr": "KU"},
        {"name": "Blue Devils", "location": "Duke", "abbr": "DUKE"},
        {"name": "Tar Heels", "location": "North Carolina", "abbr": "UNC"},
        {"name": "Wildcats", "location": "Kentucky", "abbr": "UK"},
        {"name": "Huskies", "location": "Connecticut", "abbr": "UCON"},
        {"name": "Boilermakers", "location": "Purdue", "abbr": "PUR"},
    ],
    "ncaabb": [
        {"name": "Razorbacks", "location": "Arkansas", "abbr": "ARK"},
        {"name": "Volunteers", "location": "Tennessee", "abbr": "TENN"},
        {"name": "Tigers", "location": "LSU", "abbr": "LSU"},
        {"name": "Gators", "location": "Florida", "abbr": "FLA"},
        {"name": "Commodores", "location": "Vanderbilt", "abbr": "VAN"},
        {"name": "Volunteers", "location": "Tennessee", "abbr": "TENN"},
    ],
}
