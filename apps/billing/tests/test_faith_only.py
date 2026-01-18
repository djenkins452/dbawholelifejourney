"""
Tests for Faith Only plan functionality.

Tests cover:
- Selecting Faith Only plan
- Access control for Faith Only users
- Dashboard redirect
- Upgrade prompt schedule
- Upgrading from Faith Only to paid subscription
"""

import json
from datetime import date, timedelta
from unittest.mock import patch

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import BillingProfile
from apps.users.models import TermsAcceptance

User = get_user_model()

# Common test settings
TEST_SETTINGS = {
    'STRIPE_PUBLIC_KEY': 'pk_test_fake',
    'STRIPE_SECRET_KEY': 'sk_test_fake',
    'STORAGES': {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
}


def complete_user_setup(user, with_subscription=False):
    """Helper to set up user for testing (terms + onboarding)."""
    terms_version = django_settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
    TermsAcceptance.objects.create(user=user, terms_version=terms_version)
    user.preferences.has_completed_onboarding = True
    user.preferences.faith_enabled = True
    user.preferences.save()

    if with_subscription:
        profile = user.billing_profile
        profile.subscription_status = BillingProfile.STATUS_ACTIVE
        profile.pricing_tier = BillingProfile.TIER_ADULT
        profile.save()


@override_settings(**TEST_SETTINGS)
class FaithOnlySelectionTest(TestCase):
    """Test selecting the Faith Only plan."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='faith@example.com',
            password='testpass123',
            date_of_birth=date(1990, 1, 15),
        )
        complete_user_setup(self.user)
        self.client.login(email='faith@example.com', password='testpass123')

    def test_select_faith_only_sets_correct_tier(self):
        """Selecting Faith Only should set TIER_FAITH_ONLY."""
        response = self.client.post(reverse('billing:select_faith_only'))

        self.user.billing_profile.refresh_from_db()
        self.assertEqual(
            self.user.billing_profile.pricing_tier,
            BillingProfile.TIER_FAITH_ONLY
        )

    def test_select_faith_only_sets_correct_status(self):
        """Selecting Faith Only should set STATUS_FAITH_ONLY."""
        response = self.client.post(reverse('billing:select_faith_only'))

        self.user.billing_profile.refresh_from_db()
        self.assertEqual(
            self.user.billing_profile.subscription_status,
            BillingProfile.STATUS_FAITH_ONLY
        )

    def test_select_faith_only_records_selection_date(self):
        """Selecting Faith Only should record faith_only_selected_at."""
        before = timezone.now()
        response = self.client.post(reverse('billing:select_faith_only'))
        after = timezone.now()

        self.user.preferences.refresh_from_db()
        self.assertIsNotNone(self.user.preferences.faith_only_selected_at)
        self.assertGreaterEqual(
            self.user.preferences.faith_only_selected_at,
            before
        )
        self.assertLessEqual(
            self.user.preferences.faith_only_selected_at,
            after
        )

    def test_select_faith_only_redirects_to_faith_home(self):
        """Selecting Faith Only should redirect to Faith Home."""
        response = self.client.post(reverse('billing:select_faith_only'))
        self.assertRedirects(response, reverse('faith:home'))

    def test_select_faith_only_requires_post(self):
        """select_faith_only should require POST method."""
        response = self.client.get(reverse('billing:select_faith_only'))
        self.assertEqual(response.status_code, 405)  # Method Not Allowed


@override_settings(**TEST_SETTINGS)
class FaithOnlyAccessControlTest(TestCase):
    """Test access control for Faith Only users."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='faithaccess@example.com',
            password='testpass123',
            date_of_birth=date(1990, 1, 15),
        )
        complete_user_setup(self.user)

        # Set up as Faith Only user
        profile = self.user.billing_profile
        profile.pricing_tier = BillingProfile.TIER_FAITH_ONLY
        profile.subscription_status = BillingProfile.STATUS_FAITH_ONLY
        profile.trial_ends_at = timezone.now() - timedelta(days=1)  # Trial expired
        profile.save()

        self.client.login(email='faithaccess@example.com', password='testpass123')

    def test_faith_only_user_can_access_faith_home(self):
        """Faith Only users should access Faith Home."""
        response = self.client.get(reverse('faith:home'))
        self.assertEqual(response.status_code, 200)

    def test_faith_only_user_can_access_faith_prayers(self):
        """Faith Only users should access Faith prayers."""
        response = self.client.get(reverse('faith:prayer_list'))
        self.assertEqual(response.status_code, 200)

    def test_faith_only_user_blocked_from_journal(self):
        """Faith Only users should be blocked from Journal."""
        response = self.client.get(reverse('journal:home'))
        self.assertRedirects(response, reverse('billing:faith_only_upgrade'))

    def test_faith_only_user_blocked_from_health(self):
        """Faith Only users should be blocked from Health."""
        response = self.client.get(reverse('health:home'))
        self.assertRedirects(response, reverse('billing:faith_only_upgrade'))

    def test_faith_only_user_blocked_from_dashboard(self):
        """Faith Only users should be blocked from Dashboard (middleware catches first)."""
        response = self.client.get(reverse('dashboard:home'))
        # Middleware intercepts before view and redirects to upgrade page
        self.assertRedirects(response, reverse('billing:faith_only_upgrade'))


@override_settings(**TEST_SETTINGS)
class FaithOnlyUpgradePageTest(TestCase):
    """Test the Faith Only upgrade page."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='upgrade@example.com',
            password='testpass123',
            date_of_birth=date(1990, 1, 15),
        )
        complete_user_setup(self.user)

        # Set up as Faith Only user with expired trial
        profile = self.user.billing_profile
        profile.pricing_tier = BillingProfile.TIER_FAITH_ONLY
        profile.subscription_status = BillingProfile.STATUS_FAITH_ONLY
        profile.trial_ends_at = timezone.now() - timedelta(days=1)  # Trial expired
        profile.save()

        self.client.login(email='upgrade@example.com', password='testpass123')

    def test_faith_only_upgrade_shows_for_faith_only_users(self):
        """faith_only_upgrade should show for Faith Only users."""
        response = self.client.get(reverse('billing:faith_only_upgrade'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Faith Only")

    def test_faith_only_upgrade_redirects_subscribed_users(self):
        """faith_only_upgrade should redirect subscribed users to dashboard."""
        profile = self.user.billing_profile
        profile.pricing_tier = BillingProfile.TIER_ADULT
        profile.subscription_status = BillingProfile.STATUS_ACTIVE
        profile.save()

        response = self.client.get(reverse('billing:faith_only_upgrade'))
        self.assertRedirects(response, reverse('dashboard:home'))


@override_settings(**TEST_SETTINGS)
class FaithOnlyUpgradePromptTest(TestCase):
    """Test upgrade prompt schedule for Faith Only users."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='prompt@example.com',
            password='testpass123',
            date_of_birth=date(1990, 1, 15),
        )
        complete_user_setup(self.user)

        # Set up as Faith Only user
        profile = self.user.billing_profile
        profile.pricing_tier = BillingProfile.TIER_FAITH_ONLY
        profile.subscription_status = BillingProfile.STATUS_FAITH_ONLY
        profile.save()

        self.client.login(email='prompt@example.com', password='testpass123')

    def test_no_prompt_before_week1(self):
        """No upgrade prompt should show in first 7 days."""
        prefs = self.user.preferences
        prefs.faith_only_selected_at = timezone.now() - timedelta(days=3)
        prefs.save()

        response = self.client.get(reverse('billing:faith_upgrade_check'))
        data = response.json()

        self.assertFalse(data['should_show'])

    def test_week1_prompt_shows_at_day_7(self):
        """Week 1 prompt should show after day 7."""
        prefs = self.user.preferences
        prefs.faith_only_selected_at = timezone.now() - timedelta(days=8)
        prefs.save()

        response = self.client.get(reverse('billing:faith_upgrade_check'))
        data = response.json()

        self.assertTrue(data['should_show'])
        self.assertEqual(data['prompt_type'], 'week1')

    def test_week1_prompt_not_shown_twice(self):
        """Week 1 prompt should not show if already shown."""
        prefs = self.user.preferences
        prefs.faith_only_selected_at = timezone.now() - timedelta(days=8)
        prefs.faith_only_upgrade_week1_shown = True
        prefs.save()

        response = self.client.get(reverse('billing:faith_upgrade_check'))
        data = response.json()

        self.assertFalse(data['should_show'])

    def test_month2_prompt_shows_at_day_30(self):
        """Month 2 prompt should show after day 30."""
        prefs = self.user.preferences
        prefs.faith_only_selected_at = timezone.now() - timedelta(days=35)
        prefs.faith_only_upgrade_week1_shown = True  # Week 1 already shown
        prefs.save()

        response = self.client.get(reverse('billing:faith_upgrade_check'))
        data = response.json()

        self.assertTrue(data['should_show'])
        self.assertEqual(data['prompt_type'], 'month2')

    def test_month3_prompt_shows_at_day_60(self):
        """Month 3 (final) prompt should show after day 60."""
        prefs = self.user.preferences
        prefs.faith_only_selected_at = timezone.now() - timedelta(days=65)
        prefs.faith_only_upgrade_week1_shown = True
        prefs.faith_only_upgrade_month2_shown = True
        prefs.save()

        response = self.client.get(reverse('billing:faith_upgrade_check'))
        data = response.json()

        self.assertTrue(data['should_show'])
        self.assertEqual(data['prompt_type'], 'month3')

    def test_no_prompts_after_day_75(self):
        """No prompts should show after day 75 (even if not all shown)."""
        prefs = self.user.preferences
        prefs.faith_only_selected_at = timezone.now() - timedelta(days=80)
        prefs.faith_only_upgrade_week1_shown = True
        prefs.faith_only_upgrade_month2_shown = True
        prefs.faith_only_upgrade_month3_shown = True
        prefs.save()

        response = self.client.get(reverse('billing:faith_upgrade_check'))
        data = response.json()

        self.assertFalse(data['should_show'])

    def test_dismiss_records_week1_shown(self):
        """Dismissing week1 prompt should record it."""
        prefs = self.user.preferences
        prefs.faith_only_selected_at = timezone.now() - timedelta(days=8)
        prefs.save()

        response = self.client.post(
            reverse('billing:faith_upgrade_dismiss'),
            data=json.dumps({'prompt_type': 'week1'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)

        prefs.refresh_from_db()
        self.assertTrue(prefs.faith_only_upgrade_week1_shown)
        self.assertIsNotNone(prefs.faith_only_upgrade_week1_shown_at)


@override_settings(**TEST_SETTINGS)
class FaithOnlyModelPropertiesTest(TestCase):
    """Test BillingProfile properties for Faith Only."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='model@example.com',
            password='testpass123',
        )
        self.profile = self.user.billing_profile

    def test_is_faith_only_true_for_faith_only_tier(self):
        """is_faith_only should return True for TIER_FAITH_ONLY."""
        self.profile.pricing_tier = BillingProfile.TIER_FAITH_ONLY
        self.assertTrue(self.profile.is_faith_only)

    def test_is_faith_only_false_for_other_tiers(self):
        """is_faith_only should return False for other tiers."""
        for tier in [BillingProfile.TIER_FREE, BillingProfile.TIER_STUDENT,
                     BillingProfile.TIER_ADULT, BillingProfile.TIER_FOUNDING]:
            self.profile.pricing_tier = tier
            self.assertFalse(self.profile.is_faith_only)

    def test_has_faith_access_true_for_faith_only(self):
        """has_faith_access should return True for Faith Only users."""
        self.profile.pricing_tier = BillingProfile.TIER_FAITH_ONLY
        self.profile.subscription_status = BillingProfile.STATUS_FAITH_ONLY
        self.assertTrue(self.profile.has_faith_access)

    def test_has_faith_access_true_for_subscribed(self):
        """has_faith_access should return True for subscribed users."""
        self.profile.subscription_status = BillingProfile.STATUS_ACTIVE
        self.assertTrue(self.profile.has_faith_access)

    def test_has_access_false_for_faith_only(self):
        """has_access (full access) should return False for Faith Only users."""
        self.profile.pricing_tier = BillingProfile.TIER_FAITH_ONLY
        self.profile.subscription_status = BillingProfile.STATUS_FAITH_ONLY
        self.profile.trial_ends_at = timezone.now() - timedelta(days=1)
        self.assertFalse(self.profile.has_access)
