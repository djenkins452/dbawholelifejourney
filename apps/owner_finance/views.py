"""Owner Financial Command Center views — Phases 2-5."""

import csv
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, F, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from .mixins import OwnerOnlyMixin
from .models import (
    BudgetGuardrail, DailyCostRollup, LLMUsageEvent,
    UserSubscriptionSnapshot, VendorBillingRecord,
)


def _parse_date_range(request):
    """Extract start/end from GET params, default to last 30 days."""
    now = timezone.now()
    days = int(request.GET.get('days', 30))
    end_date = now
    start_date = now - timedelta(days=days)
    return start_date, end_date, days


class OverviewView(OwnerOnlyMixin, TemplateView):
    """Main dashboard with KPI cards, top users, top features, escalation stats, budget warnings."""

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

        # --- Budget guardrail warnings (Phase 5) ---
        ctx['budget_alerts'] = self._get_budget_alerts()

        ctx['days'] = days
        ctx['feature_labels'] = dict(LLMUsageEvent.FEATURE_CHOICES)
        return ctx

    def _get_budget_alerts(self):
        """Check active guardrails and return any warnings/exceeded."""
        alerts = []
        today = date.today()

        for g in BudgetGuardrail.objects.filter(is_active=True):
            if g.period == 'MONTHLY':
                period_start = today.replace(day=1)
            else:
                period_start = today

            events = LLMUsageEvent.objects.filter(created_at__date__gte=period_start)

            if g.scope == 'PER_FEATURE' and g.scope_value:
                events = events.filter(feature=g.scope_value)

            if g.scope == 'PER_USER':
                user_spend = (
                    events.filter(user__isnull=False)
                    .values('user')
                    .annotate(total=Sum('cost_usd'))
                    .order_by('-total')
                    .first()
                )
                spend = user_spend['total'] if user_spend else Decimal('0')
            else:
                spend = events.aggregate(total=Sum('cost_usd'))['total'] or Decimal('0')

            threshold = g.budget_usd * Decimal(str(g.alert_threshold_pct)) / Decimal('100')
            pct = (spend / g.budget_usd * 100) if g.budget_usd else Decimal('0')

            if spend >= g.budget_usd:
                alerts.append({
                    'name': g.name, 'spend': spend, 'budget': g.budget_usd,
                    'pct': pct, 'status': 'EXCEEDED', 'scope': g.get_scope_display(),
                })
            elif spend >= threshold:
                alerts.append({
                    'name': g.name, 'spend': spend, 'budget': g.budget_usd,
                    'pct': pct, 'status': 'WARNING', 'scope': g.get_scope_display(),
                })

        return alerts


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


# ──────────────────────────────────────────────────────────────
# Phase 3: Charts, Audit Ledger, CSV Export, Power User Diagnostics
# ──────────────────────────────────────────────────────────────

class DailyChartDataView(OwnerOnlyMixin, View):
    """JSON API returning daily cost data for Chart.js."""

    def get(self, request):
        _, _, days = _parse_date_range(request)
        today = date.today()
        start = today - timedelta(days=days)

        # Try rollup table first, fall back to live query
        rollups = (
            DailyCostRollup.objects
            .filter(date__gte=start, user__isnull=True, feature__isnull=True)
            .order_by('date')
        )

        if rollups.exists():
            labels = [str(r.date) for r in rollups]
            costs = [float(r.total_cost_usd) for r in rollups]
            calls = [r.total_calls for r in rollups]
        else:
            # Live query from events
            labels, costs, calls = [], [], []
            for d in range(days):
                day = start + timedelta(days=d)
                agg = LLMUsageEvent.objects.filter(
                    created_at__date=day,
                ).aggregate(
                    total_cost=Sum('cost_usd'),
                    total_calls=Count('id'),
                )
                labels.append(str(day))
                costs.append(float(agg['total_cost'] or 0))
                calls.append(agg['total_calls'] or 0)

        return JsonResponse({
            'labels': labels,
            'costs': costs,
            'calls': calls,
        })


class AuditLedgerView(OwnerOnlyMixin, TemplateView):
    """Per-call audit ledger with filtering."""

    template_name = 'owner_finance/audit.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        start, end, days = _parse_date_range(self.request)

        events = LLMUsageEvent.objects.filter(
            created_at__range=(start, end),
        ).select_related('user').order_by('-created_at')

        # Optional filters
        feature = self.request.GET.get('feature')
        model = self.request.GET.get('model')
        user_email = self.request.GET.get('user')
        escalated = self.request.GET.get('escalated')

        if feature:
            events = events.filter(feature=feature)
        if model:
            events = events.filter(model_name=model)
        if user_email:
            events = events.filter(user__email__icontains=user_email)
        if escalated == '1':
            events = events.filter(escalated=True)

        ctx['events'] = events[:500]
        ctx['days'] = days
        ctx['filter_feature'] = feature or ''
        ctx['filter_model'] = model or ''
        ctx['filter_user'] = user_email or ''
        ctx['filter_escalated'] = escalated or ''
        ctx['feature_choices'] = LLMUsageEvent.FEATURE_CHOICES
        ctx['model_choices'] = (
            LLMUsageEvent.objects.values_list('model_name', flat=True).distinct()
        )
        return ctx


class ExportCSVView(OwnerOnlyMixin, View):
    """Export LLM usage events as CSV."""

    def get(self, request):
        start, end, days = _parse_date_range(request)

        events = LLMUsageEvent.objects.filter(
            created_at__range=(start, end),
        ).select_related('user').order_by('-created_at')

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="llm_usage_{days}d.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Timestamp', 'User', 'Feature', 'Engine', 'Model',
            'Input Tokens', 'Output Tokens', 'Cost USD', 'Escalated',
            'Request ID',
        ])

        for e in events.iterator():
            writer.writerow([
                e.created_at.isoformat(),
                e.user.email if e.user else 'system',
                e.feature,
                e.engine or '',
                e.model_name,
                e.input_tokens,
                e.output_tokens,
                f'{e.cost_usd:.6f}',
                'Yes' if e.escalated else 'No',
                str(e.request_id),
            ])

        return response


class PowerUserView(OwnerOnlyMixin, TemplateView):
    """Deep-dive diagnostics for a single user."""

    template_name = 'owner_finance/power_user.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user_id = self.kwargs.get('user_id')
        start, end, days = _parse_date_range(self.request)

        events = LLMUsageEvent.objects.filter(
            created_at__range=(start, end),
            user_id=user_id,
        )

        agg = events.aggregate(
            total_cost=Sum('cost_usd'),
            total_calls=Count('id'),
            total_input=Sum('input_tokens'),
            total_output=Sum('output_tokens'),
            escalated_calls=Count('id', filter=Q(escalated=True)),
        )

        # By feature breakdown
        by_feature = (
            events.values('feature')
            .annotate(total_cost=Sum('cost_usd'), total_calls=Count('id'))
            .order_by('-total_cost')
        )

        # By model breakdown
        by_model = (
            events.values('model_name')
            .annotate(total_cost=Sum('cost_usd'), total_calls=Count('id'))
            .order_by('-total_cost')
        )

        # Recent calls
        recent = events.select_related('user').order_by('-created_at')[:50]

        # User info
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            target_user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            target_user = None

        # Subscription snapshot
        snap = UserSubscriptionSnapshot.objects.filter(
            user_id=user_id,
            effective_start__lte=end,
        ).filter(
            Q(effective_end__isnull=True) | Q(effective_end__gte=start),
        ).first()

        ctx.update({
            'target_user': target_user,
            'agg': agg,
            'by_feature': by_feature,
            'by_model': by_model,
            'recent': recent,
            'snap': snap,
            'days': days,
        })
        return ctx


# ──────────────────────────────────────────────────────────────
# Phase 4: Scenario Simulator
# ──────────────────────────────────────────────────────────────

class SimulatorView(OwnerOnlyMixin, TemplateView):
    """What-if scenario simulator for cost/revenue projections."""

    template_name = 'owner_finance/simulator.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['result'] = None
        ctx['form_data'] = {}
        return ctx

    def post(self, request, *args, **kwargs):
        from .services.simulator import simulate_scenario

        ctx = self.get_context_data(**kwargs)

        try:
            form_data = {
                'user_count': int(request.POST.get('user_count', 100)),
                'avg_interactions': float(request.POST.get('avg_interactions', 3.0)),
                'escalation_rate': float(request.POST.get('escalation_rate', 0.15)),
                'gpt4o_pct': float(request.POST.get('gpt4o_pct', 0.1)),
                'gpt4o_mini_pct': float(request.POST.get('gpt4o_mini_pct', 0.9)),
                'free_pct': float(request.POST.get('free_pct', 0.6)),
                'student_pct': float(request.POST.get('student_pct', 0.2)),
                'adult_pct': float(request.POST.get('adult_pct', 0.2)),
                'student_price': request.POST.get('student_price', '3.99'),
                'adult_price': request.POST.get('adult_price', '7.99'),
            }
            ctx['form_data'] = form_data

            result = simulate_scenario(
                user_count=form_data['user_count'],
                avg_interactions_per_day=form_data['avg_interactions'],
                escalation_rate=form_data['escalation_rate'],
                model_mix={
                    'gpt-4o': form_data['gpt4o_pct'],
                    'gpt-4o-mini': form_data['gpt4o_mini_pct'],
                },
                tier_mix={
                    'FREE': form_data['free_pct'],
                    'STUDENT': form_data['student_pct'],
                    'ADULT': form_data['adult_pct'],
                },
                tier_prices={
                    'FREE': Decimal('0'),
                    'STUDENT': Decimal(form_data['student_price']),
                    'ADULT': Decimal(form_data['adult_price']),
                },
            )
            ctx['result'] = result
        except Exception as e:
            ctx['error'] = str(e)

        return self.render_to_response(ctx)


# ──────────────────────────────────────────────────────────────
# Phase 5: Budget Guardrails Management
# ──────────────────────────────────────────────────────────────

class BudgetGuardrailsView(OwnerOnlyMixin, TemplateView):
    """View and manage budget guardrails with current spend status."""

    template_name = 'owner_finance/budgets.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = date.today()
        guardrails = BudgetGuardrail.objects.all()

        enriched = []
        for g in guardrails:
            if g.period == 'MONTHLY':
                period_start = today.replace(day=1)
            else:
                period_start = today

            events = LLMUsageEvent.objects.filter(created_at__date__gte=period_start)

            if g.scope == 'PER_FEATURE' and g.scope_value:
                events = events.filter(feature=g.scope_value)

            if g.scope == 'PER_USER':
                user_spend = (
                    events.filter(user__isnull=False)
                    .values('user')
                    .annotate(total=Sum('cost_usd'))
                    .order_by('-total')
                    .first()
                )
                spend = user_spend['total'] if user_spend else Decimal('0')
            else:
                spend = events.aggregate(total=Sum('cost_usd'))['total'] or Decimal('0')

            pct = (spend / g.budget_usd * 100) if g.budget_usd else Decimal('0')
            threshold = g.budget_usd * Decimal(str(g.alert_threshold_pct)) / Decimal('100')

            if spend >= g.budget_usd:
                status = 'EXCEEDED'
            elif spend >= threshold:
                status = 'WARNING'
            else:
                status = 'OK'

            enriched.append({
                'guardrail': g,
                'spend': spend,
                'pct': pct,
                'status': status,
            })

        ctx['guardrails'] = enriched
        ctx['feature_choices'] = LLMUsageEvent.FEATURE_CHOICES
        return ctx
