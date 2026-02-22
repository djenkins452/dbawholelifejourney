"""Check budget guardrails and create alerts when thresholds exceeded."""

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from apps.owner_finance.models import BudgetGuardrail, LLMUsageEvent

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check budget guardrails and log warnings for exceeded thresholds'

    def handle(self, *args, **options):
        guardrails = BudgetGuardrail.objects.filter(is_active=True)
        alerts = []

        for g in guardrails:
            spend = self._get_spend(g)
            threshold = g.budget_usd * Decimal(str(g.alert_threshold_pct)) / Decimal('100')

            if spend >= g.budget_usd:
                status = 'EXCEEDED'
                alerts.append((g, spend, status))
            elif spend >= threshold:
                status = 'WARNING'
                alerts.append((g, spend, status))

        for guardrail, spend, status in alerts:
            pct = (spend / guardrail.budget_usd * 100) if guardrail.budget_usd else 0
            msg = (
                f"[{status}] {guardrail.name}: "
                f"${spend:.2f} / ${guardrail.budget_usd:.2f} "
                f"({pct:.0f}%)"
            )
            if status == 'EXCEEDED':
                logger.warning(msg)
                self.stdout.write(self.style.ERROR(msg))
            else:
                logger.info(msg)
                self.stdout.write(self.style.WARNING(msg))

            # Create notification if notification system available
            self._try_create_notification(guardrail, spend, status)

        if not alerts:
            self.stdout.write(self.style.SUCCESS('All budgets within limits'))

    def _get_spend(self, guardrail):
        today = date.today()
        if guardrail.period == 'MONTHLY':
            start = today.replace(day=1)
        else:
            start = today

        events = LLMUsageEvent.objects.filter(created_at__date__gte=start)

        if guardrail.scope == 'PER_FEATURE' and guardrail.scope_value:
            events = events.filter(feature=guardrail.scope_value)
        elif guardrail.scope == 'PER_USER':
            # For PER_USER, return max single-user spend
            user_spend = (
                events
                .filter(user__isnull=False)
                .values('user')
                .annotate(total=Sum('cost_usd'))
                .order_by('-total')
                .first()
            )
            return user_spend['total'] if user_spend else Decimal('0')

        agg = events.aggregate(total=Sum('cost_usd'))
        return agg['total'] or Decimal('0')

    def _try_create_notification(self, guardrail, spend, status):
        """Best-effort: create a system notification for the owner."""
        try:
            from apps.core.models import Notification
            from django.contrib.auth import get_user_model
            User = get_user_model()

            # Notify superusers
            for user in User.objects.filter(is_superuser=True):
                pct = (spend / guardrail.budget_usd * 100) if guardrail.budget_usd else 0
                Notification.objects.create(
                    user=user,
                    title=f"Budget {status}: {guardrail.name}",
                    message=(
                        f"Spend: ${spend:.2f} / ${guardrail.budget_usd:.2f} ({pct:.0f}%). "
                        f"Scope: {guardrail.get_scope_display()}, "
                        f"Period: {guardrail.get_period_display()}."
                    ),
                    category='system',
                    action_url='/owner/finance/',
                )
        except Exception:
            pass  # notification system may not match exactly
