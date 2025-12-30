# ==============================================================================
# File: views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Dashboard AI Personal Assistant API endpoints and views
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29 (removed chat history display on page load)
# ==============================================================================
"""
Dashboard AI Personal Assistant Views

API endpoints for:
- Opening message / daily check-in
- Conversation / chat
- Daily priorities
- Trend analysis
- Reflection prompts
- State assessment
"""

import json
import logging
from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from .models import (
    AssistantConversation, AssistantMessage, DailyPriority,
    TrendAnalysis, ReflectionPromptQueue, UserStateSnapshot
)
from .personal_assistant import PersonalAssistant, get_personal_assistant
from .trend_tracking import TrendTracker, get_trend_tracker
from .services import AIService

logger = logging.getLogger(__name__)


class AssistantMixin:
    """Mixin providing common assistant functionality."""

    def get_assistant(self):
        """Get personal assistant for current user."""
        return get_personal_assistant(self.request.user)

    def get_tracker(self):
        """Get trend tracker for current user."""
        return get_trend_tracker(self.request.user)

    def check_ai_enabled(self):
        """Check if user has AI enabled and consented."""
        user = self.request.user
        prefs = user.preferences

        if not prefs.ai_enabled:
            return False, "AI features are not enabled. Enable them in Preferences."

        if not AIService.check_user_consent(user):
            return False, "AI data processing consent required. Update in Preferences."

        return True, None

    def check_personal_assistant_enabled(self):
        """
        Check if user has Personal Assistant module enabled and consented.

        Personal Assistant requires:
        1. AI Features enabled (ai_enabled)
        2. AI Data Consent (ai_data_consent)
        3. Personal Assistant module enabled (personal_assistant_enabled)
        4. Personal Assistant consent (personal_assistant_consent)

        Returns:
            tuple: (is_enabled, error_message_or_None)
        """
        user = self.request.user
        prefs = user.preferences

        # First check AI prerequisites
        if not prefs.ai_enabled:
            return False, "AI Features must be enabled first. Enable AI Features in Preferences."

        if not AIService.check_user_consent(user):
            return False, "AI data processing consent required. Update in Preferences."

        # Check Personal Assistant module
        if not prefs.personal_assistant_enabled:
            return False, "Personal Assistant is not enabled. Enable it in Preferences."

        if not prefs.personal_assistant_consent:
            return False, "Personal Assistant data consent required. Update in Preferences."

        return True, None


# =============================================================================
# OPENING MESSAGE / DAILY CHECK-IN
# =============================================================================

class AssistantOpeningView(LoginRequiredMixin, AssistantMixin, View):
    """
    Get the opening message when user opens the app.

    This is the daily check-in that:
    - Assesses current state
    - Proposes daily priorities
    - Identifies celebrations
    - Provides accountability nudges
    - Offers reflection prompts
    """

    def get(self, request, *args, **kwargs):
        enabled, error = self.check_personal_assistant_enabled()

        if not enabled:
            return JsonResponse({
                'success': False,
                'error': error,
                'fallback': True,
            }, status=200)

        try:
            assistant = self.get_assistant()
            opening = assistant.get_opening_message()

            return JsonResponse({
                'success': True,
                'greeting': opening['greeting'],
                'state_summary': opening['state_summary'],
                'priorities': list(opening['priorities']),
                'celebrations': opening['celebrations'],
                'nudges': opening['nudges'],
                'reflection_prompt': opening['reflection_prompt'],
            })

        except Exception as e:
            logger.error(f"Opening message error: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to generate opening message',
            }, status=500)


# =============================================================================
# CONVERSATION / CHAT
# =============================================================================

class AssistantChatView(LoginRequiredMixin, AssistantMixin, View):
    """
    Send a message to the assistant and get a response.
    """

    def post(self, request, *args, **kwargs):
        enabled, error = self.check_personal_assistant_enabled()

        if not enabled:
            return JsonResponse({
                'success': False,
                'error': error,
            }, status=200)

        try:
            data = json.loads(request.body)
            message = data.get('message', '').strip()

            if not message:
                return JsonResponse({
                    'success': False,
                    'error': 'Message is required',
                }, status=400)

            if len(message) > 2000:
                return JsonResponse({
                    'success': False,
                    'error': 'Message too long (max 2000 characters)',
                }, status=400)

            assistant = self.get_assistant()
            conversation = assistant.get_or_create_conversation()
            response = assistant.send_message(message, conversation)

            return JsonResponse({
                'success': True,
                'response': response,
                'conversation_id': conversation.id,
            })

        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON',
            }, status=400)
        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to process message',
            }, status=500)


class ConversationHistoryView(LoginRequiredMixin, AssistantMixin, View):
    """
    Get conversation history.
    """

    def get(self, request, *args, **kwargs):
        conversation_id = kwargs.get('conversation_id')

        try:
            if conversation_id:
                conversation = AssistantConversation.objects.get(
                    id=conversation_id,
                    user=request.user
                )
            else:
                conversation = AssistantConversation.get_or_create_active(request.user)

            messages = conversation.messages.order_by('created_at').values(
                'id', 'role', 'content', 'message_type', 'created_at', 'was_helpful'
            )

            return JsonResponse({
                'success': True,
                'conversation_id': conversation.id,
                'session_type': conversation.session_type,
                'messages': list(messages),
            })

        except AssistantConversation.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Conversation not found',
            }, status=404)
        except Exception as e:
            logger.error(f"History error: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to load history',
            }, status=500)


class MessageFeedbackView(LoginRequiredMixin, View):
    """
    Submit feedback on a message (was it helpful?).
    """

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            message_id = data.get('message_id')
            was_helpful = data.get('was_helpful')

            if message_id is None or was_helpful is None:
                return JsonResponse({
                    'success': False,
                    'error': 'message_id and was_helpful are required',
                }, status=400)

            message = AssistantMessage.objects.get(
                id=message_id,
                conversation__user=request.user
            )
            message.was_helpful = was_helpful
            message.save(update_fields=['was_helpful'])

            return JsonResponse({'success': True})

        except AssistantMessage.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Message not found',
            }, status=404)
        except Exception as e:
            logger.error(f"Feedback error: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to save feedback',
            }, status=500)


# =============================================================================
# DAILY PRIORITIES
# =============================================================================

class DailyPrioritiesView(LoginRequiredMixin, AssistantMixin, View):
    """
    Get or regenerate daily priorities.
    """

    def get(self, request, *args, **kwargs):
        enabled, error = self.check_personal_assistant_enabled()
        force_refresh = request.GET.get('refresh') == 'true'

        try:
            if enabled:
                assistant = self.get_assistant()
                priorities = assistant.generate_daily_priorities(force_refresh)
            else:
                # Return existing priorities without AI
                from apps.core.utils import get_user_today
                today = get_user_today(request.user)
                priorities = DailyPriority.objects.filter(
                    user=request.user,
                    priority_date=today
                ).values()

            return JsonResponse({
                'success': True,
                'ai_enabled': enabled,
                'priorities': list(priorities),
            })

        except Exception as e:
            logger.error(f"Priorities error: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to load priorities',
            }, status=500)


class PriorityCompleteView(LoginRequiredMixin, View):
    """
    Mark a priority as completed.
    """

    # Positive feedback messages by priority type
    FEEDBACK_MESSAGES = {
        'faith': [
            "Wonderful! Staying grounded in faith strengthens everything else.",
            "Beautiful! Your spiritual foundation is growing stronger.",
            "Excellent! Faith first leads to aligned decisions.",
        ],
        'purpose': [
            "Great progress! You're moving toward your bigger goals.",
            "Fantastic! Each step toward your purpose matters.",
            "Well done! Purpose-driven action builds lasting momentum.",
        ],
        'commitment': [
            "Awesome! Keeping commitments builds trust with yourself.",
            "Nice work! Completing what you set out to do feels great.",
            "Excellent! You're following through on your word.",
        ],
        'health': [
            "Great choice! Taking care of your health empowers everything.",
            "Well done! Your future self thanks you.",
            "Fantastic! Health is wealth in every way.",
        ],
        'personal': [
            "Great job! Personal growth compounds over time.",
            "Excellent! You're becoming who you want to be.",
            "Nice! Every small step counts.",
        ],
        'default': [
            "Great job! Keep up the momentum.",
            "Well done! You're making progress.",
            "Excellent! One step closer to your best self.",
        ],
    }

    def post(self, request, *args, **kwargs):
        import random
        priority_id = kwargs.get('priority_id')

        try:
            priority = DailyPriority.objects.get(
                id=priority_id,
                user=request.user
            )
            priority.mark_complete()

            # Get appropriate feedback message
            messages = self.FEEDBACK_MESSAGES.get(
                priority.priority_type,
                self.FEEDBACK_MESSAGES['default']
            )
            feedback = random.choice(messages)

            return JsonResponse({
                'success': True,
                'feedback': feedback,
                'completed_count': DailyPriority.objects.filter(
                    user=request.user,
                    priority_date=priority.priority_date,
                    is_completed=True
                ).count()
            })

        except DailyPriority.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Priority not found',
            }, status=404)
        except Exception as e:
            logger.error(f"Complete error: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to complete priority',
            }, status=500)


class PriorityDismissView(LoginRequiredMixin, View):
    """
    Dismiss a priority (user doesn't want it).
    """

    def post(self, request, *args, **kwargs):
        priority_id = kwargs.get('priority_id')

        try:
            priority = DailyPriority.objects.get(
                id=priority_id,
                user=request.user
            )
            priority.user_dismissed = True
            priority.save(update_fields=['user_dismissed', 'updated_at'])

            return JsonResponse({'success': True})

        except DailyPriority.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Priority not found',
            }, status=404)


# =============================================================================
# STATE ASSESSMENT
# =============================================================================

class StateAssessmentView(LoginRequiredMixin, AssistantMixin, View):
    """
    Get current state assessment.
    """

    def get(self, request, *args, **kwargs):
        force_refresh = request.GET.get('refresh') == 'true'

        try:
            assistant = self.get_assistant()
            state = assistant.assess_current_state(force_refresh)

            return JsonResponse({
                'success': True,
                'state': state,
            })

        except Exception as e:
            logger.error(f"State assessment error: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to assess state',
            }, status=500)


# =============================================================================
# TREND ANALYSIS
# =============================================================================

class WeeklyAnalysisView(LoginRequiredMixin, AssistantMixin, View):
    """
    Get weekly trend analysis.
    """

    def get(self, request, *args, **kwargs):
        enabled, error = self.check_personal_assistant_enabled()
        force_refresh = request.GET.get('refresh') == 'true'

        try:
            tracker = self.get_tracker()
            analysis = tracker.generate_weekly_analysis(force_refresh)

            if analysis:
                return JsonResponse({
                    'success': True,
                    'ai_enabled': enabled,
                    'analysis': {
                        'period_start': str(analysis.period_start),
                        'period_end': str(analysis.period_end),
                        'summary': analysis.summary,
                        'patterns': analysis.patterns_detected,
                        'recommendations': analysis.recommendations,
                        'comparison': analysis.comparison_to_previous,
                        'metrics': analysis.metrics,
                    }
                })
            else:
                return JsonResponse({
                    'success': True,
                    'analysis': None,
                    'message': 'Not enough data for weekly analysis',
                })

        except Exception as e:
            logger.error(f"Weekly analysis error: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to generate analysis',
            }, status=500)


class MonthlyAnalysisView(LoginRequiredMixin, AssistantMixin, View):
    """
    Get monthly trend analysis.
    """

    def get(self, request, *args, **kwargs):
        enabled, error = self.check_personal_assistant_enabled()
        force_refresh = request.GET.get('refresh') == 'true'

        try:
            tracker = self.get_tracker()
            analysis = tracker.generate_monthly_analysis(force_refresh)

            if analysis:
                return JsonResponse({
                    'success': True,
                    'ai_enabled': enabled,
                    'analysis': {
                        'period_start': str(analysis.period_start),
                        'period_end': str(analysis.period_end),
                        'summary': analysis.summary,
                        'patterns': analysis.patterns_detected,
                        'recommendations': analysis.recommendations,
                        'comparison': analysis.comparison_to_previous,
                        'metrics': analysis.metrics,
                    }
                })
            else:
                return JsonResponse({
                    'success': True,
                    'analysis': None,
                    'message': 'Not enough data for monthly analysis',
                })

        except Exception as e:
            logger.error(f"Monthly analysis error: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to generate analysis',
            }, status=500)


class DriftDetectionView(LoginRequiredMixin, AssistantMixin, View):
    """
    Detect drift from stated intentions.
    """

    def get(self, request, *args, **kwargs):
        try:
            tracker = self.get_tracker()
            drift_areas = tracker.detect_intention_drift()

            return JsonResponse({
                'success': True,
                'drift_areas': drift_areas,
            })

        except Exception as e:
            logger.error(f"Drift detection error: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to detect drift',
            }, status=500)


class GoalProgressView(LoginRequiredMixin, AssistantMixin, View):
    """
    Get goal progress report.
    """

    def get(self, request, *args, **kwargs):
        try:
            tracker = self.get_tracker()
            report = tracker.get_goal_progress_report()

            return JsonResponse({
                'success': True,
                'report': report,
            })

        except Exception as e:
            logger.error(f"Goal progress error: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to generate report',
            }, status=500)


# =============================================================================
# REFLECTION PROMPTS
# =============================================================================

class ReflectionPromptView(LoginRequiredMixin, AssistantMixin, View):
    """
    Get a reflection prompt for journaling.
    """

    def get(self, request, *args, **kwargs):
        context = request.GET.get('context', 'general')

        try:
            assistant = self.get_assistant()
            prompt = assistant.generate_reflection_prompt(context)

            return JsonResponse({
                'success': True,
                'prompt': prompt,
                'context': context,
            })

        except Exception as e:
            logger.error(f"Reflection prompt error: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to generate prompt',
            }, status=500)


class ReflectionPromptUsedView(LoginRequiredMixin, View):
    """
    Mark a reflection prompt as used (user started journaling with it).
    """

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            prompt_id = data.get('prompt_id')

            if prompt_id:
                prompt = ReflectionPromptQueue.objects.get(
                    id=prompt_id,
                    user=request.user
                )
                prompt.mark_used()

            return JsonResponse({'success': True})

        except ReflectionPromptQueue.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Prompt not found',
            }, status=404)
        except Exception as e:
            logger.error(f"Prompt used error: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to mark prompt',
            }, status=500)


# =============================================================================
# ASSISTANT DASHBOARD PAGE
# =============================================================================

class AssistantDashboardView(LoginRequiredMixin, AssistantMixin, TemplateView):
    """
    Full-page assistant dashboard with chat interface.
    """
    template_name = "ai/assistant_dashboard.html"

    def get(self, request, *args, **kwargs):
        """Override get to add request-level error handling."""
        try:
            return super().get(request, *args, **kwargs)
        except Exception as e:
            logger.exception(f"Error in AssistantDashboardView for {request.user.email}: {e}")
            raise

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        user = self.request.user
        logger.info(f"AssistantDashboardView.get_context_data called for user: {user.email}")

        try:
            prefs = user.preferences
        except Exception as e:
            logger.exception(f"Error getting user preferences for {user.email}: {e}")
            raise

        context['ai_enabled'] = getattr(prefs, 'ai_enabled', False)
        context['ai_consent'] = getattr(prefs, 'ai_data_consent', False)
        context['faith_enabled'] = getattr(prefs, 'faith_enabled', False)
        context['coaching_style'] = getattr(prefs, 'ai_coaching_style', 'supportive')

        # Personal Assistant module status
        context['personal_assistant_enabled'] = getattr(prefs, 'personal_assistant_enabled', False)
        context['personal_assistant_consent'] = getattr(prefs, 'personal_assistant_consent', False)

        # Check if Personal Assistant is fully accessible
        pa_enabled, pa_error = self.check_personal_assistant_enabled()
        context['personal_assistant_accessible'] = pa_enabled
        context['personal_assistant_error'] = pa_error

        # Get or create conversation for the session (but don't load history)
        # Chat starts fresh each page load - no previous messages displayed
        try:
            conversation = AssistantConversation.get_or_create_active(user)
            context['conversation'] = conversation
            # Don't pass previous messages to template - chat starts fresh each visit
            context['messages'] = []
        except Exception as e:
            logger.error(f"Error getting assistant conversation for {user.email}: {e}")
            context['conversation'] = None
            context['messages'] = []

        return context
