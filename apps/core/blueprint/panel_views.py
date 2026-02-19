"""
Whole Life Journey - Assistant Panel Views

Project: Whole Life Journey
Path: apps/core/blueprint/panel_views.py
Purpose: HTMX endpoints for the assistant panel sections

Description:
    Provides lightweight endpoints that return HTML snippets for the
    assistant panel sections: today's plan, drift summary, pending
    interventions, and mobile panel content.

Endpoints:
    GET  /api/blueprint/plan/today/          - Today's plan blocks (HTML)
    GET  /api/blueprint/drift/summary/       - Drift summary (HTML)
    GET  /api/blueprint/interventions/pending/ - Pending interventions (HTML)
    GET  /api/blueprint/interventions/check/  - Check for new interventions (JSON)
    POST /api/blueprint/interventions/<id>/respond/ - Respond to intervention (JSON)
    POST /api/blueprint/curveball/           - Handle curveball event (JSON)
    GET  /api/blueprint/panel/mobile/        - Mobile panel content (HTML)

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import json
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect

from . import engine as blueprint_engine
from . import architecture_engine
from . import drift_engine
from . import intervention_engine
from .models import ArchitecturePlan, InterventionLog

logger = logging.getLogger(__name__)


class TodayPlanView(LoginRequiredMixin, View):
    """Return HTML snippet of today's plan blocks."""

    def get(self, request):
        plan = ArchitecturePlan.get_active_for_date(request.user)

        # Auto-generate if no plan exists
        if not plan:
            try:
                from . import engine as blueprint_engine
                blueprint = blueprint_engine.get_blueprint(request.user)
                if getattr(blueprint, 'auto_architect_enabled', True):
                    plan = architecture_engine.run_architecture_pass(
                        request.user,
                        target_date=timezone.localdate(),
                    )
            except Exception:
                pass

        blocks = []
        if plan:
            for block in plan.blocks.all():
                blocks.append({
                    'start_time': block.start_time.strftime('%-I:%M %p'),
                    'end_time': block.end_time.strftime('%-I:%M %p'),
                    'title': block.title,
                    'tier': block.tier,
                    'is_completed': block.is_completed,
                    'is_locked': block.is_locked,
                })

        html = ''
        if blocks:
            for b in blocks:
                completed_class = ' completed' if b['is_completed'] else ''
                tier_class = f'tier-{b["tier"]}'
                html += (
                    f'<div class="plan-block{completed_class}">'
                    f'<span class="plan-block-time">{b["start_time"]}</span>'
                    f'<span class="plan-block-title">{b["title"]}</span>'
                    f'<span class="plan-block-tier {tier_class}">T{b["tier"]}</span>'
                    f'</div>'
                )
        else:
            html = (
                '<div style="font-size:var(--font-size-xs);'
                'color:var(--color-text-muted);">'
                'Architecture initializing. Auto-generation in progress.'
                '</div>'
            )

        return HttpResponse(html)


class DriftSummaryView(LoginRequiredMixin, View):
    """Return HTML snippet of drift status."""

    def get(self, request):
        try:
            summary = drift_engine.get_drift_summary(request.user, days=7)
        except Exception:
            summary = {'average_score': 0, 'total_events': 0}

        score = summary.get('average_score', 0)
        prediction = summary.get('latest_prediction', {})
        p24 = prediction.get('probability_24h', 0) * 100
        total_events = summary.get('total_events', 0)

        # Determine level and human-readable description
        if score < 20:
            level = 'low'
            label = 'On Track'
            description = (
                "You're staying close to your plan."
                if total_events > 0
                else "No activity logged yet this week."
            )
        elif score < 50:
            level = 'medium'
            label = 'Drifting Slightly'
            description = "You've missed a few things — nothing major, but worth a look."
        else:
            level = 'high'
            label = 'Off Course'
            description = "You've strayed from your plan. Consider re-focusing on priorities."

        html = (
            f'<div style="margin-bottom:6px;">'
            f'<span style="font-weight:600;color:var(--color-text);">{label}</span>'
            f'</div>'
            f'<div class="drift-indicator drift-score-{level}">'
            f'<div class="drift-bar"><div class="drift-bar-fill" style="width:{max(5, min(100, score))}%"></div></div>'
            f'</div>'
            f'<div style="font-size:var(--font-size-xs);color:var(--color-text-muted);margin-top:6px;line-height:1.4;">'
            f'{description}'
            f'</div>'
        )

        if p24 > 50:
            html += (
                f'<div class="cos-alert cos-alert-warning" style="margin-top:var(--space-2);">'
                f'Heads up — you may drift further in the next 24 hours.'
                f'</div>'
            )

        return HttpResponse(html)


class PendingInterventionsView(LoginRequiredMixin, View):
    """Return HTML snippet of pending interventions."""

    def get(self, request):
        # Only show recent alerts (today + yesterday) — stale alerts aren't useful
        import datetime
        cutoff = timezone.now() - datetime.timedelta(days=1)
        pending = intervention_engine.get_pending_interventions(
            request.user,
        ).filter(created_at__gte=cutoff)[:10]

        if not pending.exists():
            return HttpResponse(
                '<div style="font-size:var(--font-size-xs);color:var(--color-text-muted);">'
                'Nothing needs your attention right now.</div>'
            )

        # Deduplicate by message content — keep the most recent of each
        seen_messages = {}
        for intervention in pending:
            # Normalize message for comparison (strip whitespace, lowercase)
            key = intervention.message.strip().lower()[:100]
            if key not in seen_messages:
                seen_messages[key] = intervention

        unique_interventions = list(seen_messages.values())[:5]

        html = ''
        for intervention in unique_interventions:
            level_colors = {0: 'info', 1: 'info', 2: 'warning', 3: 'warning', 4: 'danger'}
            alert_class = level_colors.get(intervention.level, 'info')
            html += (
                f'<div class="cos-alert cos-alert-{alert_class}">'
                f'{intervention.message}'
                f'</div>'
            )

        return HttpResponse(html)


class InterventionCheckView(LoginRequiredMixin, View):
    """JSON endpoint to check for new interventions (polled by panel)."""

    def get(self, request):
        pending = intervention_engine.get_pending_interventions(request.user)
        count = pending.count()

        # Check for friction gates
        friction_gate = pending.filter(
            level=InterventionLog.LEVEL_FRICTION_GATE,
        ).first()

        friction_data = None
        if friction_gate:
            friction_data = {
                'intervention_id': friction_gate.pk,
                'message': friction_gate.message,
                'identity_cost': friction_gate.evidence.get('identity_cost', 0),
                'options': [
                    {'key': 'proceeded', 'label': 'Proceed', 'style': 'danger'},
                    {'key': 'accepted', 'label': 'Keep going', 'style': 'primary'},
                    {'key': 'adjusted', 'label': 'Adjust plan', 'style': 'secondary'},
                ],
            }

        should_ping = pending.filter(
            level__gte=InterventionLog.LEVEL_PING,
        ).exists()

        return JsonResponse({
            'count': count,
            'friction_gate': friction_data,
            'should_ping': should_ping,
        })


class InterventionRespondView(LoginRequiredMixin, View):
    """POST to respond to an intervention."""

    @method_decorator(csrf_protect)
    def post(self, request, pk):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        response = data.get('response')
        if response not in [
            InterventionLog.RESPONSE_ACCEPTED,
            InterventionLog.RESPONSE_DISMISSED,
            InterventionLog.RESPONSE_PROCEEDED,
            InterventionLog.RESPONSE_ADJUSTED,
        ]:
            return JsonResponse({'success': False, 'error': 'Invalid response'}, status=400)

        result = intervention_engine.record_intervention_response(
            pk, response, user=request.user,
        )

        if result is None:
            return JsonResponse({'success': False, 'error': 'Not found'}, status=404)

        return JsonResponse({'success': True})


class CurveballView(LoginRequiredMixin, View):
    """POST to handle a curveball event."""

    @method_decorator(csrf_protect)
    def post(self, request):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        description = data.get('description', '')
        if not description:
            return JsonResponse({'success': False, 'error': 'Description required'}, status=400)

        try:
            plan = architecture_engine.handle_curveball(
                request.user,
                description=description,
                new_event_duration_minutes=data.get('duration_minutes', 60),
            )
            return JsonResponse({
                'success': True,
                'plan_id': plan.pk,
                'blocks_count': plan.blocks.count(),
            })
        except Exception as e:
            logger.exception("Curveball handling failed for %s", request.user.email)
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


class MobilePanelView(LoginRequiredMixin, View):
    """Return full mobile panel content (HTML)."""

    def get(self, request):
        # Aggregate content for mobile
        plan = ArchitecturePlan.get_active_for_date(request.user)
        pending_count = intervention_engine.get_pending_interventions(request.user).count()

        html = '<div class="assistant-section-content">'

        # Quick stats
        html += '<div class="snapshot-strip">'
        if plan:
            block_count = plan.blocks.count()
            completed = plan.blocks.filter(is_completed=True).count()
            html += (
                f'<div class="snapshot-item">'
                f'<span class="snapshot-item-value">{completed}/{block_count}</span>'
                f'<span class="snapshot-item-label">Blocks</span>'
                f'</div>'
            )

        if pending_count > 0:
            html += (
                f'<div class="snapshot-item">'
                f'<span class="snapshot-item-value">{pending_count}</span>'
                f'<span class="snapshot-item-label">Alerts</span>'
                f'</div>'
            )

        try:
            summary = drift_engine.get_drift_summary(request.user, days=7)
            html += (
                f'<div class="snapshot-item">'
                f'<span class="snapshot-item-value">{summary.get("average_score", 0):.0f}</span>'
                f'<span class="snapshot-item-label">Drift</span>'
                f'</div>'
            )
        except Exception:
            pass

        html += '</div>'  # snapshot-strip

        # Quick actions (use data-action for CSP-compliant delegation)
        html += (
            '<div class="assistant-quick-actions" style="margin-top:var(--space-3);">'
            '<button class="assistant-action-btn" data-action="open-assistant-chat">Chat</button>'
            '<button class="assistant-action-btn" data-action="trigger-curveball">Curveball</button>'
            '<button class="assistant-action-btn" data-action="view-blueprint">Blueprint</button>'
            '</div>'
        )

        html += '</div>'

        return HttpResponse(html)
