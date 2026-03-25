"""Tests for Sports provider adapter layer."""
from datetime import date

from django.test import TestCase

from apps.sports.services.provider_adapter import (
    BaseSportsProvider,
    FixtureSportsProvider,
    NormalizedGame,
    NormalizedStanding,
    NormalizedTeam,
    get_provider,
)


class FixtureProviderTest(TestCase):
    def setUp(self):
        self.provider = FixtureSportsProvider()

    def test_provider_name(self):
        self.assertEqual(self.provider.provider_name(), "fixture")

    def test_fetch_nfl_teams(self):
        teams = self.provider.fetch_teams("nfl")
        self.assertGreater(len(teams), 0)
        for team in teams:
            self.assertIsInstance(team, NormalizedTeam)
            self.assertEqual(team.league_slug, "nfl")
            self.assertTrue(team.external_id.startswith("fixture_nfl_"))

    def test_fetch_nba_teams(self):
        teams = self.provider.fetch_teams("nba")
        self.assertGreater(len(teams), 0)

    def test_fetch_mlb_teams(self):
        teams = self.provider.fetch_teams("mlb")
        self.assertGreater(len(teams), 0)

    def test_fetch_ncaa_teams(self):
        for slug in ("ncaaf", "ncaab", "ncaabb"):
            teams = self.provider.fetch_teams(slug)
            self.assertGreater(len(teams), 0, f"No teams for {slug}")

    def test_fetch_unknown_league(self):
        teams = self.provider.fetch_teams("unknown")
        self.assertEqual(teams, [])

    def test_fetch_games_returns_empty(self):
        """Fixture provider returns no games — games are seeded manually."""
        games = self.provider.fetch_games([], date.today(), date.today())
        self.assertEqual(games, [])

    def test_fetch_standings_returns_empty(self):
        standings = self.provider.fetch_standings("nfl")
        self.assertEqual(standings, [])


class ProviderFactoryTest(TestCase):
    def test_get_default_provider(self):
        """Default provider is ESPN (free, no key required)."""
        from apps.sports.services.providers.espn_provider import EspnSportsProvider
        provider = get_provider()
        self.assertIsInstance(provider, EspnSportsProvider)

    def test_get_fixture_provider(self):
        provider = get_provider("fixture")
        self.assertIsInstance(provider, FixtureSportsProvider)

    def test_provider_is_base_class(self):
        provider = get_provider()
        self.assertIsInstance(provider, BaseSportsProvider)


class NormalizedDataTest(TestCase):
    def test_normalized_team(self):
        team = NormalizedTeam(
            external_id="test_1", name="Chiefs",
            location="Kansas City", abbreviation="KC",
            league_slug="nfl",
        )
        self.assertEqual(team.name, "Chiefs")
        self.assertEqual(team.league_slug, "nfl")

    def test_normalized_game(self):
        game = NormalizedGame(
            external_id="g_1",
            home_team_external_id="t_1",
            away_team_external_id="t_2",
            start_time="2026-03-23T19:00:00Z",
        )
        self.assertEqual(game.status, "scheduled")
        self.assertIsNone(game.home_score)

    def test_normalized_standing(self):
        standing = NormalizedStanding(
            team_external_id="t_1", wins=10, losses=5,
            win_pct=0.667, rank=3,
        )
        self.assertEqual(standing.wins, 10)
        self.assertEqual(standing.rank, 3)
