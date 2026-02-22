"""Aggregate LLMUsageEvent into DailyCostRollup rows."""

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count, Sum

from apps.owner_finance.models import LLMUsageEvent, DailyCostRollup


class Command(BaseCommand):
    help = 'Build/rebuild DailyCostRollup from LLMUsageEvent data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=7,
            help='Number of past days to rollup (default: 7)',
        )

    def handle(self, *args, **options):
        days = options['days']
        today = date.today()

        for d in range(days):
            rollup_date = today - timedelta(days=d)
            self._rollup_date(rollup_date)

        self.stdout.write(self.style.SUCCESS(f'Rolled up {days} days'))

    def _rollup_date(self, rollup_date):
        events = LLMUsageEvent.objects.filter(
            created_at__date=rollup_date,
        )

        # Per-user, per-feature rollup
        rows = (
            events
            .values('user', 'feature')
            .annotate(
                total_cost=Sum('cost_usd'),
                total_calls=Count('id'),
                total_input=Sum('input_tokens'),
                total_output=Sum('output_tokens'),
            )
        )

        for row in rows:
            DailyCostRollup.objects.update_or_create(
                date=rollup_date,
                user_id=row['user'],
                feature=row['feature'],
                defaults={
                    'total_cost_usd': row['total_cost'] or 0,
                    'total_calls': row['total_calls'] or 0,
                    'total_input_tokens': row['total_input'] or 0,
                    'total_output_tokens': row['total_output'] or 0,
                },
            )

        # Also a system total row (user=None, feature=None)
        totals = events.aggregate(
            total_cost=Sum('cost_usd'),
            total_calls=Count('id'),
            total_input=Sum('input_tokens'),
            total_output=Sum('output_tokens'),
        )
        if totals['total_calls']:
            DailyCostRollup.objects.update_or_create(
                date=rollup_date,
                user=None,
                feature=None,
                defaults={
                    'total_cost_usd': totals['total_cost'] or 0,
                    'total_calls': totals['total_calls'] or 0,
                    'total_input_tokens': totals['total_input'] or 0,
                    'total_output_tokens': totals['total_output'] or 0,
                },
            )
