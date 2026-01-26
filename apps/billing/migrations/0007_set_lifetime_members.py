# ==============================================================================
# File: apps/billing/migrations/0007_set_lifetime_members.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Set lifetime subscription status for owner/family accounts
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-26
# ==============================================================================
"""
Data migration to set lifetime subscription status for owner and family accounts.

These accounts get permanent full access without requiring a Stripe subscription.
"""

from django.db import migrations


# Owner and family email addresses that get lifetime access
LIFETIME_MEMBERS = [
    'dannyjenkins71@gmail.com',
    'heatherjenkins74@gmail.com',
    'haleyjenkins02@gmail.com',
    'parkerledford3@gmail.com',
    'zboi175.ipad@gmail.com',
    'appreview@wholelifejourney.com',  # App Store review account
]


def set_lifetime_members(apps, schema_editor):
    """Set subscription_status to 'lifetime' for owner/family accounts."""
    BillingProfile = apps.get_model('billing', 'BillingProfile')
    User = apps.get_model('users', 'User')

    for email in LIFETIME_MEMBERS:
        try:
            user = User.objects.get(email__iexact=email)
            BillingProfile.objects.filter(user=user).update(
                subscription_status='lifetime'
            )
            print(f"  Set lifetime status for: {email}")
        except User.DoesNotExist:
            print(f"  User not found (skipping): {email}")


def reverse_lifetime_members(apps, schema_editor):
    """Reverse: set back to 'canceled' (would need manual fix anyway)."""
    # No-op - don't want to accidentally remove access
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0006_add_faith_only_tier'),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            set_lifetime_members,
            reverse_lifetime_members,
        ),
    ]
