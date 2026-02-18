"""
Whole Life Journey - Blueprint API Views

Project: Whole Life Journey
Path: apps/core/blueprint/api.py
Purpose: API endpoints for reading/updating the Personal Operating Blueprint

Endpoints:
    GET  /api/blueprint/           - Get current blueprint
    PUT  /api/blueprint/           - Update blueprint
    GET  /api/blueprint/explain/   - Transparency view of what drives guidance
    POST /api/blueprint/sync/      - Sync module flags from preferences
    GET  /api/blueprint/non-negotiables/ - List non-negotiables
    POST /api/blueprint/non-negotiables/ - Add a non-negotiable
    PUT  /api/blueprint/non-negotiables/<id>/ - Update a non-negotiable
    DELETE /api/blueprint/non-negotiables/<id>/ - Remove a non-negotiable

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import json
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect

from . import engine
from .models import NonNegotiable

logger = logging.getLogger(__name__)


class BlueprintView(LoginRequiredMixin, View):
    """GET/PUT the user's Personal Operating Blueprint."""

    def get(self, request):
        blueprint = engine.get_blueprint(request.user)
        return JsonResponse({
            'success': True,
            'blueprint': {
                'operating_style': blueprint.operating_style,
                'persona_id': blueprint.persona_id,
                'interruption_tolerance': blueprint.interruption_tolerance,
                'auto_architect_enabled': blueprint.auto_architect_enabled,
                'tier1_protected_behaviors': blueprint.tier1_protected_behaviors,
                'pillars_ranked': blueprint.pillars_ranked,
                'sleep_target_minutes': blueprint.sleep_target_minutes,
                'wake_time_policy': blueprint.wake_time_policy,
                'preferred_architecture_time': str(blueprint.preferred_architecture_time),
                'override_policy': blueprint.override_policy,
                'module_flags': blueprint.module_flags_snapshot,
                'sub_feature_flags': blueprint.sub_feature_flags_snapshot,
                'last_architecture_run_at': (
                    blueprint.last_architecture_run_at.isoformat()
                    if blueprint.last_architecture_run_at else None
                ),
                'version': blueprint.version,
            },
        })

    @method_decorator(csrf_protect)
    def put(self, request):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        blueprint = engine.update_blueprint(request.user, data)
        return JsonResponse({
            'success': True,
            'version': blueprint.version,
        })


class BlueprintExplainView(LoginRequiredMixin, View):
    """GET transparency view of what's currently driving guidance."""

    def get(self, request):
        explanation = engine.explain_blueprint(request.user)
        return JsonResponse({
            'success': True,
            'explanation': explanation,
        })


class BlueprintSyncView(LoginRequiredMixin, View):
    """POST to sync module flags from user preferences."""

    @method_decorator(csrf_protect)
    def post(self, request):
        engine.sync_flags(request.user)
        return JsonResponse({'success': True})


class NonNegotiableListView(LoginRequiredMixin, View):
    """GET/POST non-negotiables."""

    def get(self, request):
        blueprint = engine.get_blueprint(request.user)
        non_negotiables = blueprint.non_negotiables.filter(is_active=True)
        items = []
        for nn in non_negotiables:
            items.append({
                'id': nn.id,
                'behavior_key': nn.behavior_key,
                'display_name': nn.display_name,
                'pillar': nn.pillar,
                'min_duration_minutes': nn.min_duration_minutes,
                'preferred_time_window_start': (
                    str(nn.preferred_time_window_start) if nn.preferred_time_window_start else None
                ),
                'preferred_time_window_end': (
                    str(nn.preferred_time_window_end) if nn.preferred_time_window_end else None
                ),
                'frequency': nn.frequency,
                'custom_days': nn.custom_days,
                'hard_deadline': str(nn.hard_deadline) if nn.hard_deadline else None,
                'module_key': nn.module_key,
                'feature_key': nn.feature_key,
                'sort_order': nn.sort_order,
                'tier': blueprint.get_tier_for_behavior(nn.behavior_key),
            })
        return JsonResponse({'success': True, 'non_negotiables': items})

    @method_decorator(csrf_protect)
    def post(self, request):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        blueprint = engine.get_blueprint(request.user)

        required_fields = ['behavior_key', 'display_name']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse(
                    {'success': False, 'error': f'Missing required field: {field}'},
                    status=400,
                )

        # Check for duplicate
        if blueprint.non_negotiables.filter(
            behavior_key=data['behavior_key'], is_active=True
        ).exists():
            return JsonResponse(
                {'success': False, 'error': 'Non-negotiable with this behavior key already exists'},
                status=400,
            )

        nn = NonNegotiable.objects.create(
            blueprint=blueprint,
            behavior_key=data['behavior_key'],
            display_name=data['display_name'],
            pillar=data.get('pillar', ''),
            min_duration_minutes=data.get('min_duration_minutes', 30),
            frequency=data.get('frequency', NonNegotiable.FREQUENCY_DAILY),
            custom_days=data.get('custom_days', []),
            module_key=data.get('module_key', ''),
            feature_key=data.get('feature_key', ''),
            sort_order=data.get('sort_order', 0),
        )

        # Handle time fields
        if data.get('preferred_time_window_start'):
            nn.preferred_time_window_start = data['preferred_time_window_start']
        if data.get('preferred_time_window_end'):
            nn.preferred_time_window_end = data['preferred_time_window_end']
        if data.get('hard_deadline'):
            nn.hard_deadline = data['hard_deadline']
        nn.save()

        return JsonResponse({'success': True, 'id': nn.id}, status=201)


class NonNegotiableDetailView(LoginRequiredMixin, View):
    """PUT/DELETE a specific non-negotiable."""

    @method_decorator(csrf_protect)
    def put(self, request, pk):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        blueprint = engine.get_blueprint(request.user)
        try:
            nn = blueprint.non_negotiables.get(pk=pk)
        except NonNegotiable.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Not found'}, status=404)

        updatable = [
            'display_name', 'pillar', 'min_duration_minutes', 'frequency',
            'custom_days', 'module_key', 'feature_key', 'sort_order',
            'preferred_time_window_start', 'preferred_time_window_end', 'hard_deadline',
        ]

        for field in updatable:
            if field in data:
                setattr(nn, field, data[field])

        nn.save()
        return JsonResponse({'success': True})

    @method_decorator(csrf_protect)
    def delete(self, request, pk):
        blueprint = engine.get_blueprint(request.user)
        try:
            nn = blueprint.non_negotiables.get(pk=pk)
        except NonNegotiable.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Not found'}, status=404)

        nn.is_active = False
        nn.save(update_fields=['is_active', 'updated_at'])
        return JsonResponse({'success': True})
