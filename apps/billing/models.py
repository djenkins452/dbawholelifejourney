"""
Whole Life Journey - Billing Models

Project: Whole Life Journey
Path: apps/billing/models.py
Purpose: Subscription, payment, referral, and rewards models

Description:
    This module defines all billing-related models for the WLJ payment system.
    It handles subscription tiers, Stripe integration, referral tracking,
    account credits, feature suggestions, and Founding Member payouts.

Key Models:
    - BillingProfile: User's billing information and subscription status
    - ReferralReward: Tracks referral signups and reward distribution
    - ReferralQualification: Tracks 90-day qualification for Founding Member bonuses
    - FoundingMemberPayout: Quarterly payout records for Founding Members
    - FeatureSuggestion: User-submitted feature ideas with rewards
    - CreditTransaction: Account credit ledger
    - PromoCodeUsage: Tracks promo code redemptions

Design Notes:
    - Uses dj-stripe for Stripe data sync, these models extend with WLJ-specific logic
    - Soft deletes via TimeStampedModel for audit trails
    - All monetary amounts stored as Decimal for precision

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import secrets
import string
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class BillingConfiguration(models.Model):
    """
    Singleton model for billing configuration.

    Stores all pricing, rewards, and threshold configuration in the database.
    Managed via Django Admin for easy updates without code changes.

    Only one record should exist - use get_config() class method to access.
    """

    # Business Info
    business_name = models.CharField(
        max_length=100,
        default='Beacon Innovation LLC',
        help_text="Business entity name",
    )
    product_name = models.CharField(
        max_length=100,
        default='Whole Life Journey',
        help_text="Product name",
    )

    # Age Thresholds
    student_max_age = models.PositiveIntegerField(
        default=22,
        help_text="Maximum age for student pricing (age X and under)",
    )

    # Student Pricing
    student_monthly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('4.99'),
        help_text="Student monthly subscription price",
    )
    student_annual_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('49.00'),
        help_text="Student annual subscription price",
    )

    # Adult Pricing
    adult_monthly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('7.99'),
        help_text="Adult monthly subscription price",
    )
    adult_annual_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('79.00'),
        help_text="Adult annual subscription price",
    )

    # Founding Member Pricing
    founding_lifetime_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('59.00'),
        help_text="Founding Member lifetime one-time price",
    )
    founding_quarterly_bonus = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('5.00'),
        help_text="Quarterly bonus per qualified referral for Founding Members",
    )

    # Rewards
    referral_bonus = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('5.00'),
        help_text="Referral bonus - both referrer and referred user receive this",
    )
    suggestion_reward = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('5.00'),
        help_text="Reward for implemented feature suggestions",
    )
    suggestions_per_month_limit = models.PositiveIntegerField(
        default=3,
        help_text="Maximum feature suggestions per user per month",
    )
    referral_qualification_days = models.PositiveIntegerField(
        default=90,
        help_text="Days a referred user must stay subscribed for Founding Member bonus",
    )

    # Stripe Fees (for documentation/calculations)
    stripe_fee_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('2.9'),
        help_text="Stripe fee percentage (e.g., 2.9 for 2.9%)",
    )
    stripe_fee_flat = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.30'),
        help_text="Stripe flat fee per transaction",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Billing Configuration"
        verbose_name_plural = "Billing Configuration"

    def __str__(self):
        return f"Billing Configuration (Updated: {self.updated_at.strftime('%Y-%m-%d %H:%M')})"

    def save(self, *args, **kwargs):
        """Ensure only one configuration exists (singleton)."""
        if not self.pk and BillingConfiguration.objects.exists():
            # Update existing record instead of creating new one
            existing = BillingConfiguration.objects.first()
            self.pk = existing.pk
        super().save(*args, **kwargs)

    @classmethod
    def get_config(cls):
        """
        Get the billing configuration singleton.

        Creates default configuration if none exists.
        Uses caching to minimize database hits.
        """
        from django.core.cache import cache

        cache_key = 'billing_configuration'
        config = cache.get(cache_key)

        if config is None:
            config, _ = cls.objects.get_or_create(pk=1)
            cache.set(cache_key, config, timeout=300)  # Cache for 5 minutes

        return config

    @classmethod
    def invalidate_cache(cls):
        """Invalidate the configuration cache."""
        from django.core.cache import cache
        cache.delete('billing_configuration')

    def as_dict(self):
        """
        Return configuration as a dictionary.

        Useful for templates and documentation generation.
        """
        return {
            'business_name': self.business_name,
            'product_name': self.product_name,
            'student_max_age': self.student_max_age,
            'adult_min_age': self.student_max_age + 1,
            'student': {
                'name': 'Student',
                'monthly_price': self.student_monthly_price,
                'annual_price': self.student_annual_price,
                'annual_savings_percent': self._calculate_savings(
                    self.student_monthly_price, self.student_annual_price
                ),
                'description': f'For students age {self.student_max_age} and under',
            },
            'adult': {
                'name': 'Adult',
                'monthly_price': self.adult_monthly_price,
                'annual_price': self.adult_annual_price,
                'annual_savings_percent': self._calculate_savings(
                    self.adult_monthly_price, self.adult_annual_price
                ),
                'description': f'For adults age {self.student_max_age + 1} and over',
            },
            'founding': {
                'name': 'Founding Member',
                'lifetime_price': self.founding_lifetime_price,
                'quarterly_bonus_per_referral': self.founding_quarterly_bonus,
                'description': 'Lifetime access with quarterly referral bonuses',
            },
            'rewards': {
                'referral_bonus': self.referral_bonus,
                'suggestion_reward': self.suggestion_reward,
                'suggestions_per_month_limit': self.suggestions_per_month_limit,
                'referral_qualification_days': self.referral_qualification_days,
            },
            'stripe_fees': {
                'percentage': self.stripe_fee_percentage,
                'flat_fee': self.stripe_fee_flat,
            },
        }

    def _calculate_savings(self, monthly_price, annual_price):
        """Calculate annual savings percentage vs monthly billing."""
        monthly_total = monthly_price * 12
        if monthly_total == 0:
            return 0
        savings = ((monthly_total - annual_price) / monthly_total) * 100
        return round(savings)


def get_reward_amount(reward_type):
    """
    Get reward amount from database configuration.

    Args:
        reward_type: 'referral_bonus' or 'suggestion_reward'

    Returns:
        Decimal amount (defaults to 5.00 if not configured)
    """
    try:
        config = BillingConfiguration.get_config()
        if reward_type == 'referral_bonus':
            return config.referral_bonus
        elif reward_type == 'suggestion_reward':
            return config.suggestion_reward
        else:
            return Decimal('5.00')
    except Exception:
        # Fallback if database not available
        return Decimal('5.00')


class BillingProfile(TimeStampedModel):
    """
    User's billing profile with subscription and payment information.

    Extends User with billing-specific fields. Created automatically
    when a user is created via signal.
    """

    # Pricing tier choices
    TIER_FREE = 'free'
    TIER_STUDENT = 'student'
    TIER_ADULT = 'adult'
    TIER_FOUNDING = 'founding'

    TIER_CHOICES = [
        (TIER_FREE, 'Free'),
        (TIER_STUDENT, 'Student ($3.99/mo)'),
        (TIER_ADULT, 'Adult ($7.99/mo)'),
        (TIER_FOUNDING, 'Founding Member (Lifetime)'),
    ]

    # Subscription status choices
    STATUS_NONE = 'none'
    STATUS_TRIALING = 'trialing'
    STATUS_ACTIVE = 'active'
    STATUS_PAST_DUE = 'past_due'
    STATUS_CANCELED = 'canceled'
    STATUS_LIFETIME = 'lifetime'

    STATUS_CHOICES = [
        (STATUS_NONE, 'No Subscription'),
        (STATUS_TRIALING, 'Trialing'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PAST_DUE, 'Past Due'),
        (STATUS_CANCELED, 'Canceled'),
        (STATUS_LIFETIME, 'Lifetime (Founding Member)'),
    ]

    # Billing cycle choices
    CYCLE_MONTHLY = 'monthly'
    CYCLE_ANNUAL = 'annual'
    CYCLE_LIFETIME = 'lifetime'

    CYCLE_CHOICES = [
        (CYCLE_MONTHLY, 'Monthly'),
        (CYCLE_ANNUAL, 'Annual'),
        (CYCLE_LIFETIME, 'Lifetime'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='billing_profile',
    )

    # Pricing tier
    pricing_tier = models.CharField(
        max_length=20,
        choices=TIER_CHOICES,
        default=TIER_FREE,
        help_text="User's current pricing tier",
    )
    tier_locked_until = models.DateField(
        null=True,
        blank=True,
        help_text="Tier cannot change until this date (for gift year, etc.)",
    )
    graduation_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date when student tier graduates to adult tier",
    )

    # Stripe integration
    stripe_customer_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Stripe Customer ID (cus_xxx)",
    )
    stripe_subscription_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Active Stripe Subscription ID (sub_xxx)",
    )

    # Subscription status
    subscription_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NONE,
        help_text="Current subscription status",
    )
    billing_cycle = models.CharField(
        max_length=20,
        choices=CYCLE_CHOICES,
        blank=True,
        help_text="Current billing cycle",
    )
    current_period_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Start of current billing period",
    )
    current_period_end = models.DateTimeField(
        null=True,
        blank=True,
        help_text="End of current billing period (next billing date)",
    )
    cancel_at_period_end = models.BooleanField(
        default=False,
        help_text="Subscription will cancel at end of current period",
    )

    # Referral system
    referral_code = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        help_text="User's unique referral code",
    )
    referred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referrals_made',
        help_text="User who referred this user",
    )

    # Account credits
    account_credit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Available account credit balance",
    )

    # Founding Member payout preferences
    PAYOUT_PAYPAL = 'paypal'
    PAYOUT_VENMO = 'venmo'
    PAYOUT_ZELLE = 'zelle'
    PAYOUT_BANK = 'bank'

    PAYOUT_METHOD_CHOICES = [
        (PAYOUT_PAYPAL, 'PayPal'),
        (PAYOUT_VENMO, 'Venmo'),
        (PAYOUT_ZELLE, 'Zelle'),
        (PAYOUT_BANK, 'Bank Transfer'),
    ]

    payout_method = models.CharField(
        max_length=20,
        choices=PAYOUT_METHOD_CHOICES,
        blank=True,
        help_text="Preferred payout method (Founding Members only)",
    )
    payout_email = models.EmailField(
        blank=True,
        help_text="Email for PayPal/Venmo payouts",
    )
    payout_phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Phone for Zelle payouts",
    )
    payout_bank_info = models.TextField(
        blank=True,
        help_text="Bank details for direct deposit (encrypted in production)",
    )

    class Meta:
        verbose_name = "Billing Profile"
        verbose_name_plural = "Billing Profiles"

    def __str__(self):
        return f"{self.user.email} - {self.get_pricing_tier_display()}"

    def save(self, *args, **kwargs):
        # Generate referral code if not set
        if not self.referral_code:
            self.referral_code = self.generate_referral_code()
        super().save(*args, **kwargs)

    def generate_referral_code(self):
        """Generate a unique referral code based on user's name."""
        # Get first name or email prefix
        if self.user.first_name:
            base = self.user.first_name.upper()[:6]
        else:
            base = self.user.email.split('@')[0].upper()[:6]

        # Add random suffix
        suffix = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
        code = f"{base}-{suffix}"

        # Ensure uniqueness
        while BillingProfile.objects.filter(referral_code=code).exists():
            suffix = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
            code = f"{base}-{suffix}"

        return code

    @property
    def is_subscribed(self):
        """Check if user has an active subscription."""
        return self.subscription_status in [
            self.STATUS_ACTIVE,
            self.STATUS_TRIALING,
            self.STATUS_LIFETIME,
        ]

    @property
    def is_founding_member(self):
        """Check if user is a Founding Member."""
        return self.pricing_tier == self.TIER_FOUNDING

    @property
    def is_student(self):
        """Check if user is on Student tier."""
        return self.pricing_tier == self.TIER_STUDENT

    @property
    def days_until_graduation(self):
        """Days until student graduates to adult tier."""
        if not self.graduation_date:
            return None
        today = timezone.now().date()
        if self.graduation_date <= today:
            return 0
        return (self.graduation_date - today).days

    @property
    def referral_link(self):
        """Get the full referral link URL."""
        return f"https://wholelifejourney.com/join?ref={self.referral_code}"

    def add_credit(self, amount, transaction_type, description):
        """Add credit to account and log transaction."""
        self.account_credit += Decimal(str(amount))
        self.save(update_fields=['account_credit', 'updated_at'])

        CreditTransaction.objects.create(
            user=self.user,
            amount=Decimal(str(amount)),
            transaction_type=transaction_type,
            description=description,
        )

    def use_credit(self, amount, invoice_id=None):
        """Use credit from account and log transaction."""
        amount = Decimal(str(amount))
        if amount > self.account_credit:
            raise ValueError("Insufficient credit balance")

        self.account_credit -= amount
        self.save(update_fields=['account_credit', 'updated_at'])

        CreditTransaction.objects.create(
            user=self.user,
            amount=-amount,  # Negative for usage
            transaction_type=CreditTransaction.TYPE_APPLIED,
            description=f"Applied to invoice {invoice_id}" if invoice_id else "Credit applied",
            related_invoice=invoice_id or '',
        )


class ReferralReward(TimeStampedModel):
    """
    Track referral signups and reward distribution.

    Created when someone signs up using a referral code.
    Rewards are given when the referred user makes their first payment.
    """

    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referral_rewards_given',
        help_text="User who made the referral",
    )
    referred_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referral_rewards_received',
        help_text="User who was referred",
    )
    signup_date = models.DateField(
        help_text="Date the referred user signed up",
    )
    first_payment_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of referred user's first payment",
    )
    referrer_reward_given = models.BooleanField(
        default=False,
        help_text="$5 credit given to referrer",
    )
    referred_reward_given = models.BooleanField(
        default=False,
        help_text="$5 credit given to referred user",
    )

    class Meta:
        verbose_name = "Referral Reward"
        verbose_name_plural = "Referral Rewards"
        unique_together = ['referrer', 'referred_user']

    def __str__(self):
        return f"{self.referrer.email} referred {self.referred_user.email}"

    def process_rewards(self):
        """
        Process rewards for both parties after first payment.

        Called by webhook when invoice.paid event fires for a referred user.
        Uses BILLING_CONFIG for reward amounts.
        """
        referral_bonus = get_reward_amount('referral_bonus')

        if self.first_payment_date and not self.referrer_reward_given:
            # Give referrer credit from config
            referrer_profile = self.referrer.billing_profile
            referrer_profile.add_credit(
                referral_bonus,
                CreditTransaction.TYPE_REFERRAL,
                f"Referral bonus: {self.referred_user.first_name or self.referred_user.email} subscribed"
            )
            self.referrer_reward_given = True

        if self.first_payment_date and not self.referred_reward_given:
            # Give referred user credit from config
            referred_profile = self.referred_user.billing_profile
            referred_profile.add_credit(
                referral_bonus,
                CreditTransaction.TYPE_REFERRAL,
                "Welcome bonus: Thanks for joining via referral!"
            )
            self.referred_reward_given = True

        self.save()


class ReferralQualification(TimeStampedModel):
    """
    Track 90-day qualification period for Founding Member quarterly bonuses.

    Founding Members earn $5 per referral who stays subscribed for 3 months.
    This model tracks when referrals hit that qualification threshold.
    """

    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referral_qualifications',
        help_text="The Founding Member who made the referral",
    )
    referred_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='qualification_records',
        help_text="The referred user being tracked",
    )
    signup_date = models.DateField(
        help_text="When the referred user signed up",
    )
    qualified_date = models.DateField(
        help_text="Date when 90 days is reached (signup_date + 90)",
    )
    bonus_eligible = models.BooleanField(
        default=False,
        help_text="True if user stayed subscribed for 90 days",
    )
    bonus_paid = models.BooleanField(
        default=False,
        help_text="True if Founding Member bonus was paid",
    )
    quarter_applied = models.CharField(
        max_length=10,
        blank=True,
        help_text="Quarter when bonus was applied (e.g., 2026-Q1)",
    )

    class Meta:
        verbose_name = "Referral Qualification"
        verbose_name_plural = "Referral Qualifications"
        unique_together = ['referrer', 'referred_user']

    def __str__(self):
        status = "Qualified" if self.bonus_eligible else "Pending"
        return f"{self.referrer.email} -> {self.referred_user.email}: {status}"


class FoundingMemberPayout(TimeStampedModel):
    """
    Quarterly payout records for Founding Members.

    Each quarter, Founding Members earn $5 per qualified referral.
    This tracks the payout amount and status.
    """

    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_CANCELED = 'canceled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PAID, 'Paid'),
        (STATUS_CANCELED, 'Canceled'),
    ]

    founding_member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='founding_payouts',
        help_text="The Founding Member receiving the payout",
    )
    quarter = models.CharField(
        max_length=10,
        help_text="Quarter (e.g., 2026-Q1)",
    )
    qualifying_referrals = models.PositiveIntegerField(
        default=0,
        help_text="Number of referrals that qualified this quarter",
    )
    payout_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total payout amount ($5 per qualified referral)",
    )
    payout_method = models.CharField(
        max_length=20,
        choices=BillingProfile.PAYOUT_METHOD_CHOICES,
        blank=True,
        help_text="Method used for this payout",
    )
    payout_reference = models.CharField(
        max_length=255,
        blank=True,
        help_text="Transaction ID or confirmation number",
    )
    paid_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the payout was sent",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    notes = models.TextField(
        blank=True,
        help_text="Admin notes about this payout",
    )

    class Meta:
        verbose_name = "Founding Member Payout"
        verbose_name_plural = "Founding Member Payouts"
        unique_together = ['founding_member', 'quarter']
        ordering = ['-quarter', 'founding_member__email']

    def __str__(self):
        return f"{self.founding_member.email} - {self.quarter}: ${self.payout_amount}"


class FeatureSuggestion(TimeStampedModel):
    """
    User-submitted feature suggestions with reward tracking.

    Users can submit feature ideas. If implemented, they earn $5 credit.
    """

    STATUS_SUBMITTED = 'submitted'
    STATUS_REVIEWING = 'reviewing'
    STATUS_PLANNED = 'planned'
    STATUS_IMPLEMENTED = 'implemented'
    STATUS_DECLINED = 'declined'

    STATUS_CHOICES = [
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_REVIEWING, 'Under Review'),
        (STATUS_PLANNED, 'Planned'),
        (STATUS_IMPLEMENTED, 'Implemented'),
        (STATUS_DECLINED, 'Declined'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feature_suggestions',
    )
    suggestion_text = models.TextField(
        help_text="The user's feature suggestion",
    )
    submitted_date = models.DateField(
        auto_now_add=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_SUBMITTED,
    )
    implemented_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the feature was implemented",
    )
    reward_given = models.BooleanField(
        default=False,
        help_text="$5 credit given for implemented suggestion",
    )
    reward_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('5.00'),
        help_text="Reward amount (default $5)",
    )
    public_credit_consent = models.BooleanField(
        default=False,
        help_text="User consents to public credit for the suggestion",
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Internal notes about this suggestion",
    )

    class Meta:
        verbose_name = "Feature Suggestion"
        verbose_name_plural = "Feature Suggestions"
        ordering = ['-submitted_date']

    def __str__(self):
        return f"{self.user.email}: {self.suggestion_text[:50]}..."

    def save(self, *args, **kwargs):
        """Set default reward amount from config on first save."""
        if not self.pk and self.reward_amount == Decimal('5.00'):
            # New record - set reward from config
            self.reward_amount = get_reward_amount('suggestion_reward')
        super().save(*args, **kwargs)

    def mark_implemented(self):
        """Mark as implemented and give reward."""
        self.status = self.STATUS_IMPLEMENTED
        self.implemented_date = timezone.now().date()

        if not self.reward_given:
            profile = self.user.billing_profile
            profile.add_credit(
                self.reward_amount,
                CreditTransaction.TYPE_SUGGESTION,
                "Feature suggestion implemented - thank you!"
            )
            self.reward_given = True

        self.save()


class CreditTransaction(TimeStampedModel):
    """
    Ledger of all account credit transactions.

    Tracks credits earned (positive) and used (negative).
    """

    TYPE_REFERRAL = 'referral_bonus'
    TYPE_SUGGESTION = 'suggestion_reward'
    TYPE_MANUAL = 'manual'
    TYPE_APPLIED = 'applied_to_invoice'
    TYPE_PROMO = 'promo_code'
    TYPE_REFUND = 'refund'

    TYPE_CHOICES = [
        (TYPE_REFERRAL, 'Referral Bonus'),
        (TYPE_SUGGESTION, 'Suggestion Reward'),
        (TYPE_MANUAL, 'Manual Adjustment'),
        (TYPE_APPLIED, 'Applied to Invoice'),
        (TYPE_PROMO, 'Promo Code'),
        (TYPE_REFUND, 'Refund'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='credit_transactions',
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Positive for credits earned, negative for credits used",
    )
    transaction_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
    )
    description = models.TextField(
        help_text="Description of the transaction",
    )
    related_invoice = models.CharField(
        max_length=255,
        blank=True,
        help_text="Stripe invoice ID if applied to payment",
    )

    class Meta:
        verbose_name = "Credit Transaction"
        verbose_name_plural = "Credit Transactions"
        ordering = ['-created_at']

    def __str__(self):
        sign = '+' if self.amount >= 0 else ''
        return f"{self.user.email}: {sign}${self.amount} ({self.get_transaction_type_display()})"


class PromoCodeUsage(TimeStampedModel):
    """
    Track promo code redemptions.

    Links to Stripe coupons but stores local usage data.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='promo_usages',
    )
    code = models.CharField(
        max_length=50,
        help_text="The promo code that was used",
    )
    stripe_coupon_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Stripe Coupon ID",
    )
    applied_date = models.DateField(
        auto_now_add=True,
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fixed discount amount (if applicable)",
    )
    discount_percent = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Percentage discount (if applicable)",
    )

    class Meta:
        verbose_name = "Promo Code Usage"
        verbose_name_plural = "Promo Code Usages"
        ordering = ['-applied_date']

    def __str__(self):
        return f"{self.user.email} used {self.code} on {self.applied_date}"


class PaymentAuditLog(models.Model):
    """
    Audit log for all payment-related actions.

    Immutable record for compliance and debugging.
    """

    ACTION_CHECKOUT_STARTED = 'checkout_started'
    ACTION_CHECKOUT_COMPLETED = 'checkout_completed'
    ACTION_PAYMENT_SUCCESS = 'payment_success'
    ACTION_PAYMENT_FAILED = 'payment_failed'
    ACTION_SUBSCRIPTION_CREATED = 'subscription_created'
    ACTION_SUBSCRIPTION_UPDATED = 'subscription_updated'
    ACTION_SUBSCRIPTION_CANCELED = 'subscription_canceled'
    ACTION_REFUND_ISSUED = 'refund_issued'
    ACTION_CREDIT_ADDED = 'credit_added'
    ACTION_CREDIT_USED = 'credit_used'
    ACTION_WEBHOOK_RECEIVED = 'webhook_received'

    ACTION_CHOICES = [
        (ACTION_CHECKOUT_STARTED, 'Checkout Started'),
        (ACTION_CHECKOUT_COMPLETED, 'Checkout Completed'),
        (ACTION_PAYMENT_SUCCESS, 'Payment Success'),
        (ACTION_PAYMENT_FAILED, 'Payment Failed'),
        (ACTION_SUBSCRIPTION_CREATED, 'Subscription Created'),
        (ACTION_SUBSCRIPTION_UPDATED, 'Subscription Updated'),
        (ACTION_SUBSCRIPTION_CANCELED, 'Subscription Canceled'),
        (ACTION_REFUND_ISSUED, 'Refund Issued'),
        (ACTION_CREDIT_ADDED, 'Credit Added'),
        (ACTION_CREDIT_USED, 'Credit Used'),
        (ACTION_WEBHOOK_RECEIVED, 'Webhook Received'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_audit_logs',
    )
    action = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES,
    )
    stripe_event_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Stripe Event ID (evt_xxx)",
    )
    stripe_object_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Related Stripe object ID",
    )
    success = models.BooleanField(
        default=True,
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional details (sensitive data redacted)",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        verbose_name = "Payment Audit Log"
        verbose_name_plural = "Payment Audit Logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'action']),
            models.Index(fields=['stripe_event_id']),
            models.Index(fields=['created_at', 'action']),
        ]

    def __str__(self):
        user_str = self.user.email if self.user else 'Anonymous'
        return f"{user_str} - {self.get_action_display()} at {self.created_at}"

    @classmethod
    def log(cls, action, user=None, stripe_event_id='', stripe_object_id='',
            success=True, details=None, ip_address=None, user_agent=''):
        """Create an audit log entry."""
        return cls.objects.create(
            user=user,
            action=action,
            stripe_event_id=stripe_event_id,
            stripe_object_id=stripe_object_id,
            success=success,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
        )


class VIPPromoCode(TimeStampedModel):
    """
    VIP promo codes that grant lifetime free access.

    Unlike Stripe promo codes (which give discounts), VIP codes bypass
    payment entirely and grant STATUS_LIFETIME subscription status.

    Usage:
        - Create codes via Django Admin
        - Users enter code during onboarding (Welcome step)
        - Valid codes grant immediate lifetime access
    """

    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="The VIP code users will enter (case-insensitive, stored uppercase)",
    )
    description = models.CharField(
        max_length=255,
        help_text="Internal description (e.g., 'Beta tester reward')",
    )
    max_uses = models.PositiveIntegerField(
        default=1,
        help_text="Maximum number of times this code can be used (0 = unlimited)",
    )
    current_uses = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this code has been redeemed",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this code can currently be redeemed",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this code expires (null = never expires)",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_vip_codes',
        help_text="Admin who created this code",
    )

    class Meta:
        verbose_name = "VIP Promo Code"
        verbose_name_plural = "VIP Promo Codes"
        ordering = ['-created_at']

    def __str__(self):
        if self.max_uses == 0:
            return f"{self.code} ({self.current_uses}/unlimited)"
        return f"{self.code} ({self.current_uses}/{self.max_uses})"

    def save(self, *args, **kwargs):
        # Normalize code to uppercase
        self.code = self.code.upper().strip()
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        """Check if the code can be redeemed."""
        if not self.is_active:
            return False
        if self.max_uses > 0 and self.current_uses >= self.max_uses:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True

    def redeem(self, user):
        """
        Redeem this code for a user.

        Updates user's billing profile to STATUS_LIFETIME.
        Returns True on success, raises ValueError on failure.
        """
        if not self.is_valid:
            raise ValueError("This VIP code is no longer valid.")

        # Check if user already has lifetime access
        profile = user.billing_profile
        if profile.subscription_status == BillingProfile.STATUS_LIFETIME:
            raise ValueError("You already have lifetime access.")

        # Check if user already used a VIP code
        if VIPPromoCodeUsage.objects.filter(user=user).exists():
            raise ValueError("You have already redeemed a VIP code.")

        # Redeem the code - increment usage
        self.current_uses += 1
        self.save(update_fields=['current_uses', 'updated_at'])

        # Record usage
        VIPPromoCodeUsage.objects.create(
            user=user,
            vip_code=self,
        )

        # Grant lifetime access
        profile.subscription_status = BillingProfile.STATUS_LIFETIME
        profile.pricing_tier = BillingProfile.TIER_FOUNDING
        profile.billing_cycle = BillingProfile.CYCLE_LIFETIME
        profile.save(update_fields=[
            'subscription_status', 'pricing_tier', 'billing_cycle', 'updated_at'
        ])

        return True


class VIPPromoCodeUsage(TimeStampedModel):
    """
    Track VIP promo code redemptions.

    Separate from PromoCodeUsage which tracks Stripe promo codes.
    This is for audit and to prevent multiple VIP code redemptions per user.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vip_promo_usages',
    )
    vip_code = models.ForeignKey(
        VIPPromoCode,
        on_delete=models.CASCADE,
        related_name='usages',
    )
    redeemed_at = models.DateTimeField(
        auto_now_add=True,
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "VIP Promo Code Usage"
        verbose_name_plural = "VIP Promo Code Usages"
        unique_together = ['user', 'vip_code']
        ordering = ['-redeemed_at']

    def __str__(self):
        return f"{self.user.email} used {self.vip_code.code}"
