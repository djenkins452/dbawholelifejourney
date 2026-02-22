"""Owner Financial Command Center views — Phase 2."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, F, Q, Sum, Case, When, Value, DecimalField
from django.utils import timezone
from django.views.generic import TemplateView

from .mixins import OwnerOnlyMixin
from .models import LLMUsageEvent, UserSubscriptionSnapshot, VendorBillingRecord


def _parse_date_range(request):
    """Extract start/end from GET params, default to last 30 days."""
    now = timezone.now()
    days = int(request.GET.get('days', 30))
    end_date = now
    start_date = now - timedelta(days=days)
    return start_date, end_date, days


class OverviewView(OwnerOnlyMixin, TemplateView):
    """Main dashboard with KPI cards, top users, top features, escalation stats."""

    template_name = 'owner_finance/overview.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        start, end, days = _parse_date_range(self.request)

        events = LLMUsageEvent.objects.filter(created_at__range=(start, end))

        # --- KPI aggregates ---
        agg = events.aggregate(
            total_cost=Sum('cost_usd'),
            total_calls=Count('id'),
            total_input=Sum('input_tokens'),
            total_output=Sum('output_tokens'),
        )
        total_cost = agg['total_cost'] or Decimal('0')

        # Revenue from subscription snapshots active in this period
        revenue_agg = UserSubscriptionSnapshot.objects.filter(
            effective_start__lte=end,
        ).filter(
            Q(effective_end__isnull=True) | Q(effective_end__gte=start),
        ).aggregate(total_revenue=Sum('monthly_price_usd'))
        total_revenue = revenue_agg['total_revenue'] or Decimal('0')

        margin = total_revenue - total_cost
        margin_pct = (
            (margin / total_revenue * 100) if total_revenue else Decimal('0')
        )

        # Active users in period
        active_users = events.values('user').distinct().count()
        avg_cost_per_user = (
            total_cost / active_users if active_users else Decimal('0')
        )

        # Non-LLM costs from VendorBillingRecord
        non_llm_cost = VendorBillingRecord.objects.filter(
            period_start__lte=end,
            period_end__gte=start,
        ).exclude(
            vendor__category='LLM',
        ).aggregate(total=Sum('cost_usd'))['total'] or Decimal('0')

        ctx['kpi'] = {
            'total_cost': total_cost,
            'total_revenue': total_revenue,
            'margin': margin,
            'margin_pct': margin_pct,
            'avg_cost_per_user': avg_cost_per_user,
            'active_users': active_users,
            'total_calls': agg['total_calls'] or 0,
            'total_input_tokens': agg['total_input'] or 0,
            'total_output_tokens': agg['total_output'] or 0,
            'llm_cost': total_cost,
            'non_llm_cost': non_llm_cost,
        }

        # --- Top 10 expensive users ---
        ctx['top_users'] = (
            events
            .filter(user__isnull=False)
            .values('user__id', 'user__email')
            .annotate(
                total_cost=Sum('cost_usd'),
                total_calls=Count('id'),
                total_tokens=Sum(F('input_tokens') + F('output_tokens')),
            )
            .order_by('-total_cost')[:10]
        )

        # --- Top features by cost ---
        ctx['top_features'] = (
            events
            .values('feature')
            .annotate(
                total_cost=Sum('cost_usd'),
                total_calls=Count('id'),
            )
            .order_by('-total_cost')[:10]
        )

        # --- Escalation economics ---
        esc_stats = events.aggregate(
            normal_calls=Count('id', filter=Q(escalated=False)),
            escalated_calls=Count('id', filter=Q(escalated=True)),
            normal_cost=Sum('cost_usd', filter=Q(escalated=False)),
            escalated_cost=Sum('cost_usd', filter=Q(escalated=True)),
        )
        normal_calls = esc_stats['normal_calls'] or 0
        escalated_calls = esc_stats['escalated_calls'] or 0
        total_calls = normal_calls + escalated_calls

        ctx['escalation'] = {
            'normal_calls': normal_calls,
            'escalated_calls': escalated_calls,
            'avg_cost_normal': (
                (esc_stats['normal_cost'] or Decimal('0')) / normal_calls
                if normal_calls else Decimal('0')
            ),
            'avg_cost_escalated': (
                (esc_stats['escalated_cost'] or Decimal('0')) / escalated_calls
                if escalated_calls else Decimal('0')
            ),
            'escalation_rate': (
                escalated_calls / total_calls * 100 if total_calls else 0
            ),
        }

        ctx['days'] = days
        ctx['feature_labels'] = dict(LLMUsageEvent.FEATURE_CHOICES)
        return ctx


class UserCostsView(OwnerOnlyMixin, TemplateView):
    """Per-user cost and margin breakdown."""

    template_name = 'owner_finance/users.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        start, end, days = _parse_date_range(self.request)

        events = LLMUsageEvent.objects.filter(created_at__range=(start, end))

        # Per-user costs
        user_costs = (
            events
            .filter(user__isnull=False)
            .values('user__id', 'user__email')
            .annotate(
                total_cost=Sum('cost_usd'),
                total_calls=Count('id'),
                total_input=Sum('input_tokens'),
                total_output=Sum('output_tokens'),
                escalated_calls=Count('id', filter=Q(escalated=True)),
            )
            .order_by('-total_cost')
        )

        # Attach subscription info
        sub_map = {}
        for snap in UserSubscriptionSnapshot.objects.filter(
            effective_start__lte=end,
        ).filter(
            Q(effective_end__isnull=True) | Q(effective_end__gte=start),
        ):
            sub_map[snap.user_id] = snap

        enriched = []
        for row in user_costs:
            snap = sub_map.get(row['user__id'])
            revenue = snap.monthly_price_usd if snap else Decimal('0')
            tier = snap.tier if snap else 'FREE'
            cost = row['total_cost'] or Decimal('0')
            margin = revenue - cost
            enriched.append({
                **row,
                'total_cost': cost,
                'tier': tier,
                'revenue': revenue,
                'margin': margin,
                'margin_pct': (margin / revenue * 100) if revenue else Decimal('0'),
            })

        ctx['user_costs'] = enriched
        ctx['days'] = days
        return ctx


class FeatureBreakdownView(OwnerOnlyMixin, TemplateView):
    """Feature / engine / model cost breakdown."""

    template_name = 'owner_finance/features.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        start, end, days = _parse_date_range(self.request)

        events = LLMUsageEvent.objects.filter(created_at__range=(start, end))

        ctx['by_feature'] = (
            events
            .values('feature')
            .annotate(
                total_cost=Sum('cost_usd'),
                total_calls=Count('id'),
                avg_input=Avg('input_tokens'),
                avg_output=Avg('output_tokens'),
            )
            .order_by('-total_cost')
        )

        ctx['by_model'] = (
            events
            .values('model_name')
            .annotate(
                total_cost=Sum('cost_usd'),
                total_calls=Count('id'),
                total_input=Sum('input_tokens'),
                total_output=Sum('output_tokens'),
            )
            .order_by('-total_cost')
        )

        ctx['by_engine'] = (
            events
            .exclude(engine='')
            .values('engine')
            .annotate(
                total_cost=Sum('cost_usd'),
                total_calls=Count('id'),
            )
            .order_by('-total_cost')
        )

        ctx['days'] = days
        ctx['feature_labels'] = dict(LLMUsageEvent.FEATURE_CHOICES)
        return ctx


class VendorLedgerView(OwnerOnlyMixin, TemplateView):
    """Vendor billing records."""

    template_name = 'owner_finance/vendors.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx['records'] = (
            VendorBillingRecord.objects
            .select_related('vendor')
            .order_by('-period_start')[:50]
        )

        # Summary by vendor
        ctx['vendor_summary'] = (
            VendorBillingRecord.objects
            .values('vendor__name', 'vendor__category')
            .annotate(
                total_cost=Sum('cost_usd'),
                record_count=Count('id'),
            )
            .order_by('-total_cost')
        )

        return ctx
