"""
Sports Domain — ESPN Public API Provider

Free, no-key-required sports data from ESPN's public scoreboard API.

Endpoint pattern:
    https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard
    https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams
    https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/standings

Supports: MLB, NBA, NCAA Basketball, NCAA Baseball, NFL, NCAA Football, NHL.
No API key. No rate limiting. No season resolution needed.

All responses are normalized to NormalizedTeam/Game/Standing before return.
This provider NEVER shapes internal models — adapter pattern enforced.
"""
import logging
from datetime import date, datetime, timedelta, timezone as dt_tz

import requests

from apps.sports.services.provider_adapter import (
    BaseSportsProvider,
    NormalizedGame,
    NormalizedStanding,
    NormalizedTeam,
)

logger = logging.getLogger(__name__)

# ESPN base URL
_ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

# Internal league slug → ESPN sport/league path
_ESPN_LEAGUE_PATHS = {
    "mlb": "baseball/mlb",
    "nba": "basketball/nba",
    "ncaab": "basketball/mens-college-basketball",
    "ncaabb": "baseball/college-baseball",
    "nfl": "football/nfl",
    "ncaaf": "football/college-football",
    "nhl": "hockey/nhl",
}

# Request timeout (seconds)
_TIMEOUT = 15

# Hard limit: max date requests per league per sync
_MAX_DATE_REQUESTS = 3


class EspnSportsProvider(BaseSportsProvider):
    """
    ESPN public API sports data provider.

    No API key required. All methods return normalized data or empty lists
    on failure. Never raises — logs errors and degrades gracefully.
    """

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "WholLifeJourney/1.0",
            "Accept": "application/json",
        })

    def provider_name(self) -> str:
        return "espn"

    # ── Teams ───────────────────────────────────────────────────────

    def fetch_teams(self, league_slug: str) -> list[NormalizedTeam]:
        """Fetch all teams for a league from ESPN."""
        espn_path = _ESPN_LEAGUE_PATHS.get(league_slug)
        if not espn_path:
            logger.warning("ESPN: no path mapping for league %s", league_slug)
            return []

        url = f"{_ESPN_BASE}/{espn_path}/teams"
        data = self._request(url)
        if not data:
            return []

        teams = []
        try:
            # ESPN wraps teams in sports[0].leagues[0].teams[]
            sports = data.get("sports", [])
            if not sports:
                return []
            leagues = sports[0].get("leagues", [])
            if not leagues:
                return []
            team_entries = leagues[0].get("teams", [])

            for entry in team_entries:
                team_data = entry.get("team", {})
                if not team_data:
                    continue

                team_id = team_data.get("id", "")
                if not team_id:
                    continue

                teams.append(NormalizedTeam(
                    external_id=f"espn_{league_slug}_{team_id}",
                    name=team_data.get("shortDisplayName", "") or team_data.get("name", ""),
                    location=team_data.get("location", ""),
                    abbreviation=team_data.get("abbreviation", ""),
                    league_slug=league_slug,
                    logo_url=self._extract_logo(team_data),
                ))
        except (KeyError, IndexError, TypeError) as e:
            logger.warning("ESPN: failed to parse teams for %s: %s", league_slug, e)

        return teams

    # ── Games ───────────────────────────────────────────────────────

    def fetch_games(
        self, team_external_ids: list[str], date_from: date, date_to: date
    ) -> list[NormalizedGame]:
        """Fetch games for teams within a date range.

        Fetches scoreboard data for each day in the range, per league.
        Hard limit: MAX 3 date requests per league per sync.
        """
        if not team_external_ids:
            return []

        # Determine which leagues to query from external_id prefixes
        leagues_needed = set()
        team_id_set = set(team_external_ids)
        for ext_id in team_external_ids:
            parts = ext_id.split("_")
            # Format: espn_{league_slug}_{team_id}
            if len(parts) >= 3 and parts[0] == "espn":
                leagues_needed.add(parts[1])

        if not leagues_needed:
            return []

        all_games = []

        for league_slug in leagues_needed:
            espn_path = _ESPN_LEAGUE_PATHS.get(league_slug)
            if not espn_path:
                continue

            # Loop date range with hard limit
            current = date_from
            requests_made = 0

            while current <= date_to and requests_made < _MAX_DATE_REQUESTS:
                date_str = current.strftime("%Y%m%d")
                url = f"{_ESPN_BASE}/{espn_path}/scoreboard"
                data = self._request(url, params={"dates": date_str})
                requests_made += 1

                if data:
                    events = data.get("events", [])
                    for event in events:
                        game = self._normalize_game(event, league_slug)
                        if game:
                            all_games.append(game)

                current += timedelta(days=1)

        return all_games

    # ── Standings ───────────────────────────────────────────────────

    def fetch_standings(self, league_slug: str) -> list[NormalizedStanding]:
        """Fetch current standings for a league."""
        espn_path = _ESPN_LEAGUE_PATHS.get(league_slug)
        if not espn_path:
            return []

        url = f"{_ESPN_BASE}/{espn_path}/standings"
        data = self._request(url)
        if not data:
            return []

        standings = []
        try:
            # ESPN standings structure: children[] (conferences/divisions)
            # each containing standings.entries[]
            children = data.get("children", [])
            for group in children:
                entries = group.get("standings", {}).get("entries", [])
                for entry in entries:
                    standing = self._normalize_standing(entry, league_slug)
                    if standing:
                        standings.append(standing)

            # Fallback: some leagues have flat standings at top level
            if not standings:
                top_entries = data.get("standings", {}).get("entries", [])
                for entry in top_entries:
                    standing = self._normalize_standing(entry, league_slug)
                    if standing:
                        standings.append(standing)

        except (KeyError, IndexError, TypeError) as e:
            logger.warning("ESPN: failed to parse standings for %s: %s", league_slug, e)

        return standings

    # ── HTTP Layer ──────────────────────────────────────────────────

    def _request(self, url, params=None):
        """Make an ESPN API request. Returns parsed JSON or None on failure."""
        try:
            resp = self._session.get(url, params=params, timeout=_TIMEOUT)

            if resp.status_code != 200:
                logger.warning("ESPN %s returned %d", url, resp.status_code)
                return None

            return resp.json()

        except requests.Timeout:
            logger.warning("ESPN timeout on %s", url)
            return None
        except requests.RequestException as e:
            logger.warning("ESPN request failed %s: %s", url, e)
            return None
        except (ValueError, KeyError) as e:
            logger.warning("ESPN parse error %s: %s", url, e)
            return None

    # ── Game Normalization ──────────────────────────────────────────

    def _normalize_game(self, event, league_slug):
        """Normalize an ESPN event into a NormalizedGame.

        Always returns a complete NormalizedGame or None.
        Never returns partial objects.
        """
        try:
            event_id = event.get("id", "")
            if not event_id:
                return None

            competitions = event.get("competitions", [])
            if not competitions:
                return None
            comp = competitions[0]

            # Extract teams
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                return None

            home = None
            away = None
            for c in competitors:
                if c.get("homeAway") == "home":
                    home = c
                elif c.get("homeAway") == "away":
                    away = c

            if not home or not away:
                return None

            home_team_id = home.get("team", {}).get("id", "")
            away_team_id = away.get("team", {}).get("id", "")
            if not home_team_id or not away_team_id:
                return None

            # Parse start time
            start_time = self._parse_datetime(event.get("date", ""))
            if not start_time:
                return None

            # Map status — strict mapping
            status = self._map_status(comp.get("status", {}))

            # Scores — default to 0 if missing
            home_score = self._safe_int(home.get("score"), 0)
            away_score = self._safe_int(away.get("score"), 0)

            # Venue — default to empty string if missing
            venue_data = comp.get("venue", {})
            venue = ""
            if isinstance(venue_data, dict):
                venue = venue_data.get("fullName", "") or ""

            # Pitchers (baseball only) — default to None if missing
            home_pitcher = ""
            away_pitcher = ""
            if league_slug in ("mlb", "ncaabb"):
                home_pitcher, away_pitcher = self._extract_pitchers(comp)

            return NormalizedGame(
                external_id=f"espn_{league_slug}_{event_id}",
                home_team_external_id=f"espn_{league_slug}_{home_team_id}",
                away_team_external_id=f"espn_{league_slug}_{away_team_id}",
                start_time=start_time,
                status=status,
                home_score=home_score,
                away_score=away_score,
                venue=venue,
                home_probable_pitcher=home_pitcher,
                away_probable_pitcher=away_pitcher,
            )
        except Exception as e:
            logger.warning("ESPN: failed to normalize game: %s", e)
            return None

    # ── Standing Normalization ──────────────────────────────────────

    def _normalize_standing(self, entry, league_slug):
        """Normalize an ESPN standings entry into a NormalizedStanding.

        Always returns a complete NormalizedStanding or None.
        """
        try:
            team_data = entry.get("team", {})
            team_id = team_data.get("id", "")
            if not team_id:
                return None

            # Extract stats by name from the stats array
            stats = entry.get("stats", [])
            stats_dict = {}
            for stat in stats:
                name = stat.get("name", "")
                value = stat.get("value", 0)
                if name:
                    stats_dict[name] = value

            wins = int(stats_dict.get("wins", 0) or 0)
            losses = int(stats_dict.get("losses", 0) or 0)
            win_pct = float(stats_dict.get("winPercent", 0.0) or 0.0)

            return NormalizedStanding(
                team_external_id=f"espn_{league_slug}_{team_id}",
                wins=wins,
                losses=losses,
                win_pct=win_pct,
            )
        except Exception as e:
            logger.warning("ESPN: failed to normalize standing: %s", e)
            return None

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _map_status(status_obj):
        """Map ESPN status to internal GameEvent status.

        Strict mapping:
            "pre" → scheduled
            "in" → live
            "post" + completed → final
            "post" + not completed → postponed
            unknown → scheduled
        """
        if not status_obj or not isinstance(status_obj, dict):
            return "scheduled"

        type_obj = status_obj.get("type", {})
        if not isinstance(type_obj, dict):
            return "scheduled"

        state = type_obj.get("state", "")
        completed = type_obj.get("completed", False)
        description = (type_obj.get("description", "") or "").lower()

        # Check for explicit postponed/cancelled in description
        if "postponed" in description:
            return "postponed"
        if "canceled" in description or "cancelled" in description:
            return "cancelled"

        if state == "pre":
            return "scheduled"
        elif state == "in":
            return "live"
        elif state == "post":
            return "final" if completed else "postponed"

        return "scheduled"

    @staticmethod
    def _parse_datetime(date_str):
        """Parse ISO datetime from ESPN response."""
        if not date_str:
            return None
        try:
            # ESPN returns: "2026-03-24T23:10Z" or "2026-03-24T23:10:00Z"
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_int(value, default=0):
        """Safely convert a value to int, returning default on failure."""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _extract_pitchers(competition):
        """Extract probable/winning/losing pitchers from ESPN competition data.

        Returns (home_pitcher, away_pitcher) as strings.
        Defaults to empty string if not available.
        """
        home_pitcher = ""
        away_pitcher = ""

        try:
            # Check probables first (pre-game)
            probables = competition.get("probables", [])
            for probable in probables:
                athlete = probable.get("athlete", {})
                pitcher_name = athlete.get("displayName", "")
                if not pitcher_name:
                    continue

                # Determine home/away from team reference
                team_ref = probable.get("team", {})
                team_id = team_ref.get("$ref", "").split("/")[-1] if "$ref" in team_ref else ""

                # Check competitors to match team_id to home/away
                competitors = competition.get("competitors", [])
                for c in competitors:
                    if c.get("team", {}).get("id", "") == team_id:
                        if c.get("homeAway") == "home":
                            home_pitcher = pitcher_name
                        elif c.get("homeAway") == "away":
                            away_pitcher = pitcher_name

            # Fallback: check featuredAthletes for post-game pitchers
            if not home_pitcher and not away_pitcher:
                status = competition.get("status", {})
                featured = status.get("featuredAthletes", [])
                for group in featured:
                    athletes = group.get("athletes", [])
                    label = (group.get("displayName", "") or "").lower()
                    if athletes and ("winning" in label or "losing" in label):
                        # Just grab the first featured pitcher as a display item
                        name = athletes[0].get("displayName", "")
                        if name and not home_pitcher:
                            home_pitcher = name

        except (KeyError, IndexError, TypeError):
            pass

        return home_pitcher, away_pitcher

    @staticmethod
    def _extract_logo(team_data):
        """Extract team logo URL from ESPN team data."""
        logos = team_data.get("logos", [])
        if logos and isinstance(logos, list):
            return logos[0].get("href", "") if logos[0] else ""
        return ""
