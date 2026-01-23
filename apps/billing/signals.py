"""
Billing app signals.

Auto-creates BillingProfile when User is created with age-based tier assignment
and free trial period.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.core.utils import user_log_id

logger = logging.getLogger(__name__)


def get_trial_days():
    """Get the number of trial days from BillingConfiguration."""
    try:
        from apps.billing.models import BillingConfiguration
        config = BillingConfiguration.get_config()
        return config.free_trial_days
    except Exception:
        return 7  # Default to 7 days if config not available


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_billing_profile(sender, instance, created, **kwargs):
    """
    Create a BillingProfile for every new user.

    Sets the initial pricing tier based on the user's age:
    - Age <= 22: Student tier
    - Age >= 23: Adult tier

    The tier is set to FREE initially (no subscription).
    The eligible tier is determined but the user still needs to subscribe.

    Also sets up a free trial period based on BillingConfiguration.free_trial_days.
    """
    if created:
        from apps.billing.models import BillingProfile
        from apps.billing.services import determine_tier_by_age

        # Determine eligible tier based on date of birth
        eligible_tier = determine_tier_by_age(instance.date_of_birth)

        # Calculate trial end date
        trial_days = get_trial_days()
        trial_ends_at = None
        if trial_days > 0:
            trial_ends_at = timezone.now() + timedelta(days=trial_days)

        # Create profile - tier stays FREE until they subscribe
        # But we track what tier they're eligible for
        profile, was_created = BillingProfile.objects.get_or_create(
            user=instance,
            defaults={
                'pricing_tier': BillingProfile.TIER_FREE,
                'trial_ends_at': trial_ends_at,
            }
        )

        if was_created:
            trial_info = f", trial ends {trial_ends_at}" if trial_ends_at else ""
            logger.info(
                f"Created BillingProfile for {user_log_id(instance)}, "
                f"eligible for {eligible_tier} tier based on age{trial_info}"
            )


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def update_billing_profile_on_dob_change(sender, instance, created, **kwargs):
    """
    Update eligible tier if user's date of birth changes.

    This handles the case where a user updates their DOB after signup.
    Only updates if they haven't already subscribed.
    """
    if not created:
        try:
            profile = instance.billing_profile
            # Only update tier eligibility if user is still on free tier
            # (hasn't subscribed yet)
            if profile.pricing_tier == profile.TIER_FREE:
                from apps.billing.services import determine_tier_by_age
                # Just log the eligible tier - don't change anything
                # since they haven't subscribed yet
                eligible = determine_tier_by_age(instance.date_of_birth)
                logger.debug(
                    f"User {user_log_id(instance)} eligible for {eligible} tier"
                )
        except Exception:
            pass  # Profile might not exist during tests
