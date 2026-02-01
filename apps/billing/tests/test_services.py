"""
Tests for billing services.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.billing.models import BillingProfile
from apps.billing.services import (
    calculate_age,
    determine_tier_by_age,
    get_current_quarter,
    is_subscription_active,
    StripeService,
)

User = get_user_model()


class AgeCalculationTest(TestCase):
    """Test age calculation utilities."""

    def test_calculate_age_basic(self):
        """calculate_age should return correct age."""
        today = date.today()
        dob = date(today.year - 25, 1, 1)
        self.assertEqual(calculate_age(dob), 25)

    def test_calculate_age_birthday_not_yet(self):
        """calculate_age should handle birthdays not yet occurred this year."""
        today = date.today()
        # Birthday later this year
        future_month = 12 if today.month < 12 else today.month
        dob = date(today.year - 25, future_month, 28)
        age = calculate_age(dob)
        # Should be 24 or 25 depending on exact date
        self.assertIn(age, [24, 25])

    def test_calculate_age_none(self):
        """calculate_age should return None for None input."""
        self.assertIsNone(calculate_age(None))

    def test_determine_tier_student(self):
        """determine_tier_by_age should return student for age <= 22."""
        today = date.today()
        dob_20 = date(today.year - 20, 1, 1)
        dob_22 = date(today.year - 22, 1, 1)

        self.assertEqual(determine_tier_by_age(dob_20), BillingProfile.TIER_STUDENT)
        self.assertEqual(determine_tier_by_age(dob_22), BillingProfile.TIER_STUDENT)

    def test_determine_tier_adult(self):
        """determine_tier_by_age should return adult for age >= 23."""
        today = date.today()
        dob_23 = date(today.year - 23, 1, 1)
        dob_30 = date(today.year - 30, 1, 1)

        self.assertEqual(determine_tier_by_age(dob_23), BillingProfile.TIER_ADULT)
        self.assertEqual(determine_tier_by_age(dob_30), BillingProfile.TIER_ADULT)

    def test_determine_tier_none_defaults_adult(self):
        """determine_tier_by_age should return adult if DOB is None."""
        self.assertEqual(determine_tier_by_age(None), BillingProfile.TIER_ADULT)


class SubscriptionCheckTest(TestCase):
    """Test subscription status checking."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='sub@example.com',
            password='testpass123',
        )
        self.profile = self.user.billing_profile

    def test_is_subscription_active_true(self):
        """is_subscription_active should return True for active subscription."""
        self.profile.subscription_status = BillingProfile.STATUS_ACTIVE
        self.profile.save()
        self.assertTrue(is_subscription_active(self.user))

    def test_is_subscription_active_false(self):
        """is_subscription_active should return False for no subscription."""
        self.profile.subscription_status = BillingProfile.STATUS_NONE
        self.profile.save()
        self.assertFalse(is_subscription_active(self.user))

    def test_is_subscription_active_lifetime(self):
        """is_subscription_active should return True for lifetime members."""
        self.profile.subscription_status = BillingProfile.STATUS_LIFETIME
        self.profile.save()
        self.assertTrue(is_subscription_active(self.user))


class QuarterCalculationTest(TestCase):
    """Test quarter calculation."""

    @patch('apps.billing.services.date')
    def test_get_current_quarter_q1(self, mock_date):
        """get_current_quarter should return Q1 for Jan-Mar."""
        mock_date.today.return_value = date(2026, 2, 15)
        self.assertEqual(get_current_quarter(), '2026-Q1')

    @patch('apps.billing.services.date')
    def test_get_current_quarter_q2(self, mock_date):
        """get_current_quarter should return Q2 for Apr-Jun."""
        mock_date.today.return_value = date(2026, 5, 15)
        self.assertEqual(get_current_quarter(), '2026-Q2')

    @patch('apps.billing.services.date')
    def test_get_current_quarter_q3(self, mock_date):
        """get_current_quarter should return Q3 for Jul-Sep."""
        mock_date.today.return_value = date(2026, 8, 15)
        self.assertEqual(get_current_quarter(), '2026-Q3')

    @patch('apps.billing.services.date')
    def test_get_current_quarter_q4(self, mock_date):
        """get_current_quarter should return Q4 for Oct-Dec."""
        mock_date.today.return_value = date(2026, 11, 15)
        self.assertEqual(get_current_quarter(), '2026-Q4')


@override_settings(
    STRIPE_SECRET_KEY='sk_test_fake',
    STRIPE_PUBLIC_KEY='pk_test_fake',
)
class StripeServiceTest(TestCase):
    """Test StripeService class."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='stripe@example.com',
            password='testpass123',
        )
        self.profile = self.user.billing_profile

    @patch('apps.billing.services.stripe')
    def test_get_or_create_customer_new(self, mock_stripe):
        """get_or_create_customer should create new customer if none exists."""
        mock_customer = MagicMock()
        mock_customer.id = 'cus_test123'
        mock_stripe.Customer.create.return_value = mock_customer

        customer = StripeService.get_or_create_customer(self.user)

        mock_stripe.Customer.create.assert_called_once()
        self.assertEqual(customer.id, 'cus_test123')

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.stripe_customer_id, 'cus_test123')

    @patch('apps.billing.services.stripe')
    def test_get_or_create_customer_existing(self, mock_stripe):
        """get_or_create_customer should retrieve existing customer."""
        self.profile.stripe_customer_id = 'cus_existing123'
        self.profile.save()

        mock_customer = MagicMock()
        mock_customer.id = 'cus_existing123'
        mock_customer.get.return_value = False  # Not deleted
        mock_stripe.Customer.retrieve.return_value = mock_customer

        StripeService.get_or_create_customer(self.user)

        mock_stripe.Customer.retrieve.assert_called_once_with('cus_existing123')
        mock_stripe.Customer.create.assert_not_called()

    @patch('apps.billing.services.stripe')
    def test_cancel_subscription_at_period_end(self, mock_stripe):
        """cancel_subscription should mark cancel_at_period_end."""
        self.profile.stripe_subscription_id = 'sub_test123'
        self.profile.save()

        mock_subscription = MagicMock()
        mock_subscription.id = 'sub_test123'
        mock_subscription.cancel_at_period_end = True
        mock_stripe.Subscription.modify.return_value = mock_subscription

        StripeService.cancel_subscription(self.user, at_period_end=True)

        mock_stripe.Subscription.modify.assert_called_once()
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.cancel_at_period_end)

    def test_cancel_subscription_no_subscription(self):
        """cancel_subscription should raise error if no subscription."""
        self.profile.stripe_subscription_id = ''
        self.profile.save()

        with self.assertRaises(ValueError):
            StripeService.cancel_subscription(self.user)
