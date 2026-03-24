"""
Sports Domain — API-Sports Provider (api-sports.io)

Real data provider using the API-Sports family of APIs:
  - v1.baseball.api-sports.io   (MLB, NCAA Baseball)
  - v1.basketball.api-sports.io (NBA, NCAA Basketball)
  - v1.hockey.api-sports.io     (NHL)
  - v3.football.api-sports.io   (MLS — soccer/football)

Auth: x-apisports-key header (single key works across all sport APIs).
Rate limit: Free tier = 100 req/day. Pro tier varies.

All responses are normalized to NormalizedTeam/Game/Standing before return.
This provider NEVER shapes internal models — adapter pattern enforced.
"""
import logging
from datetime import date, datetime, timedelta, timezone as dt_tz

import requests
from django.conf import settings

from apps.sports.services.provider_adapter import (
    BaseSportsProvider,
    NormalizedGame,
    NormalizedStanding,
    NormalizedTeam,
)

logger = logging.getLogger(__name__)

# API-Sports host mapping per league
# Each sport has its own subdomain
_SPORT_HOSTS = {
    "mlb": "v1.baseball.api-sports.io",
    "nba": "v1.basketball.api-sports.io",
    "nhl": "v1.hockey.api-sports.io",
    "mls": "v3.football.api-sports.io",
    # NCAA — same sport hosts, different league IDs
    "ncaaf": None,      # No API-Sports coverage for college football
    "ncaab": None,      # No reliable college basketball API
    "ncaabb": None,     # No reliable college baseball API
}

# API-Sports league IDs (their internal identifiers)
_LEAGUE_IDS = {
    "mlb": 1,       # MLB
    "nba": 12,      # NBA (standard league)
    "nhl": 57,      # NHL
    "mls": 253,     # MLS (football/soccer API)
}

# Season values (current season)
_CURRENT_SEASONS = {
    "mlb": "2025",     # Baseball uses calendar year
    "nba": "2025-2026",  # Basketball spans two years
    "nhl": "2025",     # Hockey uses start year
    "mls": "2026",     # MLS uses calendar year
}

# Status mapping: API-Sports status → our GameEvent status
_STATUS_MAP_BASEBALL = {
    "NS": "scheduled",        # Not started
    "IN1": "live", "IN2": "live", "IN3": "live", "IN4": "live",
    "IN5": "live", "IN6": "live", "IN7": "live", "IN8": "live",
    "IN9": "live",
    "POST": "live",           # Postponed but live (rain delay)
    "FT": "final",            # Finished
    "AOT": "final",           # After overtime
    "CANC": "cancelled",
    "PST": "postponed",
    "SUSP": "postponed",
}

_STATUS_MAP_BASKETBALL = {
    "NS": "scheduled",
    "Q1": "live", "Q2": "live", "Q3": "live", "Q4": "live",
    "OT": "live", "HT": "live", "BT": "live",
    "FT": "final", "AOT": "final",
    "CANC": "cancelled", "PST": "postponed", "SUSP": "postponed",
}

_STATUS_MAP_HOCKEY = {
    "NS": "scheduled",
    "P1": "live", "P2": "live", "P3": "live",
    "OT": "live", "PT": "live", "BT": "live",
    "FT": "final", "AOT": "final", "AP": "final",
    "CANC": "cancelled", "PST": "postponed", "SUSP": "postponed",
}

_STATUS_MAP_FOOTBALL = {
    "NS": "scheduled", "TBD": "scheduled",
    "1H": "live", "HT": "live", "2H": "live", "ET": "live",
    "P": "live", "BT": "live", "LIVE": "live",
    "FT": "final", "AET": "final", "PEN": "final",
    "CANC": "cancelled", "PST": "postponed", "SUSP": "postponed",
    "ABD": "cancelled", "AWD": "final", "WO": "final",
}

_STATUS_MAPS = {
    "mlb": _STATUS_MAP_BASEBALL,
    "nba": _STATUS_MAP_BASKETBALL,
    "nhl": _STATUS_MAP_HOCKEY,
    "mls": _STATUS_MAP_FOOTBALL,
}

# Request timeout
_TIMEOUT = 15


class ApiSportsProvider(BaseSportsProvider):
    """
    Real sports data provider using api-sports.io APIs.

    Reads SPORTS_API_KEY from Django settings / environment.
    All methods return normalized data or empty lists on failure.
    Never raises — logs errors and degrades gracefully.
    """

    def __init__(self):
        self._api_key = getattr(settings, "SPORTS_API_KEY", "")
        if not self._api_key:
            import os
            self._api_key = os.environ.get("SPORTS_API_KEY", "")
        self._session = requests.Session()
        self._session.headers.update({
            "x-apisports-key": self._api_key,
        })

    def provider_name(self) -> str:
        return "api_sports"

    # ── Teams ───────────────────────────────────────────────────────

    def fetch_teams(self, league_slug: str) -> list[NormalizedTeam]:
        """Fetch all teams for a league from API-Sports."""
        host = _SPORT_HOSTS.get(league_slug)
        league_id = _LEAGUE_IDS.get(league_slug)
        season = _CURRENT_SEASONS.get(league_slug)

        if not host or not league_id:
            return []

        if league_slug == "mls":
            # Football API uses /teams?league=X&season=Y
            data = self._request(host, "/teams", {
                "league": league_id, "season": season,
            })
            return [self._normalize_football_team(t, league_slug) for t in (data or [])]
        else:
            # Baseball/Basketball/Hockey use /teams?league=X&season=Y
            data = self._request(host, "/teams", {
                "league": league_id, "season": season,
            })
            return [self._normalize_team(t, league_slug) for t in (data or [])]

    # ── Games ───────────────────────────────────────────────────────

    def fetch_games(
        self, team_external_ids: list[str], date_from: date, date_to: date
    ) -> list[NormalizedGame]:
        """Fetch games for teams within a date range."""
        if not team_external_ids:
            return []

        # Group by sport host (all teams in same league use same host)
        # We fetch by date range rather than per-team to minimize API calls
        all_games = []

        # Determine which leagues are represented
        leagues_seen = set()
        for ext_id in team_external_ids:
            # External IDs are formatted as "api_sports_{league}_{id}"
            parts = ext_id.split("_")
            if len(parts) >= 3:
                leagues_seen.add(parts[2])  # league slug

        # Also try to infer from the team objects
        if not leagues_seen:
            from apps.sports.models import Team
            leagues_seen = set(
                Team.objects.filter(external_id__in=team_external_ids)
                .values_list("league__slug", flat=True)
                .distinct()
            )

        for league_slug in leagues_seen:
            host = _SPORT_HOSTS.get(league_slug)
            league_id = _LEAGUE_IDS.get(league_slug)
            season = _CURRENT_SEASONS.get(league_slug)

            if not host or not league_id:
                continue

            # Fetch games day by day (API-Sports requires date parameter)
            current = date_from
            while current <= date_to:
                date_str = current.isoformat()

                if league_slug == "mls":
                    games_data = self._request(host, "/fixtures", {
                        "league": league_id, "season": season, "date": date_str,
                    })
                    for g in (games_data or []):
                        normalized = self._normalize_football_game(g, league_slug)
                        if normalized:
                            all_games.append(normalized)
                else:
                    games_data = self._request(host, "/games", {
                        "league": league_id, "season": season, "date": date_str,
                    })
                    for g in (games_data or []):
                        normalized = self._normalize_game(g, league_slug)
                        if normalized:
                            all_games.append(normalized)

                current += timedelta(days=1)

        return all_games

    # ── Standings ───────────────────────────────────────────────────

    def fetch_standings(self, league_slug: str) -> list[NormalizedStanding]:
        """Fetch current standings for a league."""
        host = _SPORT_HOSTS.get(league_slug)
        league_id = _LEAGUE_IDS.get(league_slug)
        season = _CURRENT_SEASONS.get(league_slug)

        if not host or not league_id:
            return []

        if league_slug == "mls":
            data = self._request(host, "/standings", {
                "league": league_id, "season": season,
            })
            return self._normalize_football_standings(data, league_slug)
        else:
            data = self._request(host, "/standings", {
                "league": league_id, "season": season,
            })
            return self._normalize_standings(data, league_slug)

    # ── HTTP Layer ──────────────────────────────────────────────────

    def _request(self, host, endpoint, params=None):
        """Make an API request. Returns response data or None on failure."""
        url = f"https://{host}{endpoint}"
        try:
            resp = self._session.get(url, params=params, timeout=_TIMEOUT)

            if resp.status_code == 429:
                logger.warning("API-Sports rate limited on %s%s", host, endpoint)
                return None

            if resp.status_code != 200:
                logger.warning(
                    "API-Sports %s%s returned %d", host, endpoint, resp.status_code
                )
                return None

            body = resp.json()

            # API-Sports wraps data in {"response": [...]}
            if isinstance(body, dict):
                errors = body.get("errors")
                if errors and isinstance(errors, dict) and errors:
                    logger.warning("API-Sports errors on %s%s: %s", host, endpoint, errors)
                    return None
                return body.get("response", [])

            return body

        except requests.Timeout:
            logger.warning("API-Sports timeout on %s%s", host, endpoint)
            return None
        except requests.RequestException as e:
            logger.warning("API-Sports request failed %s%s: %s", host, endpoint, e)
            return None
        except (ValueError, KeyError) as e:
            logger.warning("API-Sports parse error %s%s: %s", host, endpoint, e)
            return None

    # ── Normalization: Baseball / Basketball / Hockey ────────────────

    def _normalize_team(self, data, league_slug):
        """Normalize team from baseball/basketball/hockey API."""
        team = data.get("id", "")
        name = data.get("name", "")
        # Split "City Name" — API-Sports doesn't separate location/name consistently
        # Use full name as both for now; sync_service matches by external_id
        return NormalizedTeam(
            external_id=f"api_sports_{league_slug}_{team}",
            name=name,
            location="",
            abbreviation=data.get("code", "") or "",
            league_slug=league_slug,
            logo_url=data.get("logo", ""),
        )

    def _normalize_game(self, data, league_slug):
        """Normalize game from baseball/basketball/hockey API."""
        try:
            game_id = data.get("id", "")
            status_data = data.get("status", {})
            short_status = status_data.get("short", "NS")
            scores = data.get("scores", {})
            teams = data.get("teams", {})
            date_str = data.get("date", "")

            # Parse datetime
            start_time = self._parse_datetime(date_str)
            if not start_time:
                return None

            home_team = teams.get("home", {})
            away_team = teams.get("away", {})
            home_id = home_team.get("id", "")
            away_id = away_team.get("id", "")

            # Map status
            status_map = _STATUS_MAPS.get(league_slug, {})
            status = status_map.get(short_status, "scheduled")

            # Scores
            home_score = scores.get("home", {})
            away_score = scores.get("away", {})
            # Baseball/basketball/hockey: scores might be nested
            if isinstance(home_score, dict):
                home_score = home_score.get("total")
            if isinstance(away_score, dict):
                away_score = away_score.get("total")

            return NormalizedGame(
                external_id=f"api_sports_{league_slug}_{game_id}",
                home_team_external_id=f"api_sports_{league_slug}_{home_id}",
                away_team_external_id=f"api_sports_{league_slug}_{away_id}",
                start_time=start_time,
                status=status,
                home_score=home_score,
                away_score=away_score,
                venue="",  # Not always in game response
            )
        except Exception as e:
            logger.debug("Failed to normalize game: %s", e)
            return None

    def _normalize_standings(self, data, league_slug):
        """Normalize standings from baseball/basketball/hockey API."""
        results = []
        if not data:
            return results

        for entry in data:
            # API-Sports standings structure varies — handle list of lists
            if isinstance(entry, list):
                for team_entry in entry:
                    standing = self._extract_standing(team_entry, league_slug)
                    if standing:
                        results.append(standing)
            elif isinstance(entry, dict):
                standing = self._extract_standing(entry, league_slug)
                if standing:
                    results.append(standing)

        return results

    def _extract_standing(self, entry, league_slug):
        """Extract a single standing entry."""
        try:
            team = entry.get("team", {})
            team_id = team.get("id", "")
            games = entry.get("games", {}) or entry.get("all", {})
            win = games.get("win", {})
            lose = games.get("lose", {})

            # Different structures per sport
            if isinstance(win, dict):
                wins = win.get("total", 0) or 0
            else:
                wins = win or 0

            if isinstance(lose, dict):
                losses = lose.get("total", 0) or 0
            else:
                losses = lose or 0

            # Fallback: some sports use "won"/"lost" at top level
            if not wins and not losses:
                wins = entry.get("won", 0) or 0
                losses = entry.get("lost", 0) or 0

            return NormalizedStanding(
                team_external_id=f"api_sports_{league_slug}_{team_id}",
                wins=wins,
                losses=losses,
            )
        except Exception:
            return None

    # ── Normalization: Football (Soccer/MLS) ────────────────────────

    def _normalize_football_team(self, data, league_slug):
        """Normalize team from football API (MLS)."""
        team = data.get("team", {})
        return NormalizedTeam(
            external_id=f"api_sports_{league_slug}_{team.get('id', '')}",
            name=team.get("name", ""),
            location="",
            abbreviation=team.get("code", "") or "",
            league_slug=league_slug,
            logo_url=team.get("logo", ""),
        )

    def _normalize_football_game(self, data, league_slug):
        """Normalize game from football API (MLS)."""
        try:
            fixture = data.get("fixture", {})
            teams = data.get("teams", {})
            goals = data.get("goals", {})
            game_id = fixture.get("id", "")
            status = fixture.get("status", {})
            short_status = status.get("short", "NS")
            date_str = fixture.get("date", "")

            start_time = self._parse_datetime(date_str)
            if not start_time:
                return None

            home = teams.get("home", {})
            away = teams.get("away", {})

            mapped_status = _STATUS_MAP_FOOTBALL.get(short_status, "scheduled")

            return NormalizedGame(
                external_id=f"api_sports_{league_slug}_{game_id}",
                home_team_external_id=f"api_sports_{league_slug}_{home.get('id', '')}",
                away_team_external_id=f"api_sports_{league_slug}_{away.get('id', '')}",
                start_time=start_time,
                status=mapped_status,
                home_score=goals.get("home"),
                away_score=goals.get("away"),
                venue=fixture.get("venue", {}).get("name", "") if isinstance(fixture.get("venue"), dict) else "",
            )
        except Exception as e:
            logger.debug("Failed to normalize football game: %s", e)
            return None

    def _normalize_football_standings(self, data, league_slug):
        """Normalize standings from football API (MLS)."""
        results = []
        if not data:
            return results

        for league_block in data:
            standings_list = league_block.get("league", {}).get("standings", [])
            for group in standings_list:
                for entry in group:
                    try:
                        team = entry.get("team", {})
                        team_id = team.get("id", "")
                        all_stats = entry.get("all", {})
                        wins = all_stats.get("win", 0) or 0
                        losses = all_stats.get("lose", 0) or 0
                        results.append(NormalizedStanding(
                            team_external_id=f"api_sports_{league_slug}_{team_id}",
                            wins=wins,
                            losses=losses,
                        ))
                    except Exception:
                        continue

        return results

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_datetime(date_str):
        """Parse ISO datetime from API-Sports response."""
        if not date_str:
            return None
        try:
            # API-Sports returns ISO format: "2026-03-24T23:10:00+00:00"
            return datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            try:
                # Fallback: some responses use "2026-03-24T23:10:00Z"
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return None
