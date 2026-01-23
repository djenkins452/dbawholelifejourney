"""
Billing services - Stripe integration and business logic.

This module provides the core Stripe integration and billing logic.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

import stripe
from django.conf import settings
from django.utils import timezone

from apps.core.utils import user_log_id
from .models import (
    BillingProfile,
    CreditTransaction,
    PaymentAuditLog,
    PromoCodeUsage,
    ReferralQualification,
    ReferralReward,
)

logger = logging.getLogger(__name__)


def get_billing_config():
    """
    Get billing configuration from the database.

    Returns a dict with all pricing, rewards, and threshold configuration.
    This is the single source of truth for all billing-related values.
    """
    from .models import BillingConfiguration
    try:
        config = BillingConfiguration.get_config()
        return config.as_dict()
    except Exception:
        # Fallback to empty dict if database not available
        return {}


def get_stripe():
    """Get configured Stripe client."""
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


class StripeService:
    """
    Service class for Stripe operations.

    Handles customer creation, checkout sessions, subscription management,
    and webhook processing.
    """

    # Price IDs - these should match your Stripe product configuration
    # Set via environment variables or settings
    PRICES = {
        'student_monthly': settings.STRIPE_PRICE_STUDENT_MONTHLY if hasattr(settings, 'STRIPE_PRICE_STUDENT_MONTHLY') else '',
        'student_annual': settings.STRIPE_PRICE_STUDENT_ANNUAL if hasattr(settings, 'STRIPE_PRICE_STUDENT_ANNUAL') else '',
        'adult_monthly': settings.STRIPE_PRICE_ADULT_MONTHLY if hasattr(settings, 'STRIPE_PRICE_ADULT_MONTHLY') else '',
        'adult_annual': settings.STRIPE_PRICE_ADULT_ANNUAL if hasattr(settings, 'STRIPE_PRICE_ADULT_ANNUAL') else '',
        'founding_lifetime': settings.STRIPE_PRICE_FOUNDING if hasattr(settings, 'STRIPE_PRICE_FOUNDING') else '',
    }

    @classmethod
    def get_or_create_customer(cls, user):
        """
        Get or create a Stripe customer for a user.

        Args:
            user: Django User instance

        Returns:
            Stripe Customer object
        """
        stripe_client = get_stripe()
        profile = user.billing_profile

        if profile.stripe_customer_id:
            try:
                customer = stripe_client.Customer.retrieve(profile.stripe_customer_id)
                if not customer.get('deleted'):
                    return customer
            except stripe.error.InvalidRequestError:
                # Customer doesn't exist in Stripe, create new one
                pass

        # Create new customer
        customer = stripe_client.Customer.create(
            email=user_log_id(user),
            name=user.get_full_name(),
            metadata={
                'user_id': str(user.id),
                'pricing_tier': profile.pricing_tier,
            }
        )

        # Save customer ID to profile
        profile.stripe_customer_id = customer.id
        profile.save(update_fields=['stripe_customer_id', 'updated_at'])

        logger.info(f"Created Stripe customer {customer.id} for user {user_log_id(user)}")
        return customer

    @classmethod
    def create_checkout_session(cls, user, price_key, success_url, cancel_url,
                                 promo_code=None, referral_code=None):
        """
        Create a Stripe Checkout session for subscription.

        Args:
            user: Django User instance
            price_key: Key from PRICES dict (e.g., 'adult_monthly')
            success_url: URL to redirect on success
            cancel_url: URL to redirect on cancel
            promo_code: Optional promo code string
            referral_code: Optional referral code (stored in metadata)

        Returns:
            Checkout Session object with url for redirect
        """
        stripe_client = get_stripe()
        customer = cls.get_or_create_customer(user)

        price_id = cls.PRICES.get(price_key)
        if not price_id:
            raise ValueError(f"Invalid price key: {price_key}")

        # Determine if this is a one-time payment (founding) or subscription
        is_subscription = price_key != 'founding_lifetime'

        session_params = {
            'customer': customer.id,
            'success_url': success_url + '?session_id={CHECKOUT_SESSION_ID}',
            'cancel_url': cancel_url,
            'metadata': {
                'user_id': str(user.id),
                'price_key': price_key,
                'referral_code': referral_code or '',
            },
        }

        if is_subscription:
            session_params['mode'] = 'subscription'
            session_params['line_items'] = [{
                'price': price_id,
                'quantity': 1,
            }]
        else:
            session_params['mode'] = 'payment'
            session_params['line_items'] = [{
                'price': price_id,
                'quantity': 1,
            }]

        # Handle promo code
        if promo_code:
            try:
                # Look up the promotion code in Stripe
                promo_codes = stripe_client.PromotionCode.list(code=promo_code, active=True)
                if promo_codes.data:
                    session_params['discounts'] = [{'promotion_code': promo_codes.data[0].id}]
                else:
                    logger.warning(f"Promo code {promo_code} not found or inactive")
            except stripe.error.StripeError as e:
                logger.error(f"Error looking up promo code: {e}")

        # Allow promo code entry during checkout if none provided
        if 'discounts' not in session_params:
            session_params['allow_promotion_codes'] = True

        session = stripe_client.checkout.Session.create(**session_params)

        # Log the checkout start
        PaymentAuditLog.log(
            action=PaymentAuditLog.ACTION_CHECKOUT_STARTED,
            user=user,
            stripe_object_id=session.id,
            details={
                'price_key': price_key,
                'mode': session_params['mode'],
            }
        )

        return session

    @classmethod
    def create_customer_portal_session(cls, user, return_url):
        """
        Create a Stripe Customer Portal session.

        Allows users to manage their subscription, update payment method,
        view invoices, etc.

        Args:
            user: Django User instance
            return_url: URL to return to after portal

        Returns:
            Portal Session object with url for redirect
        """
        stripe_client = get_stripe()
        customer = cls.get_or_create_customer(user)

        session = stripe_client.billing_portal.Session.create(
            customer=customer.id,
            return_url=return_url,
        )

        return session

    @classmethod
    def cancel_subscription(cls, user, at_period_end=True):
        """
        Cancel a user's subscription.

        Args:
            user: Django User instance
            at_period_end: If True, cancel at end of billing period

        Returns:
            Updated Subscription object
        """
        stripe_client = get_stripe()
        profile = user.billing_profile

        if not profile.stripe_subscription_id:
            raise ValueError("User has no active subscription")

        if at_period_end:
            subscription = stripe_client.Subscription.modify(
                profile.stripe_subscription_id,
                cancel_at_period_end=True,
            )
            profile.cancel_at_period_end = True
        else:
            subscription = stripe_client.Subscription.cancel(
                profile.stripe_subscription_id,
            )
            profile.subscription_status = BillingProfile.STATUS_CANCELED
            profile.stripe_subscription_id = ''

        profile.save()

        PaymentAuditLog.log(
            action=PaymentAuditLog.ACTION_SUBSCRIPTION_CANCELED,
            user=user,
            stripe_object_id=subscription.id,
            details={'at_period_end': at_period_end}
        )

        return subscription

    @classmethod
    def handle_checkout_completed(cls, session):
        """
        Handle successful checkout completion.

        Called by webhook when checkout.session.completed fires.

        Args:
            session: Stripe Checkout Session object
        """
        from apps.users.models import User

        user_id = session.metadata.get('user_id')
        if not user_id:
            logger.error(f"Checkout session {session.id} missing user_id in metadata")
            return

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.error(f"User {user_id} not found for checkout {session.id}")
            return

        profile = user.billing_profile
        price_key = session.metadata.get('price_key', '')

        # Update profile based on price
        if 'student' in price_key:
            profile.pricing_tier = BillingProfile.TIER_STUDENT
        elif 'adult' in price_key:
            profile.pricing_tier = BillingProfile.TIER_ADULT
        elif 'founding' in price_key:
            profile.pricing_tier = BillingProfile.TIER_FOUNDING
            profile.subscription_status = BillingProfile.STATUS_LIFETIME

        # Set billing cycle
        if 'monthly' in price_key:
            profile.billing_cycle = BillingProfile.CYCLE_MONTHLY
        elif 'annual' in price_key:
            profile.billing_cycle = BillingProfile.CYCLE_ANNUAL
        elif 'lifetime' in price_key:
            profile.billing_cycle = BillingProfile.CYCLE_LIFETIME

        # Get subscription ID if applicable
        if session.mode == 'subscription' and session.subscription:
            profile.stripe_subscription_id = session.subscription
            profile.subscription_status = BillingProfile.STATUS_ACTIVE

        profile.save()

        # Handle referral code if present
        referral_code = session.metadata.get('referral_code')
        if referral_code:
            cls._process_referral_on_checkout(user, referral_code)

        # Log success
        PaymentAuditLog.log(
            action=PaymentAuditLog.ACTION_CHECKOUT_COMPLETED,
            user=user,
            stripe_object_id=session.id,
            details={
                'price_key': price_key,
                'tier': profile.pricing_tier,
            }
        )

        logger.info(f"Checkout completed for {user_log_id(user)}: {profile.pricing_tier}")

    @classmethod
    def handle_invoice_paid(cls, invoice):
        """
        Handle successful invoice payment.

        Called by webhook when invoice.paid fires.

        Args:
            invoice: Stripe Invoice object
        """
        from apps.users.models import User

        customer_id = invoice.customer
        if not customer_id:
            return

        try:
            profile = BillingProfile.objects.get(stripe_customer_id=customer_id)
            user = profile.user
        except BillingProfile.DoesNotExist:
            logger.warning(f"No profile found for customer {customer_id}")
            return

        # Update subscription status
        if profile.subscription_status == BillingProfile.STATUS_PAST_DUE:
            profile.subscription_status = BillingProfile.STATUS_ACTIVE
            profile.save(update_fields=['subscription_status', 'updated_at'])

        # Check if this is first payment for referral tracking
        cls._process_referral_first_payment(user)

        PaymentAuditLog.log(
            action=PaymentAuditLog.ACTION_PAYMENT_SUCCESS,
            user=user,
            stripe_object_id=invoice.id,
            details={
                'amount': invoice.amount_paid / 100,  # Convert cents to dollars
                'currency': invoice.currency,
            }
        )

    @classmethod
    def handle_invoice_payment_failed(cls, invoice):
        """
        Handle failed invoice payment.

        Args:
            invoice: Stripe Invoice object
        """
        customer_id = invoice.customer
        if not customer_id:
            return

        try:
            profile = BillingProfile.objects.get(stripe_customer_id=customer_id)
            user = profile.user
        except BillingProfile.DoesNotExist:
            return

        profile.subscription_status = BillingProfile.STATUS_PAST_DUE
        profile.save(update_fields=['subscription_status', 'updated_at'])

        PaymentAuditLog.log(
            action=PaymentAuditLog.ACTION_PAYMENT_FAILED,
            user=user,
            stripe_object_id=invoice.id,
            success=False,
            details={
                'amount': invoice.amount_due / 100,
                'attempt_count': invoice.attempt_count,
            }
        )

        # TODO: Send payment_failed email

    @classmethod
    def handle_subscription_updated(cls, subscription):
        """
        Handle subscription updates (status changes, plan changes).

        Args:
            subscription: Stripe Subscription object
        """
        customer_id = subscription.customer
        if not customer_id:
            return

        try:
            profile = BillingProfile.objects.get(stripe_customer_id=customer_id)
        except BillingProfile.DoesNotExist:
            return

        # Map Stripe status to our status
        status_map = {
            'active': BillingProfile.STATUS_ACTIVE,
            'trialing': BillingProfile.STATUS_TRIALING,
            'past_due': BillingProfile.STATUS_PAST_DUE,
            'canceled': BillingProfile.STATUS_CANCELED,
            'unpaid': BillingProfile.STATUS_PAST_DUE,
        }

        profile.subscription_status = status_map.get(
            subscription.status,
            BillingProfile.STATUS_NONE
        )
        profile.stripe_subscription_id = subscription.id
        profile.cancel_at_period_end = subscription.cancel_at_period_end

        # Update billing period
        if subscription.current_period_start:
            profile.current_period_start = timezone.datetime.fromtimestamp(
                subscription.current_period_start,
                tz=timezone.utc
            )
        if subscription.current_period_end:
            profile.current_period_end = timezone.datetime.fromtimestamp(
                subscription.current_period_end,
                tz=timezone.utc
            )

        profile.save()

        PaymentAuditLog.log(
            action=PaymentAuditLog.ACTION_SUBSCRIPTION_UPDATED,
            user=profile.user,
            stripe_object_id=subscription.id,
            details={
                'status': subscription.status,
                'cancel_at_period_end': subscription.cancel_at_period_end,
            }
        )

    @classmethod
    def handle_subscription_deleted(cls, subscription):
        """
        Handle subscription cancellation/deletion.

        Args:
            subscription: Stripe Subscription object
        """
        customer_id = subscription.customer
        if not customer_id:
            return

        try:
            profile = BillingProfile.objects.get(stripe_customer_id=customer_id)
        except BillingProfile.DoesNotExist:
            return

        # Keep tier but mark as canceled
        profile.subscription_status = BillingProfile.STATUS_CANCELED
        profile.stripe_subscription_id = ''
        profile.cancel_at_period_end = False
        profile.save()

        PaymentAuditLog.log(
            action=PaymentAuditLog.ACTION_SUBSCRIPTION_CANCELED,
            user=profile.user,
            stripe_object_id=subscription.id,
        )

    @classmethod
    def _process_referral_on_checkout(cls, user, referral_code):
        """
        Process referral code on checkout.

        Links the new user to their referrer.
        """
        try:
            referrer_profile = BillingProfile.objects.get(referral_code=referral_code)
            referrer = referrer_profile.user
        except BillingProfile.DoesNotExist:
            logger.warning(f"Invalid referral code: {referral_code}")
            return

        profile = user.billing_profile
        if profile.referred_by:
            # Already has a referrer, don't overwrite
            return

        profile.referred_by = referrer
        profile.save(update_fields=['referred_by', 'updated_at'])

        # Create ReferralReward record
        ReferralReward.objects.get_or_create(
            referrer=referrer,
            referred_user=user,
            defaults={
                'signup_date': timezone.now().date(),
            }
        )

        # If referrer is Founding Member, create qualification tracking
        if referrer_profile.is_founding_member:
            # Get qualification days from config (defaults to 90)
            config = get_billing_config()
            qualification_days = config.get('rewards', {}).get('referral_qualification_days', 90)

            ReferralQualification.objects.get_or_create(
                referrer=referrer,
                referred_user=user,
                defaults={
                    'signup_date': timezone.now().date(),
                    'qualified_date': timezone.now().date() + timedelta(days=qualification_days),
                }
            )

        logger.info(f"Referral recorded: {user_log_id(referrer)} referred {user_log_id(user)}")

    @classmethod
    def _process_referral_first_payment(cls, user):
        """
        Process first payment for referral rewards.

        Gives $5 credit to both referrer and referred user.
        """
        try:
            referral = ReferralReward.objects.get(
                referred_user=user,
                first_payment_date__isnull=True,
            )
        except ReferralReward.DoesNotExist:
            # User wasn't referred or already processed
            return

        referral.first_payment_date = timezone.now().date()
        referral.process_rewards()

        logger.info(f"Referral rewards processed for {user_log_id(user)}")


# Utility functions

def calculate_age(birth_date):
    """Calculate age from birth date."""
    if not birth_date:
        return None
    today = date.today()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def determine_tier_by_age(birth_date):
    """
    Determine pricing tier based on age.

    Uses database configuration for age thresholds.
    """
    from .models import BillingConfiguration

    age = calculate_age(birth_date)
    if age is None:
        return BillingProfile.TIER_ADULT  # Default to adult if unknown

    # Get age threshold from database config (defaults to 22 if not set)
    try:
        config = BillingConfiguration.get_config()
        student_max_age = config.student_max_age
    except Exception:
        student_max_age = 22

    if age <= student_max_age:
        return BillingProfile.TIER_STUDENT
    return BillingProfile.TIER_ADULT


def is_subscription_active(user):
    """Check if a user has an active subscription."""
    try:
        return user.billing_profile.is_subscribed
    except BillingProfile.DoesNotExist:
        return False


def get_current_quarter():
    """Get the current quarter string (e.g., '2026-Q1')."""
    today = date.today()
    quarter = (today.month - 1) // 3 + 1
    return f"{today.year}-Q{quarter}"


# VIP Promo Code Functions

def validate_vip_code(code):
    """
    Validate a VIP promo code.

    Args:
        code: The VIP code string

    Returns:
        VIPPromoCode instance if valid, None if not found or invalid
    """
    from .models import VIPPromoCode

    if not code:
        return None

    code = code.upper().strip()

    try:
        vip_code = VIPPromoCode.objects.get(code=code)
        if vip_code.is_valid:
            return vip_code
        return None
    except VIPPromoCode.DoesNotExist:
        return None


def redeem_vip_code(user, code, ip_address=None):
    """
    Redeem a VIP promo code for a user.

    Args:
        user: User instance
        code: The VIP code string
        ip_address: Optional client IP for audit

    Returns:
        tuple: (success: bool, message: str)
    """
    from .models import VIPPromoCode, VIPPromoCodeUsage

    if not code:
        return False, "No VIP code provided."

    code = code.upper().strip()

    try:
        vip_code = VIPPromoCode.objects.get(code=code)
    except VIPPromoCode.DoesNotExist:
        return False, "Invalid VIP code."

    try:
        vip_code.redeem(user)

        # Update usage record with IP if provided
        if ip_address:
            usage = VIPPromoCodeUsage.objects.get(user=user, vip_code=vip_code)
            usage.ip_address = ip_address
            usage.save(update_fields=['ip_address'])

        # Log the redemption
        PaymentAuditLog.log(
            action='vip_code_redeemed',
            user=user,
            details={
                'vip_code': code,
                'vip_code_id': vip_code.id,
            },
            ip_address=ip_address,
        )

        logger.info(f"VIP code {code} redeemed by {user_log_id(user)}")
        return True, "VIP code redeemed! You now have lifetime access."

    except ValueError as e:
        return False, str(e)


def has_vip_access(user):
    """
    Check if a user has VIP/lifetime access.

    Returns True if user has STATUS_LIFETIME subscription.
    """
    try:
        return user.billing_profile.subscription_status == BillingProfile.STATUS_LIFETIME
    except Exception:
        return False
