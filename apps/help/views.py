"""
Help System Views

Contains:
1. Context-Aware Help API - Fetches help content by context ID
2. WLJ Assistant Chat Bot - Chat interface and API endpoints
"""

import json
import logging
import os
import markdown
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib.auth.decorators import login_required

from .models import HelpTopic, AdminHelpTopic, HelpArticle, HelpCategory, HelpConversation, HelpMessage
from .services import HelpChatService, TeachingToolService


@method_decorator(login_required, name='dispatch')
class HelpTopicAPIView(View):
    """
    API endpoint for fetching user-facing help content.

    GET /help/api/topic/<context_id>/
    Returns JSON with help content for the given context.

    Contextual Fallback:
    If a specific help topic doesn't exist (e.g., HEALTH_HEART_RATE),
    the API will try to fall back to the module's home topic (e.g., HEALTH_HOME).
    This ensures users always see relevant help for their current module.
    """

    # Map context_id prefixes to their module home context_ids
    MODULE_FALLBACKS = {
        'BRAIN_TRAINING_': 'HEALTH_COGNITIVE_HUB',
        'HEALTH_COGNITIVE_': 'HEALTH_COGNITIVE_HUB',
        'HEALTH_': 'HEALTH_HOME',
        'JOURNAL_': 'JOURNAL_HOME',
        'FAITH_': 'FAITH_HOME',
        'LIFE_': 'LIFE_HOME',
        'PURPOSE_': 'PURPOSE_HOME',
        'DASHBOARD_': 'DASHBOARD_HOME',
        'SETTINGS_': 'SETTINGS_PREFERENCES',
        'NUTRITION_': 'NUTRITION_HOME',
        'GLUCOSE_': 'GLUCOSE_DASHBOARD',
        'ADMIN_CONSOLE_': 'ADMIN_CONSOLE_HOME',
        'SCAN_': 'SCAN_HOME',
        'ASSISTANT_': 'ASSISTANT_HOME',
        'FINANCE_': 'FINANCE_HOME',
        'CAPTURE_': 'CAPTURE_HOME',
        'MEALS_': 'MEALS_DASHBOARD',
        'MEDICAL_': 'MEDICAL_LABS_SUMMARY',
        'RELATIONSHIPS_': 'RELATIONSHIPS_PEOPLE',
        'BILLING_': 'BILLING_SETTINGS',
        'CORE_': 'DASHBOARD_HOME',
        'SMS_': 'SMS_HISTORY',
        'NOTES_': 'NOTES_HOME',
    }

    def get(self, request, context_id):
        topic = HelpTopic.get_by_context(context_id)

        # If specific topic not found, try module fallback
        if topic is None:
            fallback_context = self._get_fallback_context(context_id)
            if fallback_context and fallback_context != context_id:
                topic = HelpTopic.get_by_context(fallback_context)

        # Last resort: read directly from the fixture file
        # Try the exact context_id first, then the module fallback
        if topic is None:
            fixture_data = self._load_from_fixture(context_id)
            if not fixture_data:
                fallback_context = self._get_fallback_context(context_id)
                if fallback_context and fallback_context != context_id:
                    fixture_data = self._load_from_fixture(fallback_context)
            if fixture_data:
                md = markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists'])
                return JsonResponse({
                    'found': True,
                    'context_id': fixture_data['context_id'],
                    'help_id': fixture_data.get('help_id', ''),
                    'title': fixture_data['title'],
                    'description': fixture_data.get('description', ''),
                    'content': md.convert(fixture_data.get('content', '')),
                    'app_name': fixture_data.get('app_name', ''),
                    'related': []
                })

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

    def _get_fallback_context(self, context_id):
        """
        Get the fallback context_id for module-level help.

        For example:
        - HEALTH_HEART_RATE -> HEALTH_HOME
        - JOURNAL_ENTRY_CREATE -> JOURNAL_HOME
        - GLUCOSE_LIST -> GLUCOSE_DASHBOARD
        """
        for prefix, fallback in self.MODULE_FALLBACKS.items():
            if context_id.startswith(prefix):
                return fallback

    # In-memory cache for fixture data (loaded once per worker)
    _fixture_cache = None

    @classmethod
    def _load_from_fixture(cls, context_id):
        """
        Fallback: read help topic directly from the fixture JSON file.

        Used when a topic exists in the fixture file but hasn't been loaded
        into the database yet (e.g., first deploy after adding new topics).
        Data is cached in memory to avoid repeated file reads.
        """
        logger = logging.getLogger(__name__)
        if cls._fixture_cache is None:
            fixture_path = os.path.join(
                settings.BASE_DIR, 'apps', 'help', 'fixtures', 'help_topics.json'
            )
            try:
                with open(fixture_path, 'r') as f:
                    raw = json.load(f)
                cls._fixture_cache = {
                    entry['fields']['context_id']: entry['fields']
                    for entry in raw
                    if entry.get('model') == 'help.helptopic'
                    and entry.get('fields', {}).get('is_active', True)
                }
                logger.info(f'Help fixture fallback: loaded {len(cls._fixture_cache)} topics from file')
            except Exception as e:
                logger.warning(f'Help fixture fallback: failed to read fixture file: {e}')
                cls._fixture_cache = {}

        return cls._fixture_cache.get(context_id)
        return None


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


# =============================================================================
# WLJ ASSISTANT CHAT BOT
# =============================================================================


class HelpCenterView(LoginRequiredMixin, View):
    """Main help center page with categories and search."""

    def get(self, request):
        categories = HelpCategory.objects.filter(
            is_active=True
        ).prefetch_related('articles').order_by('sort_order', 'name')

        context = {
            'categories': categories,
        }
        return render(request, 'help/help_center.html', context)


class HelpArticleView(LoginRequiredMixin, View):
    """Individual help article page."""

    def get(self, request, slug):
        article = get_object_or_404(HelpArticle, slug=slug, is_active=True)
        related = article.related_articles.filter(is_active=True)[:3]

        context = {
            'article': article,
            'related_articles': related,
        }
        return render(request, 'help/article.html', context)


class HelpCategoryView(LoginRequiredMixin, View):
    """Articles within a category."""

    def get(self, request, slug):
        category = get_object_or_404(HelpCategory, slug=slug, is_active=True)
        articles = category.articles.filter(is_active=True).order_by('sort_order', 'title')

        context = {
            'category': category,
            'articles': articles,
        }
        return render(request, 'help/category.html', context)


# =============================================================================
# Chat API Endpoints
# =============================================================================

class ChatStartView(LoginRequiredMixin, View):
    """Start a new chat conversation."""

    def post(self, request):
        # Parse request body
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            data = {}

        context_module = data.get('module', '')
        context_url = data.get('url', '')

        # Create new conversation
        conversation = HelpConversation.objects.create(
            user=request.user,
            context_module=context_module,
            context_url=context_url
        )

        # Get welcome message with user's coaching style
        service = HelpChatService(request.user)
        welcome_message = service.get_welcome_message()

        # Save welcome message
        HelpMessage.objects.create(
            conversation=conversation,
            content=welcome_message,
            is_user=False
        )

        return JsonResponse({
            'conversation_id': conversation.id,
            'message': welcome_message,
        })


class ChatMessageView(LoginRequiredMixin, View):
    """Send a message and get a response."""

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        conversation_id = data.get('conversation_id')
        user_message = data.get('message', '').strip()

        if not conversation_id:
            return JsonResponse({'error': 'Missing conversation_id'}, status=400)

        if not user_message:
            return JsonResponse({'error': 'Empty message'}, status=400)

        # Get conversation
        try:
            conversation = HelpConversation.objects.get(
                id=conversation_id,
                user=request.user
            )
        except HelpConversation.DoesNotExist:
            return JsonResponse({'error': 'Conversation not found'}, status=404)

        # Save user message
        HelpMessage.objects.create(
            conversation=conversation,
            content=user_message,
            is_user=True
        )

        # Generate response
        service = HelpChatService(request.user)
        response = service.generate_response(
            query=user_message,
            context_module=conversation.context_module
        )

        # Save assistant message
        assistant_msg = HelpMessage.objects.create(
            conversation=conversation,
            content=response['message'],
            is_user=False
        )

        # Link source articles
        if response['articles']:
            assistant_msg.source_articles.set(response['articles'])

        # Update last activity
        conversation.last_activity = timezone.now()
        conversation.save(update_fields=['last_activity'])

        return JsonResponse({
            'message': response['message'],
            'article_count': len(response['articles']),
        })


class ChatEndView(LoginRequiredMixin, View):
    """End a chat conversation with optional email export."""

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        conversation_id = data.get('conversation_id')
        send_email = data.get('send_email', False)

        if not conversation_id:
            return JsonResponse({'error': 'Missing conversation_id'}, status=400)

        # Get conversation
        try:
            conversation = HelpConversation.objects.get(
                id=conversation_id,
                user=request.user
            )
        except HelpConversation.DoesNotExist:
            return JsonResponse({'error': 'Conversation not found'}, status=404)

        email_sent = False

        # Send email if requested
        if send_email:
            email_sent = self._send_conversation_email(conversation)

        # Get closing message
        service = HelpChatService(request.user)
        closing_message = service.get_closing_message()

        # Delete conversation and messages
        conversation.delete()

        return JsonResponse({
            'success': True,
            'email_sent': email_sent,
            'message': closing_message,
        })

    def _send_conversation_email(self, conversation):
        """Send the conversation transcript to the user."""
        try:
            user = conversation.user
            messages_text = conversation.get_messages_for_email()

            subject = f"Your WLJ Assistant Chat - {conversation.started_at.strftime('%B %d, %Y')}"

            # Build email body
            body = f"""Hello {user.first_name or 'there'},

Here's a transcript of your recent chat with the WLJ Assistant:

{'=' * 50}

{messages_text}

{'=' * 50}

If you have more questions, you can always start a new chat from the help button in Whole Life Journey.

Best regards,
The Whole Life Journey Team
"""

            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False
            )

            # Mark as emailed (even though we're about to delete)
            conversation.emailed_at = timezone.now()
            conversation.save(update_fields=['emailed_at'])

            return True

        except Exception as e:
            print(f"Error sending chat email: {e}")
            return False


class ChatSearchView(LoginRequiredMixin, View):
    """Search help articles (for autocomplete/suggestions)."""

    def get(self, request):
        query = request.GET.get('q', '').strip()
        module = request.GET.get('module', '')

        if len(query) < 2:
            return JsonResponse({'results': []})

        service = HelpChatService(request.user)
        articles = service.search_articles(query, module=module, limit=5)

        results = [
            {
                'id': article.id,
                'title': article.title,
                'summary': article.summary,
                'module': article.module,
                'url': f'/help/article/{article.slug}/',
            }
            for article in articles
        ]

        return JsonResponse({'results': results})


class ChatSuggestionsView(LoginRequiredMixin, View):
    """Get suggested topics for current module."""

    def get(self, request):
        module = request.GET.get('module', 'general')

        service = HelpChatService(request.user)
        articles = service.get_suggestions_for_module(module)

        suggestions = [
            {
                'id': article.id,
                'title': article.title,
                'summary': article.summary,
            }
            for article in articles
        ]

        return JsonResponse({'suggestions': suggestions})


# =============================================================================
# Teaching Tool API Endpoints
# =============================================================================


class TeachingToolSearchView(LoginRequiredMixin, View):
    """
    API endpoint for the Teaching Tool.

    GET /help/api/teaching/search/?q=<query>
    Returns a destination and suggestions for navigation questions.
    """

    def get(self, request):
        query = request.GET.get('q', '').strip()

        service = TeachingToolService()
        result = service.search(query)

        return JsonResponse(result)


class TeachingToolSuggestionsView(LoginRequiredMixin, View):
    """
    API endpoint for popular destination suggestions.

    GET /help/api/teaching/suggestions/
    Returns a list of popular destinations for display.
    """

    def get(self, request):
        limit = int(request.GET.get('limit', 5))

        service = TeachingToolService()
        destinations = service.get_popular_destinations(limit=limit)

        return JsonResponse({'destinations': destinations})
