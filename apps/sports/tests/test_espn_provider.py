"""
Tests for ESPN Sports Provider.

Tests normalization, status mapping, league slug mapping, error handling,
and pitcher extraction using mocked HTTP responses.
"""
from datetime import date
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.sports.services.provider_adapter import get_provider
from apps.sports.services.providers.espn_provider import (
    EspnSportsProvider,
    _ESPN_LEAGUE_PATHS,
)


class TestEspnProviderFactory(TestCase):
    """Test provider factory returns ESPN provider."""

    def test_get_provider_espn(self):
        with self.settings(SPORTS_PROVIDER="espn"):
            provider = get_provider("espn")
            self.assertIsInstance(provider, EspnSportsProvider)
            self.assertEqual(provider.provider_name(), "espn")


class TestEspnLeaguePaths(TestCase):
    """Test league slug → ESPN path mapping."""

    def test_all_expected_leagues_mapped(self):
        expected = {"mlb", "nba", "ncaab", "ncaabb", "nfl", "ncaaf", "nhl"}
        self.assertEqual(set(_ESPN_LEAGUE_PATHS.keys()), expected)

    def test_mlb_path(self):
        self.assertEqual(_ESPN_LEAGUE_PATHS["mlb"], "baseball/mlb")

    def test_ncaab_path(self):
        self.assertEqual(_ESPN_LEAGUE_PATHS["ncaab"], "basketball/mens-college-basketball")

    def test_ncaabb_path(self):
        self.assertEqual(_ESPN_LEAGUE_PATHS["ncaabb"], "baseball/college-baseball")


class TestEspnStatusMapping(TestCase):
    """Test ESPN status → internal status mapping."""

    def setUp(self):
        self.provider = EspnSportsProvider()

    def test_pre_state_maps_to_scheduled(self):
        status = {"type": {"state": "pre", "completed": False, "description": ""}}
        self.assertEqual(self.provider._map_status(status), "scheduled")

    def test_in_state_maps_to_live(self):
        status = {"type": {"state": "in", "completed": False, "description": ""}}
        self.assertEqual(self.provider._map_status(status), "live")

    def test_post_completed_maps_to_final(self):
        status = {"type": {"state": "post", "completed": True, "description": "Final"}}
        self.assertEqual(self.provider._map_status(status), "final")

    def test_post_not_completed_maps_to_postponed(self):
        status = {"type": {"state": "post", "completed": False, "description": ""}}
        self.assertEqual(self.provider._map_status(status), "postponed")

    def test_postponed_in_description(self):
        status = {"type": {"state": "post", "completed": False, "description": "Postponed"}}
        self.assertEqual(self.provider._map_status(status), "postponed")

    def test_cancelled_in_description(self):
        status = {"type": {"state": "post", "completed": False, "description": "Cancelled"}}
        self.assertEqual(self.provider._map_status(status), "cancelled")

    def test_empty_status_defaults_to_scheduled(self):
        self.assertEqual(self.provider._map_status({}), "scheduled")
        self.assertEqual(self.provider._map_status(None), "scheduled")

    def test_unknown_state_defaults_to_scheduled(self):
        status = {"type": {"state": "unknown", "completed": False, "description": ""}}
        self.assertEqual(self.provider._map_status(status), "scheduled")


class TestEspnGameNormalization(TestCase):
    """Test game normalization from ESPN event data."""

    def setUp(self):
        self.provider = EspnSportsProvider()
        self.sample_event = {
            "id": "401234567",
            "date": "2026-03-25T23:10:00Z",
            "competitions": [{
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"id": "15", "displayName": "Atlanta Braves", "abbreviation": "ATL"},
                        "score": "5",
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": "22", "displayName": "Los Angeles Dodgers", "abbreviation": "LAD"},
                        "score": "3",
                    },
                ],
                "status": {
                    "type": {"state": "post", "completed": True, "description": "Final"},
                },
                "venue": {"fullName": "Truist Park"},
            }],
        }

    def test_normalizes_complete_game(self):
        game = self.provider._normalize_game(self.sample_event, "mlb")
        self.assertIsNotNone(game)
        self.assertEqual(game.external_id, "espn_mlb_401234567")
        self.assertEqual(game.home_team_external_id, "espn_mlb_15")
        self.assertEqual(game.away_team_external_id, "espn_mlb_22")
        self.assertEqual(game.home_score, 5)
        self.assertEqual(game.away_score, 3)
        self.assertEqual(game.status, "final")
        self.assertEqual(game.venue, "Truist Park")

    def test_missing_scores_default_to_zero(self):
        event = dict(self.sample_event)
        event["competitions"] = [{
            "competitors": [
                {"homeAway": "home", "team": {"id": "15"}, "score": None},
                {"homeAway": "away", "team": {"id": "22"}, "score": None},
            ],
            "status": {"type": {"state": "pre", "completed": False, "description": ""}},
            "venue": {},
        }]
        game = self.provider._normalize_game(event, "mlb")
        self.assertIsNotNone(game)
        self.assertEqual(game.home_score, 0)
        self.assertEqual(game.away_score, 0)

    def test_missing_venue_defaults_to_empty(self):
        event = dict(self.sample_event)
        event["competitions"] = [{
            "competitors": self.sample_event["competitions"][0]["competitors"],
            "status": self.sample_event["competitions"][0]["status"],
        }]
        game = self.provider._normalize_game(event, "mlb")
        self.assertIsNotNone(game)
        self.assertEqual(game.venue, "")

    def test_missing_event_id_returns_none(self):
        event = dict(self.sample_event)
        event["id"] = ""
        game = self.provider._normalize_game(event, "mlb")
        self.assertIsNone(game)

    def test_no_competitions_returns_none(self):
        event = {"id": "123", "date": "2026-03-25T23:10:00Z", "competitions": []}
        game = self.provider._normalize_game(event, "mlb")
        self.assertIsNone(game)

    def test_fewer_than_two_competitors_returns_none(self):
        event = {
            "id": "123",
            "date": "2026-03-25T23:10:00Z",
            "competitions": [{
                "competitors": [{"homeAway": "home", "team": {"id": "15"}, "score": "0"}],
                "status": {"type": {"state": "pre", "completed": False}},
            }],
        }
        game = self.provider._normalize_game(event, "mlb")
        self.assertIsNone(game)

    def test_missing_date_returns_none(self):
        event = dict(self.sample_event)
        event["date"] = ""
        game = self.provider._normalize_game(event, "mlb")
        self.assertIsNone(game)


class TestEspnTeamNormalization(TestCase):
    """Test team normalization from ESPN teams data."""

    def setUp(self):
        self.provider = EspnSportsProvider()

    @patch.object(EspnSportsProvider, "_request")
    def test_normalizes_teams(self, mock_request):
        mock_request.return_value = {
            "sports": [{
                "leagues": [{
                    "teams": [
                        {
                            "team": {
                                "id": "15",
                                "displayName": "Atlanta Braves",
                                "shortDisplayName": "Braves",
                                "location": "Atlanta",
                                "abbreviation": "ATL",
                                "logos": [{"href": "https://logo.url/atl.png"}],
                            }
                        },
                    ]
                }]
            }]
        }
        teams = self.provider.fetch_teams("mlb")
        self.assertEqual(len(teams), 1)
        self.assertEqual(teams[0].external_id, "espn_mlb_15")
        self.assertEqual(teams[0].name, "Braves")
        self.assertEqual(teams[0].location, "Atlanta")
        self.assertEqual(teams[0].abbreviation, "ATL")

    @patch.object(EspnSportsProvider, "_request")
    def test_empty_response_returns_empty(self, mock_request):
        mock_request.return_value = None
        teams = self.provider.fetch_teams("mlb")
        self.assertEqual(teams, [])

    @patch.object(EspnSportsProvider, "_request")
    def test_malformed_response_returns_empty(self, mock_request):
        mock_request.return_value = {"sports": []}
        teams = self.provider.fetch_teams("mlb")
        self.assertEqual(teams, [])

    def test_unknown_league_returns_empty(self):
        teams = self.provider.fetch_teams("unknown_league")
        self.assertEqual(teams, [])


class TestEspnStandingsNormalization(TestCase):
    """Test standings normalization from ESPN standings data."""

    def setUp(self):
        self.provider = EspnSportsProvider()

    def test_normalizes_standing_entry(self):
        entry = {
            "team": {"id": "15"},
            "stats": [
                {"name": "wins", "value": 88},
                {"name": "losses", "value": 74},
                {"name": "winPercent", "value": 0.543},
            ],
        }
        standing = self.provider._normalize_standing(entry, "mlb")
        self.assertIsNotNone(standing)
        self.assertEqual(standing.team_external_id, "espn_mlb_15")
        self.assertEqual(standing.wins, 88)
        self.assertEqual(standing.losses, 74)
        self.assertAlmostEqual(standing.win_pct, 0.543)

    def test_missing_stats_default_to_zero(self):
        entry = {
            "team": {"id": "15"},
            "stats": [],
        }
        standing = self.provider._normalize_standing(entry, "mlb")
        self.assertIsNotNone(standing)
        self.assertEqual(standing.wins, 0)
        self.assertEqual(standing.losses, 0)

    def test_missing_team_id_returns_none(self):
        entry = {"team": {}, "stats": []}
        standing = self.provider._normalize_standing(entry, "mlb")
        self.assertIsNone(standing)


class TestEspnHttpErrors(TestCase):
    """Test graceful error handling on HTTP failures."""

    def setUp(self):
        self.provider = EspnSportsProvider()

    @patch.object(EspnSportsProvider, "_request")
    def test_api_failure_returns_empty_teams(self, mock_request):
        mock_request.return_value = None
        teams = self.provider.fetch_teams("mlb")
        self.assertEqual(teams, [])

    @patch.object(EspnSportsProvider, "_request")
    def test_api_failure_returns_empty_standings(self, mock_request):
        mock_request.return_value = None
        standings = self.provider.fetch_standings("mlb")
        self.assertEqual(standings, [])

    @patch.object(EspnSportsProvider, "_request")
    def test_api_failure_returns_empty_games(self, mock_request):
        mock_request.return_value = None
        games = self.provider.fetch_games(["espn_mlb_15"], date(2026, 3, 25), date(2026, 3, 26))
        self.assertEqual(games, [])


class TestEspnDateLimits(TestCase):
    """Test that game fetches respect the 3-request-per-league limit."""

    def setUp(self):
        self.provider = EspnSportsProvider()

    @patch.object(EspnSportsProvider, "_request")
    def test_max_three_date_requests(self, mock_request):
        mock_request.return_value = {"events": []}
        # Request 5 days — should only make 3 requests
        self.provider.fetch_games(
            ["espn_mlb_15"],
            date(2026, 3, 20),
            date(2026, 3, 25),
        )
        self.assertEqual(mock_request.call_count, 3)

    @patch.object(EspnSportsProvider, "_request")
    def test_normal_window_makes_expected_calls(self, mock_request):
        mock_request.return_value = {"events": []}
        # 3-day window (yesterday + today + tomorrow)
        self.provider.fetch_games(
            ["espn_mlb_15"],
            date(2026, 3, 24),
            date(2026, 3, 26),
        )
        self.assertEqual(mock_request.call_count, 3)


class TestEspnPitcherExtraction(TestCase):
    """Test pitcher extraction from ESPN competition data."""

    def setUp(self):
        self.provider = EspnSportsProvider()

    def test_no_pitchers_returns_empty_strings(self):
        comp = {"competitors": [], "status": {}}
        home, away = self.provider._extract_pitchers(comp)
        self.assertEqual(home, "")
        self.assertEqual(away, "")

    def test_featured_athletes_extraction(self):
        comp = {
            "competitors": [
                {"homeAway": "home", "team": {"id": "15"}},
                {"homeAway": "away", "team": {"id": "22"}},
            ],
            "status": {
                "featuredAthletes": [
                    {
                        "displayName": "Winning Pitcher",
                        "athletes": [{"displayName": "Max Fried"}],
                    },
                ],
            },
        }
        home, away = self.provider._extract_pitchers(comp)
        self.assertEqual(home, "Max Fried")


class TestEspnSafeInt(TestCase):
    """Test safe integer conversion."""

    def test_string_number(self):
        self.assertEqual(EspnSportsProvider._safe_int("5"), 5)

    def test_none_returns_default(self):
        self.assertEqual(EspnSportsProvider._safe_int(None, 0), 0)

    def test_invalid_string_returns_default(self):
        self.assertEqual(EspnSportsProvider._safe_int("abc", 0), 0)

    def test_integer_passes_through(self):
        self.assertEqual(EspnSportsProvider._safe_int(42), 42)
