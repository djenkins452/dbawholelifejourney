"""
Help System Views

API endpoints for fetching help content by context ID.
"""

import markdown
from django.http import JsonResponse
from django.views import View
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from .models import HelpTopic, AdminHelpTopic


@method_decorator(login_required, name='dispatch')
class HelpTopicAPIView(View):
    """
    API endpoint for fetching user-facing help content.

    GET /help/api/topic/<context_id>/
    Returns JSON with help content for the given context.
    """

    def get(self, request, context_id):
        topic = HelpTopic.get_by_context(context_id)

        if topic is None:
            return JsonResponse({
                'found': False,
                'context_id': context_id,
                'title': 'Help Not Available',
                'content': 'No help content is available for this page yet.',
                'related': []
            })

        # Convert Markdown to HTML
        md = markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists'])
        content_html = md.convert(topic.content)

        # Get related topics
        related = []
        for rel in topic.related_topics.filter(is_active=True)[:5]:
            related.append({
                'context_id': rel.context_id,
                'title': rel.title,
            })

        return JsonResponse({
            'found': True,
            'context_id': topic.context_id,
            'help_id': topic.help_id,
            'title': topic.title,
            'description': topic.description,
            'content': content_html,
            'app_name': topic.app_name,
            'related': related
        })


@method_decorator(login_required, name='dispatch')
class AdminHelpTopicAPIView(View):
    """
    API endpoint for fetching admin/technical help content.

    GET /help/api/admin/<context_id>/
    Returns JSON with admin help content for the given context.
    Only accessible to staff users.
    """

    def get(self, request, context_id):
        # Only staff can access admin help
        if not request.user.is_staff:
            return JsonResponse({
                'found': False,
                'error': 'Access denied'
            }, status=403)

        topic = AdminHelpTopic.get_by_context(context_id)

        if topic is None:
            return JsonResponse({
                'found': False,
                'context_id': context_id,
                'title': 'Admin Help Not Available',
                'content': 'No admin help content is available for this page yet.',
                'related': []
            })

        # Convert Markdown to HTML
        md = markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists'])
        content_html = md.convert(topic.content)

        # Get related topics
        related = []
        for rel in topic.related_topics.filter(is_active=True)[:5]:
            related.append({
                'context_id': rel.context_id,
                'title': rel.title,
            })

        return JsonResponse({
            'found': True,
            'context_id': topic.context_id,
            'help_id': topic.help_id,
            'title': topic.title,
            'description': topic.description,
            'content': content_html,
            'category': topic.category,
            'related': related
        })


@method_decorator(login_required, name='dispatch')
class HelpSearchAPIView(View):
    """
    API endpoint for searching help content.

    GET /help/api/search/?q=<query>&type=<user|admin>
    Returns JSON with matching help topics.
    """

    def get(self, request):
        query = request.GET.get('q', '').strip()
        help_type = request.GET.get('type', 'user')

        if len(query) < 2:
            return JsonResponse({
                'results': [],
                'query': query,
                'error': 'Query must be at least 2 characters'
            })

        if help_type == 'admin':
            # Only staff can search admin help
            if not request.user.is_staff:
                return JsonResponse({
                    'results': [],
                    'error': 'Access denied'
                }, status=403)

            topics = AdminHelpTopic.objects.filter(
                is_active=True
            ).filter(
                models.Q(title__icontains=query) |
                models.Q(description__icontains=query) |
                models.Q(content__icontains=query)
            )[:10]

            results = [{
                'context_id': t.context_id,
                'title': t.title,
                'description': t.description[:100] + '...' if len(t.description) > 100 else t.description,
                'category': t.category,
            } for t in topics]
        else:
            topics = HelpTopic.objects.filter(
                is_active=True
            ).filter(
                models.Q(title__icontains=query) |
                models.Q(description__icontains=query) |
                models.Q(content__icontains=query)
            )[:10]

            results = [{
                'context_id': t.context_id,
                'title': t.title,
                'description': t.description[:100] + '...' if len(t.description) > 100 else t.description,
                'app_name': t.app_name,
            } for t in topics]

        return JsonResponse({
            'results': results,
            'query': query,
            'count': len(results)
        })


# Add missing import for Q
from django.db import models
