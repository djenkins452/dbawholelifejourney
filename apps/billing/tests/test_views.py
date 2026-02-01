"""
Tests for billing views.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.billing.models import BillingProfile, FeatureSuggestion
from apps.users.models import TermsAcceptance

User = get_user_model()

# Common test settings to avoid staticfiles manifest issues
TEST_SETTINGS = {
    'STRIPE_PUBLIC_KEY': 'pk_test_fake',
    'STRIPE_SECRET_KEY': 'sk_test_fake',
    'STORAGES': {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
}


def complete_user_setup(user):
    """Helper to set up user for testing (terms + onboarding)."""
    terms_version = django_settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
    TermsAcceptance.objects.create(user=user, terms_version=terms_version)
    user.preferences.has_completed_onboarding = True
    user.preferences.save()


@override_settings(**TEST_SETTINGS)
class SelectPlanViewTest(TestCase):
    """Test plan selection view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='plan@example.com',
            password='testpass123',
            date_of_birth=date(2000, 1, 15),
        )
        complete_user_setup(self.user)
        self.client.login(email='plan@example.com', password='testpass123')

    def test_select_plan_requires_login(self):
        """select_plan should require authentication."""
        self.client.logout()
        response = self.client.get(reverse('billing:select_plan'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url.lower())

    def test_select_plan_shows_plans(self):
        """select_plan should display plan options."""
        response = self.client.get(reverse('billing:select_plan'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Choose Your Plan')

    def test_select_plan_shows_student_for_young_user(self):
        """select_plan should show student option for users <= 22."""
        self.user.date_of_birth = date.today() - timedelta(days=365 * 20)
        self.user.save()

        response = self.client.get(reverse('billing:select_plan'))
        self.assertEqual(response.status_code, 200)
        # Context should indicate student eligibility
        self.assertTrue(response.context.get('is_student_eligible', False))

    def test_select_plan_captures_promo_code(self):
        """select_plan should capture promo code from URL."""
        response = self.client.get(
            reverse('billing:select_plan') + '?promo=LAUNCH20'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context.get('promo_code'), 'LAUNCH20')


@override_settings(**TEST_SETTINGS)
class BillingSettingsViewTest(TestCase):
    """Test billing settings view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='settings@example.com',
            password='testpass123',
        )
        complete_user_setup(self.user)
        self.profile = self.user.billing_profile
        self.client.login(email='settings@example.com', password='testpass123')

    def test_billing_settings_shows_profile(self):
        """billing_settings should display user's billing profile."""
        response = self.client.get(reverse('billing:billing_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Billing Settings')
        self.assertIn('profile', response.context)

    def test_billing_settings_shows_referral_link(self):
        """billing_settings should show referral link."""
        response = self.client.get(reverse('billing:billing_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.profile.referral_code)


class CaptureReferralViewTest(TestCase):
    """Test referral capture view."""

    def setUp(self):
        self.client = Client()
        self.referrer = User.objects.create_user(
            email='referrer@example.com',
            password='testpass123',
        )
        complete_user_setup(self.referrer)
        self.referrer_profile = self.referrer.billing_profile

    def test_capture_referral_stores_in_session(self):
        """capture_referral should store valid code in session."""
        code = self.referrer_profile.referral_code
        response = self.client.get(
            reverse('billing:capture_referral') + f'?ref={code}'
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.client.session.get('referral_code'),
            code
        )

    def test_capture_referral_invalid_code(self):
        """capture_referral should not store invalid code."""
        response = self.client.get(
            reverse('billing:capture_referral') + '?ref=INVALID123'
        )

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.client.session.get('referral_code'))

    def test_capture_referral_redirects_to_signup(self):
        """capture_referral should redirect to signup page."""
        response = self.client.get(reverse('billing:capture_referral'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('signup', response.url.lower())


@override_settings(**TEST_SETTINGS)
class SubmitSuggestionViewTest(TestCase):
    """Test feature suggestion submission view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='suggest@example.com',
            password='testpass123',
        )
        complete_user_setup(self.user)
        self.client.login(email='suggest@example.com', password='testpass123')

    def test_submit_suggestion_get(self):
        """submit_suggestion GET should show form."""
        response = self.client.get(reverse('billing:submit_suggestion'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Submit a Feature Suggestion')

    def test_submit_suggestion_post(self):
        """submit_suggestion POST should create suggestion."""
        response = self.client.post(
            reverse('billing:submit_suggestion'),
            {
                'suggestion_text': 'Add dark mode please!',
                'public_credit_consent': True,
            }
        )

        self.assertEqual(response.status_code, 302)  # Redirect on success

        suggestion = FeatureSuggestion.objects.filter(user=self.user).first()
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.suggestion_text, 'Add dark mode please!')

    def test_submit_suggestion_rate_limit(self):
        """submit_suggestion should enforce rate limit."""
        # Create 3 suggestions
        for i in range(3):
            FeatureSuggestion.objects.create(
                user=self.user,
                suggestion_text=f'Suggestion {i}',
            )

        response = self.client.get(reverse('billing:submit_suggestion'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context.get('suggestions_remaining'), 0)


@override_settings(**TEST_SETTINGS)
class CreditHistoryViewTest(TestCase):
    """Test credit history view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='credits@example.com',
            password='testpass123',
        )
        complete_user_setup(self.user)
        self.client.login(email='credits@example.com', password='testpass123')

    def test_credit_history_shows_transactions(self):
        """credit_history should display transactions."""
        # Add some credit
        self.user.billing_profile.add_credit(
            Decimal('5.00'),
            'referral_bonus',
            'Test credit'
        )

        response = self.client.get(reverse('billing:credit_history'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Credit History')
        self.assertContains(response, '5.00')


@override_settings(**TEST_SETTINGS)
class PayoutPreferencesViewTest(TestCase):
    """Test payout preferences view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='payout@example.com',
            password='testpass123',
        )
        complete_user_setup(self.user)
        self.profile = self.user.billing_profile
        self.client.login(email='payout@example.com', password='testpass123')

    def test_payout_preferences_non_founding_redirects(self):
        """payout_preferences should redirect non-founding members."""
        self.profile.pricing_tier = BillingProfile.TIER_ADULT
        self.profile.save()

        response = self.client.get(reverse('billing:payout_preferences'))
        self.assertEqual(response.status_code, 302)

    def test_payout_preferences_founding_shows_form(self):
        """payout_preferences should show form for founding members."""
        self.profile.pricing_tier = BillingProfile.TIER_FOUNDING
        self.profile.save()

        response = self.client.get(reverse('billing:payout_preferences'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Payout Preferences')

    def test_payout_preferences_post_saves(self):
        """payout_preferences POST should save preferences."""
        self.profile.pricing_tier = BillingProfile.TIER_FOUNDING
        self.profile.save()

        response = self.client.post(
            reverse('billing:payout_preferences'),
            {
                'payout_method': 'paypal',
                'payout_email': 'pay@example.com',
            }
        )

        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.payout_method, 'paypal')
        self.assertEqual(self.profile.payout_email, 'pay@example.com')
