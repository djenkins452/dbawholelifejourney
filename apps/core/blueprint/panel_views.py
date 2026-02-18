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
                    'start_time': block.start_time.strftime('%H:%M'),
                    'end_time': block.end_time.strftime('%H:%M'),
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
                'Generating plan...'
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

        # Determine level
        if score < 20:
            level = 'low'
            label = 'Stable'
        elif score < 50:
            level = 'medium'
            label = 'Moderate'
        else:
            level = 'high'
            label = 'Elevated'

        html = (
            f'<div class="drift-indicator drift-score-{level}">'
            f'<div class="drift-bar"><div class="drift-bar-fill" style="width:{min(100, score)}%"></div></div>'
            f'<span class="drift-value">{score:.0f}</span>'
            f'</div>'
            f'<div style="font-size:var(--font-size-xs);color:var(--color-text-muted);margin-top:4px;">'
            f'{label} &middot; {summary.get("total_events", 0)} events (7d)'
            f'</div>'
        )

        if p24 > 50:
            html += (
                f'<div class="cos-alert cos-alert-warning" style="margin-top:var(--space-2);">'
                f'24h drift risk: {p24:.0f}%'
                f'</div>'
            )

        return HttpResponse(html)


class PendingInterventionsView(LoginRequiredMixin, View):
    """Return HTML snippet of pending interventions."""

    def get(self, request):
        pending = intervention_engine.get_pending_interventions(request.user)[:5]

        if not pending.exists():
            return HttpResponse(
                '<div style="font-size:var(--font-size-xs);color:var(--color-text-muted);">'
                'No active alerts</div>'
            )

        html = ''
        for intervention in pending:
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

        # Quick actions
        html += (
            '<div class="assistant-quick-actions" style="margin-top:var(--space-3);">'
            '<button class="assistant-action-btn" onclick="openAssistantChat()">Chat</button>'
            '<button class="assistant-action-btn" onclick="triggerCurveball()">Curveball</button>'
            '<button class="assistant-action-btn" onclick="viewBlueprint()">Blueprint</button>'
            '</div>'
        )

        html += '</div>'

        return HttpResponse(html)
