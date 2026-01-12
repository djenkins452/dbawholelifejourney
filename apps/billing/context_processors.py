"""
Billing context processors.

Provides billing configuration to all templates.
"""

from .models import BillingConfiguration


def billing_config(request):
    """
    Add billing configuration to template context from database.

    This allows templates to access pricing, rewards, and other
    billing configuration without hardcoding values.

    Usage in templates:
        {{ billing_config.student.monthly_price }}
        {{ billing_config.rewards.referral_bonus }}
        {{ billing_config.student_max_age }}
    """
    try:
        config = BillingConfiguration.get_config()
        return {
            'billing_config': config.as_dict(),
        }
    except Exception:
        # Fallback to empty dict if database not available
        return {
            'billing_config': {},
        }
