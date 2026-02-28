# ==============================================================================
# File: views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Dashboard AI Personal Assistant API endpoints and views
# Owner: Danny Jenkins (admin@wholelifejourney.com)
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

import base64
import json
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views import View
from django.views.generic import RedirectView, TemplateView

from apps.core.utils import user_log_id
from apps.help.mixins import HelpContextMixin

from .models import (
    AssistantConversation, AssistantMessage, DailyPriority,
    ReflectionPromptQueue
)
from .personal_assistant import get_personal_assistant
from .trend_tracking import get_trend_tracker
from .services import AIService

logger = logging.getLogger(__name__)


class CalibrationDebugView(LoginRequiredMixin, View):
    """Temporary debug view to check calibration state in production."""

    def get(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return JsonResponse({'error': 'staff only'}, status=403)
        try:
            from apps.core.blueprint.cos_governance import get_calibration_state
            from apps.core.blueprint.models import PersonalOperatingBlueprint
            from apps.core.ai_governance.models import GovernanceAlignmentSession

            cal_state = get_calibration_state(request.user)
            blueprint = PersonalOperatingBlueprint.objects.filter(
                user=request.user).first()
            alignment = GovernanceAlignmentSession.objects.filter(
                user=request.user).first()
            prefs = request.user.preferences

            return JsonResponse({
                'calibration_state': cal_state,
                'blueprint_exists': blueprint is not None,
                'calibration_complete': blueprint.calibration_complete if blueprint else None,
                'governance_overrides_keys': list(
                    (blueprint.governance_overrides or {}).keys()
                ) if blueprint else None,
                'calibration_stage': (blueprint.governance_overrides or {}).get(
                    'calibration_stage') if blueprint else None,
                'calibration_welcome_shown': (blueprint.governance_overrides or {}).get(
                    'calibration_welcome_shown') if blueprint else None,
                'calibration_answers': (blueprint.governance_overrides or {}).get(
                    'calibration_answers') if blueprint else None,
                'alignment_session_exists': alignment is not None,
                'alignment_is_complete': alignment.is_complete if alignment else None,
                'pa_enabled': prefs.personal_assistant_enabled,
                'pa_consent': prefs.personal_assistant_consent,
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


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

            # Build CoS snapshot for auto-initialized chat
            cos_snapshot = {}
            try:
                from apps.core.ai_orchestrator.cos_context import build_cos_context
                ctx = build_cos_context(request.user)
                cos_snapshot = {
                    'alignment': ctx.get('alignment_score', 100),
                    'drift_risk': ctx.get('drift_probability', {}).get(
                        'probability_24h', 0,
                    ),
                    'capacity': ctx.get(
                        'capacity_snapshot', {},
                    ).get('capacity_pct', 0),
                    'tier1_protected': ctx.get('protected_tiers', []),
                    'in_recovery': False,
                }
                # Check recovery
                try:
                    from apps.core.blueprint.recovery_engine import (
                        get_recovery_status,
                    )
                    rec = get_recovery_status(request.user)
                    cos_snapshot['in_recovery'] = rec.get(
                        'in_recovery', False,
                    )
                    cos_snapshot['recovery_warnings'] = rec.get(
                        'recovery_warnings', [],
                    )
                except Exception:
                    pass
            except Exception:
                pass

            return JsonResponse({
                'success': True,
                'greeting': opening['greeting'],
                'state_summary': opening['state_summary'],
                'priorities': list(opening['priorities']),
                'celebrations': opening['celebrations'],
                'nudges': opening['nudges'],
                'reflection_prompt': opening['reflection_prompt'],
                'is_first_visit': opening.get('is_first_visit', True),
                'cos_snapshot': cos_snapshot,
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

    Supports:
    - JSON body with 'message' and optional 'page_context'
    - Multipart form data with 'message', optional 'page_context', and optional 'image'
    - Intent recognition for structured data extraction
    - Image uploads for OpenAI Vision processing

    The response includes 'action_taken' when an action was executed.
    """

    # Maximum image size (5MB)
    MAX_IMAGE_SIZE = 5 * 1024 * 1024
    # Allowed image MIME types
    ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']

    def post(self, request, *args, **kwargs):
        enabled, error = self.check_personal_assistant_enabled()

        if not enabled:
            return JsonResponse({
                'success': False,
                'error': error,
            }, status=200)

        try:
            # Handle both JSON and multipart/form-data requests
            content_type = request.content_type or ''

            if 'multipart/form-data' in content_type:
                # Multipart form data (with potential image)
                message = request.POST.get('message', '').strip()
                page_context_str = request.POST.get('page_context', '{}')
                try:
                    page_context = json.loads(page_context_str)
                except json.JSONDecodeError:
                    page_context = {}

                # Handle image upload
                image_data = None
                image_mime_type = None
                if 'image' in request.FILES:
                    image_file = request.FILES['image']

                    # Validate file size
                    if image_file.size > self.MAX_IMAGE_SIZE:
                        return JsonResponse({
                            'success': False,
                            'error': 'Image too large (max 5MB)',
                        }, status=400)

                    # Validate MIME type
                    if image_file.content_type not in self.ALLOWED_IMAGE_TYPES:
                        return JsonResponse({
                            'success': False,
                            'error': f'Invalid image type. Allowed: {", ".join(self.ALLOWED_IMAGE_TYPES)}',
                        }, status=400)

                    # Read and encode image as base64
                    image_bytes = image_file.read()
                    image_data = base64.b64encode(image_bytes).decode('utf-8')
                    image_mime_type = image_file.content_type

            else:
                # JSON body (traditional request)
                data = json.loads(request.body)
                message = data.get('message', '').strip()
                page_context = data.get('page_context', {})
                image_data = data.get('image_data')  # Already base64 encoded
                image_mime_type = data.get('image_mime_type')

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
            result = assistant.send_message(
                message,
                conversation,
                page_context=page_context,
                image_data=image_data,
                image_mime_type=image_mime_type
            )

            # Phase 4: Extract learning from user message (non-blocking)
            try:
                from apps.core.ai_learning.learning_extractor import (
                    extract_learning, evolve_profile,
                )
                response_text = result.get('response', '') if isinstance(result, dict) else str(result)
                extract_learning(request.user, message, response_text)
                # Run profile evolution periodically (lightweight check)
                evolve_profile(request.user)
            except Exception:
                pass  # Learning extraction must never break chat

            # Phase 4b: Detect corrections and store them (non-blocking)
            try:
                from apps.ai.correction_service import detect_correction, store_correction
                if detect_correction(message):
                    # Get the previous assistant message to know what was corrected
                    prev_msgs = conversation.messages.filter(
                        role='assistant'
                    ).order_by('-created_at')[:1]
                    if prev_msgs:
                        prev = prev_msgs[0]
                        store_correction(
                            user=request.user,
                            user_message=message,
                            original_response=prev.content,
                            conversation=conversation,
                            original_message_id=prev.id,
                        )
            except Exception:
                pass  # Correction detection must never break chat

            # Phase 4c: Run behavioral pattern detection (lightweight, non-blocking)
            try:
                from apps.ai.pattern_detector import detect_patterns
                detect_patterns(request.user)
            except Exception:
                pass  # Pattern detection must never break chat

            # Handle both old string response and new dict response
            if isinstance(result, dict):
                response_data = {
                    'success': True,
                    'response': result.get('response', ''),
                    'conversation_id': conversation.id,
                }
                # Include actions_taken if present (supports multiple actions)
                if result.get('actions_taken'):
                    response_data['actions_taken'] = result['actions_taken']
                    # Also include action_taken for backwards compatibility with single action
                    if result.get('action_taken'):
                        response_data['action_taken'] = result['action_taken']
                elif result.get('action_taken'):
                    # Single action only
                    response_data['action_taken'] = result['action_taken']
                # Include image info if present in user message
                if result.get('user_message_has_image'):
                    response_data['user_message_has_image'] = True
            else:
                # Backwards compatibility for string response
                response_data = {
                    'success': True,
                    'response': result,
                    'conversation_id': conversation.id,
                }

            return JsonResponse(response_data)

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
                'id', 'role', 'content', 'message_type', 'created_at', 'was_helpful',
                'image_data', 'image_mime_type', 'quick_replies', 'quick_reply_used',
                'is_proactive'
            )

            # Process messages to include image data URLs and quick replies
            messages_list = []
            for msg in messages:
                msg_data = {
                    'id': msg['id'],
                    'role': msg['role'],
                    'content': msg['content'],
                    'message_type': msg['message_type'],
                    'created_at': msg['created_at'],
                    'was_helpful': msg['was_helpful'],
                    'is_proactive': msg.get('is_proactive', False),
                }
                # Add image data URL if present
                if msg.get('image_data') and msg.get('image_mime_type'):
                    msg_data['image_data_url'] = f"data:{msg['image_mime_type']};base64,{msg['image_data']}"
                # Add quick replies if present and not already used
                if msg.get('quick_replies') and not msg.get('quick_reply_used'):
                    msg_data['quick_replies'] = msg['quick_replies']
                elif msg.get('quick_reply_used'):
                    msg_data['quick_reply_used'] = msg['quick_reply_used']
                messages_list.append(msg_data)

            # Add calibration state for chat auto-start
            calibration_active = False
            calibration_next_question = None
            calibration_welcome_needed = False
            try:
                from apps.core.blueprint.cos_governance import get_calibration_state
                cal_state = get_calibration_state(request.user)
                if cal_state and cal_state['active'] and not cal_state['paused']:
                    calibration_active = True
                    calibration_welcome_needed = not cal_state.get('welcome_shown', False)
                    if cal_state.get('next_question'):
                        calibration_next_question = cal_state['next_question'].get('question')
            except Exception:
                pass

            return JsonResponse({
                'success': True,
                'conversation_id': conversation.id,
                'session_type': conversation.session_type,
                'messages': messages_list,
                'calibration_active': calibration_active,
                'calibration_next_question': calibration_next_question,
                'calibration_welcome_needed': calibration_welcome_needed,
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

            # Persistent Learning: propagate feedback to memory + response optimizer
            try:
                from apps.ai.memory_service import propagate_feedback
                propagate_feedback(request.user, message_id, was_helpful)
            except Exception:
                pass  # Feedback propagation must never break the response

            try:
                from apps.ai.response_optimizer import record_feedback
                record_feedback(request.user, message.content, was_helpful)
            except Exception:
                pass  # Response optimization must never break the response

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


class ClearConversationView(LoginRequiredMixin, View):
    """
    Clear the active conversation, starting fresh.

    This allows users to clear their chat history and start a new conversation.
    Before clearing, we extract any personal context from the conversation
    to help the AI respond more empathetically in the future.
    """

    def post(self, request, *args, **kwargs):
        try:
            # Extract personal context in a background thread so it doesn't
            # block the clear response. The messages are captured before clearing.
            self._extract_personal_context_async(request.user)

            conversation = AssistantConversation.clear_active_conversation(request.user)

            return JsonResponse({
                'success': True,
                'conversation_id': conversation.id,
                'message': 'Conversation cleared successfully',
            })

        except Exception as e:
            logger.error(f"Clear conversation error: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to clear conversation',
            }, status=500)

    def _extract_personal_context_async(self, user):
        """
        Extract personal context from the active conversation in a background
        thread so the clear response returns immediately.

        We capture messages before clearing so they're available for extraction
        even after the conversation is wiped.
        """
        import threading

        try:
            # Get the active conversation and its messages BEFORE clearing
            conversation = AssistantConversation.objects.filter(
                user=user,
                is_active=True
            ).first()

            if not conversation:
                return

            messages = list(conversation.messages.order_by('created_at').values(
                'role', 'content'
            ))

            if not messages:
                return

            # Run extraction in background thread
            def _extract(user_id, messages_copy):
                try:
                    from django.contrib.auth import get_user_model
                    from .personal_context import update_user_personal_context
                    from django import db

                    # Get a fresh user instance for the new thread
                    User = get_user_model()
                    user = User.objects.get(pk=user_id)
                    update_user_personal_context(user, messages_copy)
                except Exception as e:
                    logger.warning(f"Background personal context extraction failed: {e}")
                finally:
                    db.connections.close_all()

            thread = threading.Thread(
                target=_extract,
                args=(user.pk, messages),
                daemon=True
            )
            thread.start()

        except Exception as e:
            # Log but don't fail the clear operation
            logger.warning(f"Personal context extraction setup failed: {e}", exc_info=True)


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
# QUICK REPLY HANDLING
# =============================================================================

class QuickReplyView(LoginRequiredMixin, AssistantMixin, View):
    """
    Handle quick reply button clicks from the assistant chat.

    Quick replies allow users to respond to proactive check-ins
    with a single tap (e.g., "Yes, I took my medicine").
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
            message_id = data.get('message_id')
            reply_id = data.get('reply_id')
            action = data.get('action')
            params = data.get('params', {})

            if not action:
                return JsonResponse({
                    'success': False,
                    'error': 'Action is required',
                }, status=400)

            # Handle the quick reply action
            from .quick_reply_handlers import handle_quick_reply
            result = handle_quick_reply(request.user, action, params)

            # Mark the quick reply as used on the message
            if message_id and reply_id:
                try:
                    message = AssistantMessage.objects.get(
                        id=message_id,
                        conversation__user=request.user
                    )
                    message.quick_reply_used = reply_id
                    message.save(update_fields=['quick_reply_used'])
                except AssistantMessage.DoesNotExist:
                    pass  # Message not found, but action was handled

            # Add assistant response message to conversation
            if result.get('success') and result.get('message'):
                conversation = AssistantConversation.get_or_create_active(request.user)
                AssistantMessage.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=result['message'],
                    message_type='text',
                )

            return JsonResponse({
                'success': result.get('success', False),
                'message': result.get('message', ''),
                'data': result.get('data', {}),
            })

        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON',
            }, status=400)
        except Exception as e:
            logger.error(f"Quick reply error: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to process quick reply',
            }, status=500)


# =============================================================================
# ASSISTANT DASHBOARD PAGE (RETIRED — redirects to main dashboard)
# =============================================================================

class AssistantDashboardView(LoginRequiredMixin, RedirectView):
    """
    Legacy assistant page — redirects to main dashboard.

    The Chief of Staff panel (persistent on every page) is now the single
    chat interface. Today's Priorities are available as a dashboard tile.
    All /assistant/api/* endpoints remain unchanged.
    """
    permanent = False
    pattern_name = 'dashboard:home'


# =============================================================================
# COS SETTINGS
# =============================================================================

class CosSettingsView(LoginRequiredMixin, TemplateView):
    """
    CoS governance settings — simple controls for adaptive authority.

    5 primary controls:
    1. Accountability style (light/standard/firm)
    2. Question frequency (low/medium/high)
    3. Relationship suggestions toggle
    4. Event reflections toggle
    5. Preferred notification channel
    """

    template_name = "ai/cos_settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        prefs = user.preferences

        # Get blueprint governance profile
        try:
            from apps.core.blueprint.models import PersonalOperatingBlueprint
            blueprint = PersonalOperatingBlueprint.get_or_create_for_user(user)
            context['blueprint'] = blueprint
            context['sensitivity_tags'] = blueprint.sensitivity_tags or []

            # Learned preferences from SLCME
            try:
                from apps.core.ai_memory.models import LearnedMapping
                learned = LearnedMapping.objects.filter(
                    user=user,
                    meaning_type='governance_preference',
                    is_active=True,
                ).order_by('-confidence_score')[:10]
                context['learned_preferences'] = learned
            except Exception:
                context['learned_preferences'] = []

            # Known people from AI Relationships
            try:
                from apps.core.ai_relationships.models import Person
                people = Person.objects.filter(
                    user=user, is_active=True,
                ).order_by('display_name')[:20]
                context['known_people'] = people
            except Exception:
                context['known_people'] = []

        except Exception as e:
            logger.debug(f"CoS settings: blueprint unavailable: {e}")
            context['blueprint'] = None

        context['prefs'] = prefs
        context['pa_enabled'] = getattr(prefs, 'personal_assistant_enabled', False)
        context['cos_display_name_raw'] = getattr(prefs, 'cos_display_name', '')

        # Learning Mode state for toggle UI
        try:
            from apps.core.blueprint.learning_mode import (
                is_learning_mode_active,
                is_exit_pending,
                get_exit_summary,
            )
            context['learning_mode_active'] = is_learning_mode_active(user)
            context['learning_mode_exit_pending'] = is_exit_pending(user)
            context['learning_mode_exit_summary'] = get_exit_summary(user)
        except Exception:
            context['learning_mode_active'] = False
            context['learning_mode_exit_pending'] = False
            context['learning_mode_exit_summary'] = ''

        return context


class CosSettingsSaveView(LoginRequiredMixin, View):
    """Handle CoS settings form submission."""

    def post(self, request, *args, **kwargs):
        from django.contrib import messages as django_messages

        user = request.user

        try:
            from apps.core.blueprint.models import PersonalOperatingBlueprint
            blueprint = PersonalOperatingBlueprint.get_or_create_for_user(user)

            # Update governance fields
            accountability = request.POST.get('accountability_style', 'standard')
            if accountability in ('light', 'standard', 'firm'):
                blueprint.accountability_style = accountability

            frequency = request.POST.get('question_frequency', 'medium')
            if frequency in ('low', 'medium', 'high'):
                blueprint.question_frequency = frequency

            blueprint.relationship_suggestions_enabled = (
                request.POST.get('relationship_suggestions') == 'on'
            )
            blueprint.event_reflections_enabled = (
                request.POST.get('event_reflections') == 'on'
            )

            # Sensitivity tags (comma-separated)
            tags_raw = request.POST.get('sensitivity_tags', '')
            if tags_raw.strip():
                tags = [t.strip().lower() for t in tags_raw.split(',') if t.strip()]
                blueprint.sensitivity_tags = tags
            else:
                blueprint.sensitivity_tags = []

            blueprint.save()

            # Update CoS display name on user preferences
            cos_name = request.POST.get('cos_display_name', '').strip()[:50]
            prefs = user.preferences
            if prefs.cos_display_name != cos_name:
                prefs.cos_display_name = cos_name
                prefs.save(update_fields=['cos_display_name'])

            django_messages.success(request, "Settings saved.")

        except Exception as e:
            logger.error(f"CoS settings save error: {e}", exc_info=True)
            django_messages.error(request, "Could not save settings.")

        return redirect('ai:cos_settings')


class EventReflectionView(LoginRequiredMixin, View):
    """
    API endpoint for event reflection actions (answer, skip).

    POST: { reflection_id: int, action: 'answer'|'skip', text: str (if answer) }
    """

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        user = request.user
        reflection_id = data.get('reflection_id')
        action = data.get('action', 'skip')

        if not reflection_id:
            return JsonResponse({'error': 'reflection_id required'}, status=400)

        if action == 'skip':
            from apps.core.blueprint.reflection_engine import skip_reflection
            success = skip_reflection(user, reflection_id)
            return JsonResponse({'success': success})

        elif action == 'answer':
            answer_text = data.get('text', '').strip()
            if not answer_text:
                return JsonResponse({'error': 'text required'}, status=400)

            from apps.core.blueprint.reflection_engine import process_reflection_answer
            result = process_reflection_answer(user, reflection_id, answer_text)
            return JsonResponse(result)

        return JsonResponse({'error': 'Unknown action'}, status=400)


class LearningModeToggleView(LoginRequiredMixin, View):
    """
    Toggle Learning Mode on/off.

    POST: { action: 'enter' | 'exit' | 'confirm_exit' | 'cancel_exit' }

    Phase 1 — CoS Foundational Restructure:
    - 'enter': Activates Learning Mode, blocks UAIO/PIE/PRIE
    - 'exit': Requests exit (pending confirmation), CoS generates summary
    - 'confirm_exit': User confirms summary, execution resumes
    - 'cancel_exit': User rejects summary, stays in Learning Mode
    """

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        user = request.user
        action = data.get('action', '')

        from apps.core.blueprint.learning_mode import (
            enter_learning_mode,
            request_exit_learning_mode,
            confirm_exit_learning_mode,
            cancel_exit_learning_mode,
            is_learning_mode_active,
            is_exit_pending,
            get_exit_summary,
        )

        if action == 'enter':
            success = enter_learning_mode(user)
            # Optionally start priority onboarding
            if success:
                try:
                    from apps.core.blueprint.priority_questions import start_priority_onboarding
                    start_priority_onboarding(user)
                except Exception:
                    pass
            return JsonResponse({
                'success': success,
                'learning_mode_active': is_learning_mode_active(user),
            })

        elif action == 'exit':
            summary = data.get('summary', '')
            success = request_exit_learning_mode(user, summary)
            return JsonResponse({
                'success': success,
                'exit_pending': is_exit_pending(user),
                'summary': get_exit_summary(user),
            })

        elif action == 'confirm_exit':
            success = confirm_exit_learning_mode(user)
            return JsonResponse({
                'success': success,
                'learning_mode_active': is_learning_mode_active(user),
            })

        elif action == 'cancel_exit':
            success = cancel_exit_learning_mode(user)
            return JsonResponse({
                'success': success,
                'learning_mode_active': is_learning_mode_active(user),
            })

        return JsonResponse({'error': 'Unknown action'}, status=400)


# ---------------------------------------------------------------------------
# Text-to-Speech (TTS) API
# ---------------------------------------------------------------------------

class TextToSpeechView(LoginRequiredMixin, View):
    """
    POST /ai/api/tts/

    Convert text to speech audio using OpenAI TTS API.
    Returns base64-encoded MP3 audio for playback in the browser.

    Body (JSON):
        text (str): Text to convert (required, max 4096 chars).
        voice (str): Voice choice — alloy, echo, fable, nova, onyx, shimmer.
        speed (float): Playback speed 0.25–4.0 (default 1.0).

    Response:
        { "audio": "<base64 mp3>", "content_type": "audio/mpeg" }
    """

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON body'}, status=400)

        text = (body.get('text') or '').strip()
        if not text:
            return JsonResponse({'error': 'Text is required'}, status=400)

        voice = body.get('voice')
        speed = body.get('speed', 1.0)

        try:
            speed = float(speed)
        except (TypeError, ValueError):
            speed = 1.0

        from apps.ai.tts_service import (
            clean_text_for_speech,
            generate_speech_base64,
            VOICE_CHOICES,
        )

        # Validate voice
        if voice and voice not in VOICE_CHOICES:
            return JsonResponse(
                {'error': f'Invalid voice. Choose from: {", ".join(VOICE_CHOICES.keys())}'},
                status=400,
            )

        # Clean text for natural speech
        cleaned_text = clean_text_for_speech(text)
        if not cleaned_text:
            return JsonResponse({'error': 'Text is empty after cleaning'}, status=400)

        # Generate audio
        audio_b64 = generate_speech_base64(cleaned_text, voice=voice, speed=speed)
        if not audio_b64:
            return JsonResponse(
                {'error': 'Speech generation failed. Please try again.'},
                status=502,
            )

        return JsonResponse({
            'audio': audio_b64,
            'content_type': 'audio/mpeg',
        })
