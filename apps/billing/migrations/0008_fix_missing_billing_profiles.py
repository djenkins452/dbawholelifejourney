# ==============================================================================
# File: apps/billing/migrations/0008_fix_missing_billing_profiles.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Create missing BillingProfiles and re-apply lifetime status
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-26
# ==============================================================================
"""
Data migration to ensure all users have BillingProfiles and lifetime members
have correct status.

This fixes an issue where 0007 used filter().update() which didn't create
missing profiles.
"""

import secrets
import string

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


def generate_referral_code(user, BillingProfile):
    """Generate a unique referral code for a user."""
    if user.first_name:
        base = user.first_name.upper()[:6]
    else:
        base = user.email.split('@')[0].upper()[:6]

    suffix = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    code = f"{base}-{suffix}"

    # Ensure uniqueness
    while BillingProfile.objects.filter(referral_code=code).exists():
        suffix = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
        code = f"{base}-{suffix}"

    return code


def ensure_billing_profiles_and_lifetime(apps, schema_editor):
    """
    1. Create BillingProfile for any user missing one
    2. Set lifetime status for owner/family accounts
    """
    BillingProfile = apps.get_model('billing', 'BillingProfile')
    User = apps.get_model('users', 'User')

    # First, ensure ALL users have a billing profile
    all_users = User.objects.all()
    for user in all_users:
        if not BillingProfile.objects.filter(user=user).exists():
            # Generate unique referral code
            referral_code = generate_referral_code(user, BillingProfile)
            BillingProfile.objects.create(
                user=user,
                subscription_status='canceled',
                referral_code=referral_code,
            )
            print(f"  Created missing BillingProfile for: {user.email}")

    # Then set lifetime status for owner/family
    for email in LIFETIME_MEMBERS:
        try:
            user = User.objects.get(email__iexact=email)
            updated = BillingProfile.objects.filter(user=user).update(
                subscription_status='lifetime'
            )
            if updated:
                print(f"  Set lifetime status for: {email}")
        except User.DoesNotExist:
            print(f"  User not found (skipping): {email}")


def noop(apps, schema_editor):
    """No-op for reverse migration."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0007_set_lifetime_members'),
    ]

    operations = [
        migrations.RunPython(
            ensure_billing_profiles_and_lifetime,
            noop,
        ),
    ]
