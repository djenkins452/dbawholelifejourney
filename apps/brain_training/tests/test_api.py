"""
Tests for Brain Training API endpoints.

Tests authentication, subscription checks, and API functionality.
"""

import json
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import BillingProfile
from apps.brain_training.models import Challenge, Game, GameSession
from apps.users.models import TermsAcceptance


User = get_user_model()


class BrainTrainingAPITestCase(TestCase):
    """Base test case with user and subscription setup."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
        )
        # Accept terms of service
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
        )
        # Complete onboarding
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        # Create billing profile with subscription
        BillingProfile.objects.filter(user=self.user).update(
            subscription_status='active',
        )
        # Create a game
        self.game = Game.objects.create(
            slug='sudoku',
            name='Sudoku',
            category='logic',
            difficulty_levels=['easy', 'medium', 'hard', 'expert'],
            default_difficulty='medium',
        )
        # Create a challenge
        self.challenge = Challenge.objects.create(
            game=self.game,
            challenge_id='test123',
            difficulty='medium',
            puzzle_data={'grid': [[0] * 9 for _ in range(9)]},
            solution_data={'grid': [[1] * 9 for _ in range(9)]},
            solution_hash='fakehash',
        )


class HubViewTests(BrainTrainingAPITestCase):
    """Tests for the Brain Training hub page."""

    def test_hub_requires_login(self):
        """Hub page should redirect to login if not authenticated."""
        response = self.client.get(reverse('brain_training:hub'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('accounts/login', response.url)

    def test_hub_requires_subscription(self):
        """Hub page should redirect to billing if no subscription."""
        # Remove subscription and expire trial
        BillingProfile.objects.filter(user=self.user).update(
            subscription_status='canceled',
            trial_ends_at=timezone.now() - timedelta(days=1),
        )
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('brain_training:hub'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('billing', response.url)

    def test_hub_accessible_with_subscription(self):
        """Hub page should be accessible with valid subscription."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('brain_training:hub'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Brain Training')


class BatchAPITests(BrainTrainingAPITestCase):
    """Tests for the challenge batch API."""

    def test_batch_requires_login(self):
        """Batch API should return 302 redirect if not authenticated."""
        url = reverse('brain_training:api_batch', kwargs={'game_slug': 'sudoku'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_batch_returns_challenges(self):
        """Batch API should return challenges for logged-in users."""
        self.client.login(email='test@example.com', password='testpass123')
        url = reverse('brain_training:api_batch', kwargs={'game_slug': 'sudoku'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertIn('challenges', data)
        self.assertIn('game', data)
        self.assertEqual(data['game'], 'sudoku')

    def test_batch_respects_count_param(self):
        """Batch API should respect count parameter (max 20)."""
        # Create more challenges
        for i in range(15):
            Challenge.objects.create(
                game=self.game,
                challenge_id=f'test{i}',
                difficulty='medium',
                puzzle_data={},
                solution_data={},
                solution_hash='hash',
            )

        self.client.login(email='test@example.com', password='testpass123')
        url = reverse('brain_training:api_batch', kwargs={'game_slug': 'sudoku'})

        # Request 5 challenges
        response = self.client.get(f'{url}?count=5')
        data = json.loads(response.content)
        self.assertLessEqual(len(data['challenges']), 5)

        # Request more than max (20)
        response = self.client.get(f'{url}?count=50')
        data = json.loads(response.content)
        self.assertLessEqual(len(data['challenges']), 20)


class SessionAPITests(BrainTrainingAPITestCase):
    """Tests for session start/complete APIs."""

    def test_session_start(self):
        """Session start API should create a new session."""
        self.client.login(email='test@example.com', password='testpass123')

        url = reverse('brain_training:api_session_start')
        response = self.client.post(
            url,
            data=json.dumps({'challenge_id': 'test123'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('session_id', data)

        # Verify session was created
        session = GameSession.objects.get(id=data['session_id'])
        self.assertEqual(session.user, self.user)
        self.assertEqual(session.challenge, self.challenge)
        self.assertEqual(session.status, GameSession.STATUS_IN_PROGRESS)

    def test_session_complete(self):
        """Session complete API should mark session as completed."""
        self.client.login(email='test@example.com', password='testpass123')

        # Start a session
        session = GameSession.objects.create(
            user=self.user,
            challenge=self.challenge,
        )

        url = reverse('brain_training:api_session_complete')
        response = self.client.post(
            url,
            data=json.dumps({
                'session_id': session.id,
                'time_spent': 120,
                'mistakes': 2,
                'hints_used': 1,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

        # Verify session was updated
        session.refresh_from_db()
        self.assertEqual(session.status, GameSession.STATUS_COMPLETED)
        self.assertEqual(session.time_spent_seconds, 120)
        self.assertEqual(session.mistakes, 2)
        self.assertEqual(session.hints_used, 1)


class StatsAPITests(BrainTrainingAPITestCase):
    """Tests for stats API endpoints."""

    def test_stats_overview(self):
        """Stats overview API should return user stats."""
        self.client.login(email='test@example.com', password='testpass123')

        url = reverse('brain_training:api_stats_overview')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('overall', data)
        self.assertIn('games', data)

    def test_stats_game(self):
        """Game stats API should return game-specific stats."""
        self.client.login(email='test@example.com', password='testpass123')

        url = reverse('brain_training:api_stats_game', kwargs={'game_slug': 'sudoku'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['game'], 'sudoku')
        self.assertIn('daily', data)
        self.assertIn('improvement', data)

    def test_ai_summary(self):
        """AI summary API should return compact stats for AI coaching."""
        self.client.login(email='test@example.com', password='testpass123')

        url = reverse('brain_training:api_ai_summary')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('ai_summary', data)
        self.assertIn('timeframe_days', data['ai_summary'])
        self.assertIn('total_sessions', data['ai_summary'])
        self.assertIn('games', data['ai_summary'])
