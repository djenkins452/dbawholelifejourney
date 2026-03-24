"""Tests for Sports signal generation.

Key architecture rule: Disabled module MUST produce ZERO signals.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.sports.models import GameEvent, League, Sport, Team, UserTeamFollow
from apps.sports.services.signal_generator import (
    SIGNAL_GAME_COMPLETED,
    SIGNAL_GAME_LIVE,
    SIGNAL_GAME_STARTING_SOON,
    SIGNAL_GAME_TODAY,
    SIGNAL_LOSING_STREAK,
    SIGNAL_TEAM_LOSS,
    SIGNAL_TEAM_WIN,
    SIGNAL_WIN_STREAK,
    generate_sports_signals,
)
from apps.sports.services.time_windows import GameTimeWindow
from apps.users.models import User


def _create_fixtures():
    """Create base sport/league/team fixtures for tests."""
    sport = Sport.objects.create(name="Football", slug="football")
    league = League.objects.create(
        sport=sport, name="NFL", slug="nfl", abbreviation="NFL"
    )
    chiefs = Team.objects.create(
        league=league, name="Chiefs", location="Kansas City", abbreviation="KC"
    )
    niners = Team.objects.create(
        league=league, name="49ers", location="San Francisco", abbreviation="SF"
    )
    return sport, league, chiefs, niners


class DisabledModuleTest(TestCase):
    """CRITICAL: Disabled module = ZERO signals, ZERO activity."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="disabled@example.com", password="testpass123"
        )
        _, _, self.chiefs, self.niners = _create_fixtures()
        # Follow a team but keep module disabled
        UserTeamFollow.objects.create(
            user=self.user, team=self.chiefs, priority=1
        )
        # Create a game today
        GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now() + timedelta(hours=2),
        )

    def test_disabled_module_produces_zero_signals(self):
        """Module disabled (default) — NO signals generated."""
        prefs = self.user.preferences
        self.assertFalse(prefs.sports_enabled)
        signals = generate_sports_signals(self.user)
        self.assertEqual(signals, [])

    def test_enabled_module_produces_signals(self):
        """Module enabled — signals generated for followed teams."""
        prefs = self.user.preferences
        prefs.sports_enabled = True
        prefs.save()
        signals = generate_sports_signals(self.user)
        self.assertGreater(len(signals), 0)


class GameTodaySignalTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="today@example.com", password="testpass123"
        )
        prefs = self.user.preferences
        prefs.sports_enabled = True
        prefs.save()
        _, _, self.chiefs, self.niners = _create_fixtures()
        UserTeamFollow.objects.create(
            user=self.user, team=self.chiefs, priority=1
        )

    @patch("apps.sports.services.signal_generator.timezone")
    def test_game_today_signal(self, mock_tz):
        """Game scheduled for today generates game_today signal."""
        # Pin 'now' to 10 AM UTC so +4h is still today
        fake_now = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
        mock_tz.now.return_value = fake_now
        GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=fake_now + timedelta(hours=4),
        )
        signals = generate_sports_signals(self.user)
        signal_types = [s["signal_type"] for s in signals]
        self.assertIn(SIGNAL_GAME_TODAY, signal_types)

    def test_no_signal_for_unfollowed_team(self):
        """Games involving only unfollowed teams produce no signals."""
        sport = Sport.objects.get(slug="football")
        league = League.objects.get(slug="nfl")
        bills = Team.objects.create(
            league=league, name="Bills", location="Buffalo", abbreviation="BUF"
        )
        eagles = Team.objects.create(
            league=league, name="Eagles", location="Philadelphia", abbreviation="PHI"
        )
        GameEvent.objects.create(
            home_team=bills, away_team=eagles,
            start_time=timezone.now() + timedelta(hours=4),
        )
        signals = generate_sports_signals(self.user)
        # Should only have signals for chiefs games, not bills/eagles
        for s in signals:
            self.assertEqual(s["team_id"], self.chiefs.id)


class GameStartingSoonSignalTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="soon@example.com", password="testpass123"
        )
        prefs = self.user.preferences
        prefs.sports_enabled = True
        prefs.save()
        _, _, self.chiefs, self.niners = _create_fixtures()
        UserTeamFollow.objects.create(
            user=self.user, team=self.chiefs, priority=1
        )

    def test_game_starting_soon_signal(self):
        """Game within 60 minutes generates game_starting_soon signal."""
        GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now() + timedelta(minutes=30),
        )
        signals = generate_sports_signals(self.user)
        signal_types = [s["signal_type"] for s in signals]
        self.assertIn(SIGNAL_GAME_STARTING_SOON, signal_types)
        # Should also emit game_today
        self.assertIn(SIGNAL_GAME_TODAY, signal_types)


class GameLiveSignalTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="live@example.com", password="testpass123"
        )
        prefs = self.user.preferences
        prefs.sports_enabled = True
        prefs.save()
        _, _, self.chiefs, self.niners = _create_fixtures()
        UserTeamFollow.objects.create(
            user=self.user, team=self.chiefs, priority=1
        )

    def test_live_game_signal(self):
        """Live game generates game_live signal."""
        GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now() - timedelta(hours=1),
            status=GameEvent.STATUS_LIVE,
            home_score=14, away_score=7,
        )
        signals = generate_sports_signals(self.user)
        signal_types = [s["signal_type"] for s in signals]
        self.assertIn(SIGNAL_GAME_LIVE, signal_types)


class NoNoiseSignalsTest(TestCase):
    """Verify only the 5 required signals are generated — no noise."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="nonoise@example.com", password="testpass123"
        )
        prefs = self.user.preferences
        prefs.sports_enabled = True
        prefs.save()
        _, _, self.chiefs, self.niners = _create_fixtures()
        UserTeamFollow.objects.create(
            user=self.user, team=self.chiefs, priority=1
        )

    def test_completed_game_produces_no_event_signal(self):
        """Completed games do NOT produce game_completed/team_win/team_loss signals."""
        GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now() - timedelta(hours=3),
            status=GameEvent.STATUS_FINAL,
            home_score=27, away_score=20,
        )
        signals = generate_sports_signals(self.user)
        signal_types = {s["signal_type"] for s in signals}
        # Only these 5 signals are allowed
        allowed = {SIGNAL_GAME_LIVE, SIGNAL_GAME_STARTING_SOON, SIGNAL_GAME_TODAY,
                   SIGNAL_WIN_STREAK, SIGNAL_LOSING_STREAK}
        self.assertTrue(signal_types.issubset(allowed),
                        f"Unexpected signals: {signal_types - allowed}")

    def test_only_five_signal_types_exist(self):
        """Create various game states — only 5 signal types should appear."""
        now = timezone.now()
        # Live game
        GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=now - timedelta(hours=1),
            status=GameEvent.STATUS_LIVE, home_score=14, away_score=7,
        )
        # Completed game
        GameEvent.objects.create(
            home_team=self.chiefs, away_team=self.niners,
            start_time=now - timedelta(hours=4),
            status=GameEvent.STATUS_FINAL, home_score=27, away_score=20,
        )
        signals = generate_sports_signals(self.user)
        signal_types = {s["signal_type"] for s in signals}
        allowed = {SIGNAL_GAME_LIVE, SIGNAL_GAME_STARTING_SOON, SIGNAL_GAME_TODAY,
                   SIGNAL_WIN_STREAK, SIGNAL_LOSING_STREAK}
        self.assertTrue(signal_types.issubset(allowed))


class StreakSignalTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="streak@example.com", password="testpass123"
        )
        prefs = self.user.preferences
        prefs.sports_enabled = True
        prefs.save()
        _, _, self.chiefs, self.niners = _create_fixtures()
        UserTeamFollow.objects.create(
            user=self.user, team=self.chiefs, priority=1
        )

    def test_win_streak_signal(self):
        """3+ consecutive wins generates win_streak signal."""
        now = timezone.now()
        for i in range(4):
            GameEvent.objects.create(
                home_team=self.chiefs, away_team=self.niners,
                start_time=now - timedelta(days=i * 7 + 1),
                status=GameEvent.STATUS_FINAL,
                home_score=27, away_score=20,
            )
        signals = generate_sports_signals(self.user)
        signal_types = [s["signal_type"] for s in signals]
        self.assertIn(SIGNAL_WIN_STREAK, signal_types)
        streak_signal = next(s for s in signals if s["signal_type"] == SIGNAL_WIN_STREAK)
        self.assertEqual(streak_signal["data"]["streak_length"], 4)

    def test_losing_streak_signal(self):
        """3+ consecutive losses generates losing_streak signal."""
        now = timezone.now()
        for i in range(3):
            GameEvent.objects.create(
                home_team=self.chiefs, away_team=self.niners,
                start_time=now - timedelta(days=i * 7 + 1),
                status=GameEvent.STATUS_FINAL,
                home_score=10, away_score=27,
            )
        signals = generate_sports_signals(self.user)
        signal_types = [s["signal_type"] for s in signals]
        self.assertIn(SIGNAL_LOSING_STREAK, signal_types)

    def test_no_streak_below_threshold(self):
        """2 consecutive wins is NOT a streak (threshold is 3)."""
        now = timezone.now()
        for i in range(2):
            GameEvent.objects.create(
                home_team=self.chiefs, away_team=self.niners,
                start_time=now - timedelta(days=i * 7 + 1),
                status=GameEvent.STATUS_FINAL,
                home_score=27, away_score=20,
            )
        signals = generate_sports_signals(self.user)
        signal_types = [s["signal_type"] for s in signals]
        self.assertNotIn(SIGNAL_WIN_STREAK, signal_types)


class TimeWindowTest(TestCase):
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

    def test_active_window(self):
        game = GameEvent(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now() - timedelta(hours=1),
            status=GameEvent.STATUS_LIVE,
        )
        tw = GameTimeWindow(game)
        self.assertEqual(tw.window, GameTimeWindow.ACTIVE)
        self.assertTrue(tw.is_actionable)

    def test_starting_soon_window(self):
        game = GameEvent(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now() + timedelta(minutes=30),
            status=GameEvent.STATUS_SCHEDULED,
        )
        tw = GameTimeWindow(game)
        self.assertEqual(tw.window, GameTimeWindow.STARTING_SOON)
        self.assertTrue(tw.is_actionable)

    def test_today_window(self):
        game = GameEvent(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now() + timedelta(hours=5),
            status=GameEvent.STATUS_SCHEDULED,
        )
        tw = GameTimeWindow(game)
        # May be TODAY or UPCOMING depending on time — just verify it's relevant
        self.assertTrue(tw.is_relevant)

    def test_past_window(self):
        game = GameEvent(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now() - timedelta(hours=4),
            status=GameEvent.STATUS_FINAL,
        )
        tw = GameTimeWindow(game)
        self.assertEqual(tw.window, GameTimeWindow.PAST)

    def test_future_window(self):
        game = GameEvent(
            home_team=self.chiefs, away_team=self.niners,
            start_time=timezone.now() + timedelta(days=7),
            status=GameEvent.STATUS_SCHEDULED,
        )
        tw = GameTimeWindow(game)
        self.assertEqual(tw.window, GameTimeWindow.FUTURE)
        self.assertFalse(tw.is_actionable)
