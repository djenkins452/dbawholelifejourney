"""Tests for Sports domain models."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.sports.models import (
    GameEvent, League, Sport, Team, UserTeamFollow,
)
from apps.users.models import User


class SportModelTest(TestCase):
    def test_create_sport(self):
        sport = Sport.objects.create(name="Football", slug="football")
        self.assertEqual(str(sport), "Football")

    def test_unique_slug(self):
        Sport.objects.create(name="Football", slug="football")
        with self.assertRaises(Exception):
            Sport.objects.create(name="Football 2", slug="football")


class LeagueModelTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Football", slug="football")

    def test_create_league(self):
        league = League.objects.create(
            sport=self.sport, name="NFL", slug="nfl", abbreviation="NFL"
        )
        self.assertEqual(str(league), "NFL")
        self.assertFalse(league.is_college)

    def test_college_league(self):
        league = League.objects.create(
            sport=self.sport, name="NCAA Football", slug="ncaaf",
            abbreviation="NCAAF", is_college=True,
        )
        self.assertTrue(league.is_college)


class TeamModelTest(TestCase):
    def setUp(self):
        sport = Sport.objects.create(name="Football", slug="football")
        self.league = League.objects.create(
            sport=sport, name="NFL", slug="nfl", abbreviation="NFL"
        )

    def test_create_team(self):
        team = Team.objects.create(
            league=self.league, name="Chiefs",
            location="Kansas City", abbreviation="KC",
        )
        self.assertEqual(str(team), "Kansas City Chiefs")
        self.assertEqual(team.full_name, "Kansas City Chiefs")

    def test_unique_team_per_league(self):
        Team.objects.create(
            league=self.league, name="Chiefs",
            location="Kansas City", abbreviation="KC",
        )
        with self.assertRaises(Exception):
            Team.objects.create(
                league=self.league, name="Other",
                location="Other", abbreviation="KC",
            )


class GameEventModelTest(TestCase):
    def setUp(self):
        sport = Sport.objects.create(name="Football", slug="football")
        league = League.objects.create(
            sport=sport, name="NFL", slug="nfl", abbreviation="NFL"
        )
        self.chiefs = Team.objects.create(
            league=league, name="Chiefs", location="Kansas City", abbreviation="KC"
        )
        self.niners = Team.objects.create(
            league=league, name="49ers", location="San Francisco", abbreviation="SF"
        )

    def test_create_game(self):
        game = GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now() + timedelta(hours=2),
        )
        self.assertEqual(game.status, GameEvent.STATUS_SCHEDULED)
        self.assertFalse(game.is_live)
        self.assertFalse(game.is_final)

    def test_get_winner_home(self):
        game = GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now(), status=GameEvent.STATUS_FINAL,
            home_score=27, away_score=20,
        )
        self.assertEqual(game.get_winner(), self.chiefs)

    def test_get_winner_away(self):
        game = GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now(), status=GameEvent.STATUS_FINAL,
            home_score=20, away_score=27,
        )
        self.assertEqual(game.get_winner(), self.niners)

    def test_get_winner_tie(self):
        game = GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now(), status=GameEvent.STATUS_FINAL,
            home_score=20, away_score=20,
        )
        self.assertIsNone(game.get_winner())

    def test_get_winner_not_final(self):
        game = GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now(), status=GameEvent.STATUS_SCHEDULED,
        )
        self.assertIsNone(game.get_winner())

    def test_user_team_won(self):
        game = GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now(), status=GameEvent.STATUS_FINAL,
            home_score=27, away_score=20,
        )
        self.assertTrue(game.user_team_won(self.chiefs))
        self.assertFalse(game.user_team_won(self.niners))

    def test_user_team_lost(self):
        game = GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now(), status=GameEvent.STATUS_FINAL,
            home_score=20, away_score=27,
        )
        self.assertTrue(game.user_team_lost(self.chiefs))
        self.assertFalse(game.user_team_lost(self.niners))

    def test_get_opponent(self):
        game = GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now(),
        )
        self.assertEqual(game.get_opponent(self.chiefs), self.niners)
        self.assertEqual(game.get_opponent(self.niners), self.chiefs)

    def test_get_score_display(self):
        game = GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now(), status=GameEvent.STATUS_FINAL,
            home_score=27, away_score=20,
        )
        self.assertEqual(game.get_score_display(), "20-27")

    def test_score_display_no_scores(self):
        game = GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now(),
        )
        self.assertEqual(game.get_score_display(), "")


class UserTeamFollowTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123"
        )
        sport = Sport.objects.create(name="Football", slug="football")
        league = League.objects.create(
            sport=sport, name="NFL", slug="nfl", abbreviation="NFL"
        )
        self.team = Team.objects.create(
            league=league, name="Chiefs", location="Kansas City", abbreviation="KC"
        )

    def test_create_follow(self):
        follow = UserTeamFollow.objects.create(
            user=self.user, team=self.team, priority=1,
        )
        self.assertEqual(follow.priority, UserTeamFollow.PRIORITY_PRIMARY)
        self.assertTrue(follow.is_active)

    def test_unique_user_team(self):
        UserTeamFollow.objects.create(user=self.user, team=self.team)
        with self.assertRaises(Exception):
            UserTeamFollow.objects.create(user=self.user, team=self.team)
