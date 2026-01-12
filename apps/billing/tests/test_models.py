"""
Tests for billing models.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.billing.models import (
    BillingProfile,
    CreditTransaction,
    FeatureSuggestion,
    FoundingMemberPayout,
    PaymentAuditLog,
    PromoCodeUsage,
    ReferralQualification,
    ReferralReward,
)

User = get_user_model()


class BillingProfileModelTest(TestCase):
    """Test BillingProfile model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            date_of_birth=date(2000, 1, 15),
        )
        # Profile should be auto-created by signal
        self.profile = self.user.billing_profile

    def test_profile_created_on_user_creation(self):
        """BillingProfile should be auto-created when User is created."""
        self.assertIsNotNone(self.profile)
        self.assertEqual(self.profile.user, self.user)

    def test_default_tier_is_free(self):
        """Default pricing tier should be free."""
        self.assertEqual(self.profile.pricing_tier, BillingProfile.TIER_FREE)

    def test_referral_code_generated(self):
        """Referral code should be auto-generated."""
        self.assertIsNotNone(self.profile.referral_code)
        self.assertIn('-', self.profile.referral_code)

    def test_referral_code_uniqueness(self):
        """Referral codes should be unique."""
        user2 = User.objects.create_user(
            email='test2@example.com',
            password='testpass123',
        )
        self.assertNotEqual(
            self.profile.referral_code,
            user2.billing_profile.referral_code
        )

    def test_is_subscribed_property(self):
        """is_subscribed should return True for active subscriptions."""
        self.profile.subscription_status = BillingProfile.STATUS_NONE
        self.assertFalse(self.profile.is_subscribed)

        self.profile.subscription_status = BillingProfile.STATUS_ACTIVE
        self.assertTrue(self.profile.is_subscribed)

        self.profile.subscription_status = BillingProfile.STATUS_LIFETIME
        self.assertTrue(self.profile.is_subscribed)

    def test_is_founding_member_property(self):
        """is_founding_member should return True for founding tier."""
        self.profile.pricing_tier = BillingProfile.TIER_ADULT
        self.assertFalse(self.profile.is_founding_member)

        self.profile.pricing_tier = BillingProfile.TIER_FOUNDING
        self.assertTrue(self.profile.is_founding_member)

    def test_add_credit(self):
        """add_credit should increase balance and create transaction."""
        initial_balance = self.profile.account_credit
        self.profile.add_credit(
            Decimal('5.00'),
            CreditTransaction.TYPE_REFERRAL,
            'Test credit'
        )
        self.profile.refresh_from_db()

        self.assertEqual(
            self.profile.account_credit,
            initial_balance + Decimal('5.00')
        )

        # Check transaction was created
        tx = CreditTransaction.objects.filter(user=self.user).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('5.00'))

    def test_use_credit(self):
        """use_credit should decrease balance and create transaction."""
        self.profile.account_credit = Decimal('10.00')
        self.profile.save()

        self.profile.use_credit(Decimal('3.00'), 'inv_123')
        self.profile.refresh_from_db()

        self.assertEqual(self.profile.account_credit, Decimal('7.00'))

        tx = CreditTransaction.objects.filter(
            user=self.user,
            transaction_type=CreditTransaction.TYPE_APPLIED
        ).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('-3.00'))

    def test_use_credit_insufficient_balance(self):
        """use_credit should raise error if insufficient balance."""
        self.profile.account_credit = Decimal('5.00')
        self.profile.save()

        with self.assertRaises(ValueError):
            self.profile.use_credit(Decimal('10.00'))

    def test_days_until_graduation(self):
        """days_until_graduation should calculate correctly."""
        self.profile.graduation_date = None
        self.assertIsNone(self.profile.days_until_graduation)

        self.profile.graduation_date = timezone.now().date() + timedelta(days=30)
        self.assertEqual(self.profile.days_until_graduation, 30)

        self.profile.graduation_date = timezone.now().date() - timedelta(days=5)
        self.assertEqual(self.profile.days_until_graduation, 0)

    def test_referral_link(self):
        """referral_link should return full URL."""
        link = self.profile.referral_link
        self.assertIn('wholelifejourney.com', link)
        self.assertIn(self.profile.referral_code, link)


class ReferralRewardModelTest(TestCase):
    """Test ReferralReward model."""

    def setUp(self):
        self.referrer = User.objects.create_user(
            email='referrer@example.com',
            password='testpass123',
        )
        self.referred = User.objects.create_user(
            email='referred@example.com',
            password='testpass123',
        )
        self.reward = ReferralReward.objects.create(
            referrer=self.referrer,
            referred_user=self.referred,
            signup_date=timezone.now().date(),
        )

    def test_process_rewards_gives_credit_to_both(self):
        """process_rewards should give $5 to both parties."""
        self.reward.first_payment_date = timezone.now().date()
        self.reward.process_rewards()

        self.assertTrue(self.reward.referrer_reward_given)
        self.assertTrue(self.reward.referred_reward_given)

        referrer_profile = self.referrer.billing_profile
        referred_profile = self.referred.billing_profile

        self.assertEqual(referrer_profile.account_credit, Decimal('5.00'))
        self.assertEqual(referred_profile.account_credit, Decimal('5.00'))

    def test_process_rewards_only_once(self):
        """process_rewards should not double-credit."""
        self.reward.first_payment_date = timezone.now().date()
        self.reward.process_rewards()
        self.reward.process_rewards()  # Call again

        referrer_profile = self.referrer.billing_profile
        self.assertEqual(referrer_profile.account_credit, Decimal('5.00'))


class FeatureSuggestionModelTest(TestCase):
    """Test FeatureSuggestion model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='suggester@example.com',
            password='testpass123',
        )
        self.suggestion = FeatureSuggestion.objects.create(
            user=self.user,
            suggestion_text='Add dark mode',
        )

    def test_default_status(self):
        """Default status should be submitted."""
        self.assertEqual(self.suggestion.status, FeatureSuggestion.STATUS_SUBMITTED)

    def test_mark_implemented_gives_reward(self):
        """mark_implemented should give credit and update status."""
        self.suggestion.mark_implemented()

        self.assertEqual(self.suggestion.status, FeatureSuggestion.STATUS_IMPLEMENTED)
        self.assertTrue(self.suggestion.reward_given)
        self.assertIsNotNone(self.suggestion.implemented_date)

        profile = self.user.billing_profile
        self.assertEqual(profile.account_credit, Decimal('5.00'))

    def test_mark_implemented_only_once(self):
        """mark_implemented should not double-credit."""
        self.suggestion.mark_implemented()
        self.suggestion.mark_implemented()  # Call again

        profile = self.user.billing_profile
        self.assertEqual(profile.account_credit, Decimal('5.00'))


class PaymentAuditLogModelTest(TestCase):
    """Test PaymentAuditLog model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='audit@example.com',
            password='testpass123',
        )

    def test_log_creates_entry(self):
        """log() class method should create audit entry."""
        log = PaymentAuditLog.log(
            action=PaymentAuditLog.ACTION_CHECKOUT_STARTED,
            user=self.user,
            stripe_object_id='cs_test_123',
            details={'price_key': 'adult_monthly'},
        )

        self.assertIsNotNone(log.id)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.action, PaymentAuditLog.ACTION_CHECKOUT_STARTED)
        self.assertEqual(log.details['price_key'], 'adult_monthly')


class CreditTransactionModelTest(TestCase):
    """Test CreditTransaction model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='credit@example.com',
            password='testpass123',
        )

    def test_positive_amount_for_credit(self):
        """Credits earned should have positive amount."""
        tx = CreditTransaction.objects.create(
            user=self.user,
            amount=Decimal('5.00'),
            transaction_type=CreditTransaction.TYPE_REFERRAL,
            description='Referral bonus',
        )
        self.assertGreater(tx.amount, 0)

    def test_negative_amount_for_usage(self):
        """Credits used should have negative amount."""
        tx = CreditTransaction.objects.create(
            user=self.user,
            amount=Decimal('-5.00'),
            transaction_type=CreditTransaction.TYPE_APPLIED,
            description='Applied to invoice',
        )
        self.assertLess(tx.amount, 0)
