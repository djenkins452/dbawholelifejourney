"""
Billing context processors.

Provides billing configuration to all templates.
"""

from django.conf import settings


def billing_config(request):
    """
    Add BILLING_CONFIG to template context.

    This allows templates to access pricing, rewards, and other
    billing configuration without hardcoding values.

    Usage in templates:
        {{ billing_config.student.monthly_price }}
        {{ billing_config.rewards.referral_bonus }}
        {{ billing_config.student_max_age }}
    """
    config = getattr(settings, 'BILLING_CONFIG', {})
    return {
        'billing_config': config,
    }
