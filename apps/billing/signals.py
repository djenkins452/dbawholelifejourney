"""
Billing app signals.

Auto-creates BillingProfile when User is created.
"""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_billing_profile(sender, instance, created, **kwargs):
    """Create a BillingProfile for every new user."""
    if created:
        from apps.billing.models import BillingProfile
        BillingProfile.objects.get_or_create(user=instance)
