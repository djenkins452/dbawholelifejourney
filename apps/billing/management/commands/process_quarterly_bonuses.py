"""
Management command to process quarterly bonuses for Founding Members.

Run quarterly (1st of Jan, Apr, Jul, Oct) or monthly for more frequent updates.

Usage:
    python manage.py process_quarterly_bonuses
    python manage.py process_quarterly_bonuses --dry-run
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.billing.models import (
    BillingProfile,
    FoundingMemberPayout,
    ReferralQualification,
)
from apps.billing.services import get_current_quarter
from apps.core.utils import user_log_id

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process quarterly referral bonuses for Founding Members'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--quarter',
            type=str,
            help='Process specific quarter (e.g., 2026-Q1). Defaults to current quarter.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        quarter = options.get('quarter') or get_current_quarter()

        self.stdout.write(f"Processing quarterly bonuses for {quarter}")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made"))

        # Step 1: Update referral qualifications
        self.update_referral_qualifications(dry_run)

        # Step 2: Calculate and create payouts for Founding Members
        self.process_founding_member_payouts(quarter, dry_run)

        self.stdout.write(self.style.SUCCESS("Quarterly bonus processing complete"))

    def update_referral_qualifications(self, dry_run):
        """
        Check referrals that have hit the 90-day mark.

        A referral qualifies for bonus if:
        - 90 days have passed since signup
        - The referred user still has an active subscription
        """
        today = timezone.now().date()

        # Find qualifications that should be checked
        pending_qualifications = ReferralQualification.objects.filter(
            bonus_eligible=False,
            bonus_paid=False,
            qualified_date__lte=today,
        )

        qualified_count = 0
        disqualified_count = 0

        for qual in pending_qualifications:
            try:
                referred_profile = qual.referred_user.billing_profile

                # Check if referred user is still subscribed
                if referred_profile.is_subscribed:
                    qual.bonus_eligible = True
                    qualified_count += 1
                    if not dry_run:
                        qual.save(update_fields=['bonus_eligible', 'updated_at'])
                    self.stdout.write(
                        f"  Qualified: {qual.referred_user.email} referred by {qual.referrer.email}"
                    )
                else:
                    disqualified_count += 1
                    self.stdout.write(
                        f"  Not qualified (not subscribed): {qual.referred_user.email}"
                    )
            except BillingProfile.DoesNotExist:
                disqualified_count += 1

        self.stdout.write(
            f"Qualification check: {qualified_count} qualified, {disqualified_count} not qualified"
        )

    def process_founding_member_payouts(self, quarter, dry_run):
        """
        Calculate and create payout records for each Founding Member.
        """
        # Get all Founding Members
        founding_members = BillingProfile.objects.filter(
            pricing_tier=BillingProfile.TIER_FOUNDING,
        ).select_related('user')

        total_payouts = Decimal('0.00')
        member_count = 0

        for profile in founding_members:
            user = profile.user

            # Count qualifying referrals for this quarter that haven't been paid
            qualifying_referrals = ReferralQualification.objects.filter(
                referrer=user,
                bonus_eligible=True,
                bonus_paid=False,
            )

            count = qualifying_referrals.count()
            if count == 0:
                continue

            # Calculate payout ($5 per qualified referral)
            payout_amount = Decimal(str(count * 5))
            total_payouts += payout_amount
            member_count += 1

            self.stdout.write(
                f"  {user.email}: {count} referrals = ${payout_amount}"
            )

            if not dry_run:
                with transaction.atomic():
                    # Create or update payout record
                    payout, created = FoundingMemberPayout.objects.update_or_create(
                        founding_member=user,
                        quarter=quarter,
                        defaults={
                            'qualifying_referrals': count,
                            'payout_amount': payout_amount,
                            'payout_method': profile.payout_method,
                            'status': FoundingMemberPayout.STATUS_PENDING,
                        }
                    )

                    # Mark referrals as included in this payout
                    qualifying_referrals.update(
                        quarter_applied=quarter,
                    )

                    if created:
                        logger.info(f"Created payout for {user_log_id(user)}: ${payout_amount}")
                    else:
                        logger.info(f"Updated payout for {user_log_id(user)}: ${payout_amount}")

        self.stdout.write(
            f"\nTotal: {member_count} Founding Members, ${total_payouts} in pending payouts"
        )
