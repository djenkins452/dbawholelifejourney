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
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import RedirectView, TemplateView

from apps.core.utils import user_log_id
from apps.help.mixins import HelpContextMixin

from .models import (
    AssistantConversation, AssistantMessage, DailyPriority,
    MessageImage, ReflectionPromptQueue,
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


class ExecutiveCertificationConsoleView(LoginRequiredMixin, View):
    """DEVELOPER-ONLY in-app Executive Certification Console. GET renders the action
    buttons; POST runs an action against the REAL production path via the SAME shared
    implementation the management command uses (apps.ai.certification_console). Staff-
    gated — never shown to normal users. The manual counterpart to the Acceptance
    Center: it validates the Chief of Staff, not the implementation."""

    def get(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return JsonResponse({'error': 'staff only'}, status=403)
        from apps.ai.certification_console import action_list
        return render(request, "ai/certification_console.html",
                      {"actions": action_list()})

    def post(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return JsonResponse({'ok': False, 'summary': 'staff only'}, status=403)
        try:
            data = json.loads(request.body or b"{}")
        except (ValueError, TypeError):
            data = {}
        key = data.get("action")
        force = bool(data.get("force"))
        from apps.ai.certification_console import run_action
        return JsonResponse(run_action(request.user, key, force=force))


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
        from apps.ai.cos_gateway import CoSGateway, SURFACE_OPENING
        enabled, error = self.check_personal_assistant_enabled()

        if not enabled:
            return JsonResponse({
                'success': False,
                'error': error,
                'fallback': True,
            }, status=200)

        def _suppressed(reason):
            # CoS user: the legacy day-start briefing + Beth opening renderer are
            # NOT invoked. Contract keys preserved with empty/null values.
            return JsonResponse({
                'success': True,
                'greeting': None,
                'state_summary': None,
                'priorities': [],
                'celebrations': [],
                'nudges': [],
                'reflection_prompt': None,
                'is_first_visit': True,
                'cos_snapshot': {},
                'suppressed_reason': reason,
            })

        def _legacy():
            # ── Authoritative day-start (idempotent) ──
            from apps.ai.executive_briefing import handle_day_start
            handle_day_start(request.user)

            assistant = self.get_assistant()
            opening = assistant.get_opening_message()

            # Build CoS snapshot — uses full situation state when available
            cos_snapshot = {}
            try:
                # Try CoSSituationState first (pre-computed, richer)
                from apps.core.ai_state.models import CoSSituationState
                sit = CoSSituationState.objects.filter(
                    user=request.user,
                ).first()

                if sit and sit.dominant_concern:
                    cos_snapshot = {
                        'alignment': 100,  # Populated below from raw context
                        'drift_risk': 0,
                        'capacity': 0,
                        'tier1_protected': [],
                        'in_recovery': sit.situation_mode == CoSSituationState.MODE_RECOVERY,
                        # Situation state fields (Phase 4 parity)
                        'situation_mode': sit.situation_mode,
                        'situation_mode_display': sit.get_situation_mode_display(),
                        'dominant_concern': sit.dominant_concern,
                        'top_priority': sit.top_priority,
                        'opening_sentence': sit.opening_sentence,
                        'changes_since_last': sit.changes_since_last_interaction[:5],
                        'escalations': sit.escalations[:3],
                        'resolutions': sit.resolutions[:3],
                        'messages_since_briefing': sit.messages_since_briefing,
                    }

                # Enrich with raw alignment/drift/capacity from cos_context
                from apps.core.ai_orchestrator.cos_context import build_cos_context
                ctx = build_cos_context(request.user)
                cos_snapshot['alignment'] = ctx.get('alignment_score', 100)
                cos_snapshot['drift_risk'] = ctx.get(
                    'drift_probability', {},
                ).get('probability_24h', 0)
                cos_snapshot['capacity'] = ctx.get(
                    'capacity_snapshot', {},
                ).get('capacity_pct', 0)
                cos_snapshot['tier1_protected'] = ctx.get('protected_tiers', [])

                # Check recovery from blueprint if not already set
                if not cos_snapshot.get('in_recovery'):
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

        try:
            return CoSGateway.structured(
                user=request.user, surface=SURFACE_OPENING,
                legacy=_legacy, suppressed=_suppressed,
            )
        except Exception as e:
            logger.error(f"Opening message error: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to generate opening message',
            }, status=500)


# =============================================================================
# PRE-WARM / READINESS
# =============================================================================

class AssistantWakeView(LoginRequiredMixin, AssistantMixin, View):
    """
    Ultra-lightweight wake endpoint for CoS pre-warming.

    Called by frontend on input focus/keypress to:
    1. Warm DB connection pool (single SELECT 1 query)
    2. Pre-build cos_context in background thread if not cached
    3. Return immediately with readiness state

    Does NOT: trigger LLM calls, write messages, modify state.
    Target response time: <10ms.
    """

    def post(self, request, *args, **kwargs):
        import threading
        from apps.ai.readiness_cache import (
            get_cached_cos_context,
            get_readiness_state,
            prewarm_cos_context,
            set_readiness_state,
            track_active_user,
            warm_db_connection,
            warm_openai_client,
        )
        from apps.ai.readiness_telemetry import log_wake_request

        user = request.user

        # Quick PA check — skip prewarm if PA not enabled
        enabled, _ = self.check_personal_assistant_enabled()
        if not enabled:
            return JsonResponse({"status": "disabled"}, status=200)

        # Warm DB + OpenAI client connection pools
        warm_db_connection()
        warm_openai_client()

        # Track user as active (for keep-alive targeting)
        track_active_user(user)

        # Check if context is already cached
        cached = get_cached_cos_context(user) is not None
        current_state = get_readiness_state(user)
        log_wake_request(user.id, cached)

        if cached:
            return JsonResponse({
                "status": "ready",
                "cached": True,
            })

        # Avoid duplicate warm-ups
        if current_state == "warming":
            return JsonResponse({
                "status": "warming",
                "cached": False,
            })

        # Spawn background thread to build + cache context
        set_readiness_state(user, "warming")

        def _prewarm_bg():
            try:
                prewarm_cos_context(user)
            except Exception as e:
                logger.warning("CoS prewarm failed for user %s: %s", user.id, e)
                try:
                    set_readiness_state(user, "cold")
                except Exception:
                    pass

        threading.Thread(target=_prewarm_bg, daemon=True).start()

        return JsonResponse({
            "status": "warming",
            "cached": False,
        })


class ProactiveBriefingView(LoginRequiredMixin, AssistantMixin, View):
    """
    Generate a proactive daily executive briefing on chat open (v7).

    Called by the frontend when the chat drawer opens and no recent
    briefing has been delivered. Goes through the full CoS pipeline
    (_generate_response) for hallucination protection.

    POST /assistant/api/briefing/

    Returns:
        - 200 with briefing content if generated
        - 200 with 'skipped': True if briefing not needed (cooldown)
        - 200 with 'error' if PA not enabled
        - 500 on failure
    """

    def post(self, request, *args, **kwargs):
        from apps.ai.cos_gateway import CoSGateway, SURFACE_BRIEFING
        enabled, error = self.check_personal_assistant_enabled()
        if not enabled:
            return JsonResponse({
                'success': False,
                'error': error,
            }, status=200)

        def _legacy():
            # ── Authoritative day-start (idempotent) ──
            # Must run BEFORE CoS rendering so execution truth is settled.
            from apps.ai.executive_briefing import handle_day_start
            handle_day_start(request.user)

            assistant = self.get_assistant()
            result = assistant.generate_proactive_briefing()

            if result is None:
                return JsonResponse({
                    'success': True,
                    'skipped': True,
                    'reason': 'Briefing already delivered or not needed',
                })

            return JsonResponse({
                'success': True,
                'response': result['response'],
                'message_id': result['message_id'],
                'is_proactive': True,
            })

        def _suppressed(reason):
            # CoS user: legacy day-start briefing + Beth check-in renderer NOT run.
            return JsonResponse({
                'success': True,
                'skipped': True,
                'response': None,
                'is_proactive': True,
                'suppressed_reason': reason,
            })

        try:
            return CoSGateway.structured(
                user=request.user, surface=SURFACE_BRIEFING,
                legacy=_legacy, suppressed=_suppressed,
            )
        except Exception as e:
            logger.error("Proactive briefing error: %s", e, exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to generate briefing',
            }, status=500)


# =============================================================================
# SESSION START (Adaptive CoS Presence)
# =============================================================================

class SessionStartView(LoginRequiredMixin, AssistantMixin, View):
    """
    Deterministic session-start endpoint for Adaptive CoS Presence.

    Called by the frontend/iOS app on app-open to let CoS proactively
    engage without the user typing first. Returns structured, pre-computed
    data — NO LLM calls, NO heavy computation on the request path.

    Decision tree (all deterministic):
    1. First-of-day or gap re-entry → briefing or lightweight alignment
    2. High drift detected → drift intervention
    3. Otherwise → action: none (CoS stays quiet)

    POST /assistant/api/session-start/

    Returns JSON:
        {"action": "briefing",              "payload": {...}}
        {"action": "lightweight_alignment",  "payload": {...}}
        {"action": "drift_intervention",     "payload": {...}}
        {"action": "none"}
    """

    def post(self, request, *args, **kwargs):
        from apps.ai.cos_gateway import CoSGateway
        enabled, error = self.check_personal_assistant_enabled()
        if not enabled:
            return JsonResponse({
                'action': 'none',
                'reason': error,
            }, status=200)

        # SINGLE GATEWAY (Phase 0A.2): the session-start payload is built by the
        # legacy day-start briefing + Beth renderer. For CoS users the gateway
        # SUPPRESSES it (CoS stays quiet via the existing 'action: none'
        # contract) — the legacy producer is never invoked, no Beth fallback.
        if CoSGateway.is_cos(request.user):
            return JsonResponse({
                'action': 'none',
                'suppressed_reason': (
                    "ChatGPT CoS 'session_start' narrative is not yet "
                    "implemented; suppressed (no legacy Beth fallback)."
                ),
            })

        try:
            from django.utils import timezone as tz
            from apps.core.utils import get_user_now, get_user_today
            from apps.ai.executive_briefing import (
                _compute_session_gap,
                handle_day_start,
                build_lightweight_alignment,
            )

            user = request.user
            user_now = get_user_now(user)
            today = get_user_today(user)

            # ── Authoritative day-start (idempotent) ──
            # Ensures routine tasks exist + auto-completes Wake Up.
            # Must run BEFORE any CoS rendering or briefing logic.
            day_start = handle_day_start(user)

            # Get or create conversation
            conversation = AssistantConversation.get_or_create_active(user)
            metadata = conversation.metadata or {}

            # ── Gate: first-of-day or gap re-entry? ──
            last_briefing_date = metadata.get('last_briefing_date')
            is_first_of_day = last_briefing_date != str(today)

            gap_hours = _compute_session_gap(conversation)
            is_gap_reentry = (
                gap_hours is not None
                and gap_hours >= 4
                and not is_first_of_day
            )

            # ── Time classification ──
            hour = user_now.hour
            time_of_day = (
                'morning' if hour < 12
                else 'afternoon' if hour < 17
                else 'evening'
            )

            # ── Branch 1: Briefing warranted ──
            if is_first_of_day or is_gap_reentry:
                wake_inferred = day_start.get('wake_completed', False)

                # Check for recent deep interaction → lightweight alignment
                deep_at = metadata.get('last_deep_interaction_at')
                if deep_at:
                    from django.utils.dateparse import parse_datetime
                    deep_ts = parse_datetime(deep_at)
                    if (
                        deep_ts
                        and (tz.now() - deep_ts).total_seconds() < 90 * 60
                    ):
                        # Build lightweight alignment payload
                        snapshot = metadata.get('alignment_snapshot', {})
                        alignment_payload = (
                            self._build_lightweight_payload(
                                user, deep_at, snapshot,
                            )
                        )
                        logger.info(
                            "SESSION_START action=lightweight_alignment "
                            "user=%s deep_at=%s",
                            user.id, deep_at,
                        )
                        return JsonResponse({
                            'action': 'lightweight_alignment',
                            'payload': alignment_payload,
                        })

                # Full briefing payload (structured, no LLM)
                briefing_payload = self._build_briefing_payload(
                    user, today, user_now, time_of_day,
                    is_first_of_day, wake_inferred,
                )
                session_type = (
                    'morning' if is_first_of_day
                    else 'gap_reentry'
                )
                logger.info(
                    "SESSION_START action=briefing user=%s type=%s",
                    user.id, session_type,
                )
                return JsonResponse({
                    'action': 'briefing',
                    'payload': {
                        'session_type': session_type,
                        'time_of_day': time_of_day,
                        'wake_inferred': wake_inferred,
                        **briefing_payload,
                    },
                })

            # ── Branch 2: Drift intervention ──
            drift_payload = self._check_drift(user, today)
            if drift_payload:
                logger.info(
                    "SESSION_START action=drift_intervention user=%s "
                    "score=%s",
                    user.id, drift_payload.get('drift_score'),
                )
                return JsonResponse({
                    'action': 'drift_intervention',
                    'payload': drift_payload,
                })

            # ── Branch 3: Nothing to say ──
            return JsonResponse({'action': 'none'})

        except Exception as e:
            logger.error(
                "Session start error: %s", e, exc_info=True,
            )
            return JsonResponse({'action': 'none'})

    def _build_briefing_payload(self, user, today, user_now, time_of_day,
                                is_first_of_day, wake_inferred):
        """
        Build structured briefing payload from unified CoS pipeline.

        Uses build_cos_structured_output() as the single source of truth,
        then enriches with execution snapshot and drift score for backward
        compatibility.
        """
        payload = {}

        # Unified CoS structured output (Today Engine + prioritizer)
        try:
            from apps.ai.beth_checkin_renderer import (
                build_cos_structured_output,
            )
            cos_structured = build_cos_structured_output(user)
            payload['cos_structured'] = cos_structured
            payload['rendered_text'] = cos_structured['rendered_text']
            payload['next_action'] = (
                cos_structured['sequence'][0]
                if cos_structured['sequence']
                else ''
            )
            payload['overdue_count'] = (
                len(cos_structured['move_later'])
                if cos_structured['state'] == 'behind'
                else 0
            )
        except Exception as e:
            logger.debug("Session start: cos structured failed: %s", e)
            payload['cos_structured'] = {}
            payload['rendered_text'] = ''
            payload['next_action'] = ''
            payload['overdue_count'] = 0

        # Execution snapshot (backward compat for frontend)
        try:
            from apps.core.execution.execution_truth_engine import (
                get_execution_truth,
            )
            truth = get_execution_truth(user)
            routines = truth.get('routines', {})
            tasks = truth.get('tasks', {})
            meds = truth.get('medications', {})

            payload['execution_snapshot'] = {
                'routines_completed': routines.get('completed', 0),
                'routines_total': routines.get('total', 0),
                'tasks_completed': tasks.get('completed', 0),
                'tasks_total': tasks.get('total', 0),
                'meds_taken': meds.get('taken', 0),
                'meds_expected': meds.get('expected', 0),
            }
        except Exception as e:
            logger.debug("Session start: execution truth failed: %s", e)
            payload['execution_snapshot'] = {}

        # Day load classification from structured output
        cos = payload.get('cos_structured', {})
        do_now_count = len(cos.get('do_now', []))
        move_later_count = len(cos.get('move_later', []))
        total_pending = do_now_count + move_later_count
        if total_pending <= 3:
            payload['day_load'] = 'light'
        elif total_pending <= 7:
            payload['day_load'] = 'focused'
        else:
            payload['day_load'] = 'heavy'

        # Drift score (pre-computed by run_drift_scoring)
        try:
            from apps.core.blueprint.models import DriftScore
            drift_obj = DriftScore.objects.filter(
                user=user, date=today,
            ).first()
            payload['drift_score'] = (
                round(drift_obj.score) if drift_obj else 0
            )
        except Exception:
            payload['drift_score'] = 0

        return payload

    def _build_lightweight_payload(self, user, deep_at, snapshot):
        """Build lightweight alignment payload from snapshot + current state."""
        payload = {
            'prior_alignment_at': deep_at,
            'since_alignment': {
                'completed': [],
                'newly_overdue': [],
            },
            'current_next_action': '',
        }
        try:
            from apps.core.execution.execution_truth_engine import (
                get_execution_truth,
            )
            truth = get_execution_truth(user)
            prev_completed = set(snapshot.get('completed_items', []))
            current_routines = truth.get('routines', {}).get('items', {})
            current_completed = {
                name for name, info in current_routines.items()
                if info.get('fully_complete')
            }
            payload['since_alignment']['completed'] = sorted(
                current_completed - prev_completed
            )
        except Exception:
            pass

        try:
            from apps.core.today.today_engine import get_today_context
            today_ctx = get_today_context(user)
            payload['current_next_action'] = today_ctx.get('next', '')
            overdue = today_ctx.get('overdue', [])
            payload['since_alignment']['newly_overdue'] = [
                item.get('name', '') for item in overdue[:3]
            ]
        except Exception:
            pass

        return payload

    def _check_drift(self, user, today):
        """
        Check for high drift that warrants intervention at session start.

        Reads DriftScore (pre-computed by run_drift_scoring in SAME cycle).
        Returns drift payload if score >= 40, else None.
        """
        try:
            from apps.core.blueprint.models import DriftScore
            drift_obj = DriftScore.objects.filter(
                user=user, date=today,
            ).first()
            if not drift_obj or drift_obj.score < 40:
                return None

            pillar_scores = drift_obj.pillar_scores or {}
            top_pillar = max(
                pillar_scores, key=pillar_scores.get, default=None,
            ) if pillar_scores else None

            return {
                'drift_score': round(drift_obj.score),
                'top_pillar': top_pillar,
                'pillar_score': (
                    round(pillar_scores.get(top_pillar, 0), 1)
                    if top_pillar else 0
                ),
                'probability_24h': round(
                    (drift_obj.drift_probability_24h or 0) * 100
                ),
            }
        except Exception as e:
            logger.debug("Session start: drift check failed: %s", e)
            return None


# =============================================================================
# CONVERSATION / CHAT
# =============================================================================

def _log_page_context_diag(source, page_context, user):
    """LOG-ONLY diagnostic — proves exactly what page_context arrives at the chat
    endpoint (Page Awareness H1). Runs before any routing, on BOTH endpoints. No
    behavior change; never raises. Logs shape/flags only, not raw scripture text.
    """
    try:
        pc = page_context if isinstance(page_context, dict) else {}
        content = pc.get('page_content')
        content = content if isinstance(content, dict) else {}
        logger.info(
            "PAGE_CTX_DIAG source=%s user=%s present=%s keys=%s module=%s url=%s "
            "content_present=%s content_type=%s has_scriptures=%s "
            "has_scripture_text=%s scripture_text_len=%s title=%s",
            source, getattr(user, 'id', '?'),
            bool(pc), sorted(pc.keys()),
            pc.get('module'), (pc.get('url') or '')[:80],
            bool(content), content.get('type'),
            bool(content.get('scriptures')), bool(content.get('scripture_text')),
            len(content.get('scripture_text') or ''),
            (pc.get('page_title') or '')[:60],
        )
    except Exception:
        logger.debug("PAGE_CTX_DIAG failed", exc_info=True)


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
                # Multipart form data (with potential images)
                message = request.POST.get('message', '').strip()
                page_context_str = request.POST.get('page_context', '{}')
                try:
                    page_context = json.loads(page_context_str)
                except json.JSONDecodeError:
                    page_context = {}

                # Handle multiple image uploads (up to 5)
                images_list = []  # List of (base64_data, mime_type) tuples
                image_files = request.FILES.getlist('images')
                # Backward compat: also check singular 'image' key
                if not image_files and 'image' in request.FILES:
                    image_files = [request.FILES['image']]

                if len(image_files) > 5:
                    return JsonResponse({
                        'success': False,
                        'error': 'Maximum 5 images per message',
                    }, status=400)

                for image_file in image_files:
                    if image_file.size > self.MAX_IMAGE_SIZE:
                        return JsonResponse({
                            'success': False,
                            'error': f'Image too large (max 5MB): {image_file.name}',
                        }, status=400)

                    if image_file.content_type not in self.ALLOWED_IMAGE_TYPES:
                        return JsonResponse({
                            'success': False,
                            'error': f'Invalid image type. Allowed: {", ".join(self.ALLOWED_IMAGE_TYPES)}',
                        }, status=400)

                    image_bytes = image_file.read()
                    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
                    images_list.append((image_b64, image_file.content_type))

                # Backward compat: first image also set as image_data/image_mime_type
                image_data = images_list[0][0] if images_list else None
                image_mime_type = images_list[0][1] if images_list else None

            else:
                # JSON body (traditional request)
                data = json.loads(request.body)
                message = data.get('message', '').strip()
                page_context = data.get('page_context', {})
                image_data = data.get('image_data')  # Already base64 encoded
                image_mime_type = data.get('image_mime_type')
                images_list = []
                if image_data and image_mime_type:
                    images_list = [(image_data, image_mime_type)]

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

            _log_page_context_diag('chat', page_context, request.user)
            # SINGLE CONVERSATIONAL GATEWAY (Phase 0A) — runtime resolved once.
            # Legacy Beth (day-start briefing + send_message) for flag-OFF;
            # ChatGPT CoS for flag-ON. Downstream response/intelligence code is
            # unchanged — the legacy rich result dict is preserved via the
            # envelope meta so flag-OFF JSON is byte-identical.
            from apps.ai.cos_gateway import CoSGateway, SURFACE_CHAT
            from apps.ai.models import AssistantConversation
            envelope = CoSGateway.respond(
                user=request.user,
                surface=SURFACE_CHAT,
                message=message,
                page_context=page_context,
                image_data=image_data,
                image_mime_type=image_mime_type,
                images_list=images_list if len(images_list) > 1 else None,
            )
            conversation = AssistantConversation.objects.get(
                id=envelope.meta['conversation_id'],
            )
            result = envelope.meta.get('legacy_result')
            if result is None:
                result = {'response': envelope.text}
                if envelope.meta.get('tools_called'):
                    result['tools_called'] = envelope.meta['tools_called']

            # Phase 4: Post-response intelligence (truly non-blocking via bg thread)
            # Learning extraction, correction detection, and pattern detection
            # are moved off the response path to reduce latency.
            import threading
            _pr_user = request.user
            _pr_message = message
            _pr_result = result
            _pr_conversation = conversation

            def _post_response_intelligence():
                try:
                    from apps.core.ai_learning.learning_extractor import (
                        extract_learning, evolve_profile,
                    )
                    resp_text = _pr_result.get('response', '') if isinstance(_pr_result, dict) else str(_pr_result)
                    extract_learning(_pr_user, _pr_message, resp_text)
                    evolve_profile(_pr_user)
                except Exception as e:
                    logger.debug("Post-response learning extraction failed: %s", e)

                try:
                    from apps.ai.correction_service import detect_correction, store_correction
                    if detect_correction(_pr_message):
                        prev_msgs = _pr_conversation.messages.filter(
                            role='assistant'
                        ).order_by('-created_at')[:1]
                        if prev_msgs:
                            prev = prev_msgs[0]
                            store_correction(
                                user=_pr_user,
                                user_message=_pr_message,
                                original_response=prev.content,
                                conversation=_pr_conversation,
                                original_message_id=prev.id,
                            )
                except Exception as e:
                    logger.debug("Post-response correction detection failed: %s", e)

                try:
                    from apps.ai.pattern_detector import detect_patterns
                    detect_patterns(_pr_user)
                except Exception as e:
                    logger.debug("Post-response pattern detection failed: %s", e)

                # Life fact extraction — captures biographical details
                # (family, deaths, milestones) as permanent PersonalFact records
                try:
                    from apps.core.ai_memory.life_fact_extractor import (
                        extract_life_facts_from_message,
                    )
                    resp_text_for_lf = _pr_result.get('response', '') if isinstance(_pr_result, dict) else str(_pr_result)
                    extract_life_facts_from_message(
                        _pr_user, _pr_message, resp_text_for_lf
                    )
                except Exception as e:
                    logger.debug("Post-response life fact extraction failed: %s", e)

            threading.Thread(target=_post_response_intelligence, daemon=True).start()

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
                # Include structured options (A/B/C chips) for confirmations
                if result.get('options'):
                    response_data['options'] = result['options']
                # Include navigation hint for post-action UX
                if result.get('navigation'):
                    response_data['navigation'] = result['navigation']
                # Include image info if present in user message
                if result.get('user_message_has_image'):
                    response_data['user_message_has_image'] = True
                # Phase 6.7: surface request_id so the frontend can clear
                # its sessionStorage pending marker and correlate the
                # reply with the submitted message.
                if result.get('request_id'):
                    response_data['request_id'] = result['request_id']
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


def _chat_relay_stream(job_id, user_id):
    """
    Read-only SSE relay over a chat_stream_bus snapshot.

    Shared by the initial POST and the resume endpoint. Emits a leading
    ``job`` event (so the client can store the reconnect handle), then tails
    the snapshot — streaming new token text and any new control events — until
    the snapshot reaches a terminal status. It always replays from the start,
    so a reconnecting client receives the full answer so far.

    On client disconnect the generator receives GeneratorExit; we log it and
    let it propagate. The owning Celery task is unaffected and keeps running.
    """
    import json
    import time as _t

    from apps.ai import chat_stream_bus as bus
    from apps.ai.readiness_telemetry import (
        log_stream_complete, log_stream_start,
    )

    POLL_INTERVAL = 0.15      # seconds between snapshot reads
    MAX_WALL = 90.0           # cap one connection; client reconnects by job_id
    HEARTBEAT = 15.0          # SSE comment cadence to keep proxies/CDN alive

    yield f"event: job\ndata: {json.dumps({'job_id': job_id})}\n\n"

    text_cursor = 0
    event_cursor = 0
    start = _t.monotonic()
    last_activity = start
    first_token_logged = False
    try:
        while True:
            snap = bus.read(job_id)
            if snap is None:
                # Snapshot expired/unknown — nothing left to observe.
                yield (
                    "event: error\n"
                    f"data: {json.dumps({'error': 'expired'})}\n\n"
                )
                return

            text = snap.get('text', '')
            if len(text) > text_cursor:
                delta = text[text_cursor:]
                text_cursor = len(text)
                if not first_token_logged:
                    first_token_logged = True
                    try:
                        log_stream_start(
                            user_id, (_t.monotonic() - start) * 1000,
                        )
                    except Exception:
                        pass
                yield (
                    "event: token\n"
                    f"data: {json.dumps({'content': delta})}\n\n"
                )
                last_activity = _t.monotonic()

            events = snap.get('events', [])
            while event_cursor < len(events):
                frame = bus.format_sse(events[event_cursor])
                event_cursor += 1
                if frame:
                    yield frame
                    last_activity = _t.monotonic()

            status = snap.get('status')
            if status in bus.TERMINAL_STATUSES:
                try:
                    log_stream_complete(
                        user_id, (_t.monotonic() - start) * 1000, text_cursor,
                    )
                except Exception:
                    pass
                return

            now = _t.monotonic()
            if now - start > MAX_WALL:
                # Generation still running — ask the client to reconnect by
                # job_id rather than pinning a gunicorn worker indefinitely.
                yield (
                    "event: timeout\n"
                    f"data: {json.dumps({'job_id': job_id})}\n\n"
                )
                return
            if now - last_activity > HEARTBEAT:
                yield ": keep-alive\n\n"
                last_activity = now
            _t.sleep(POLL_INTERVAL)
    except GeneratorExit:
        logger.info(
            "CHAT_STREAM_DISCONNECTED job=%s user=%s — client gone, "
            "generation continues in Celery task",
            job_id, user_id,
        )
        raise


class AssistantChatStreamView(LoginRequiredMixin, AssistantMixin, View):
    """
    Streaming chat endpoint using Server-Sent Events (SSE).

    POST /assistant/api/chat/stream/
    Content-Type: application/json
    Body: {"message": "...", "page_context": {...}}

    Response: text/event-stream
        event: token
        data: {"content": "chunk of text"}

        event: done
        data: {"conversation_id": 123, "actions_taken": [...]}

        event: error
        data: {"error": "message"}

    Text-only — images use the non-streaming /api/chat/ endpoint.
    """

    def post(self, request, *args, **kwargs):
        from django.http import StreamingHttpResponse

        enabled, error = self.check_personal_assistant_enabled()
        if not enabled:
            return JsonResponse(
                {'success': False, 'error': error}, status=200,
            )

        try:
            data = json.loads(request.body)
            message = data.get('message', '').strip()
            page_context = data.get('page_context', {})

            if not message:
                return JsonResponse(
                    {'success': False, 'error': 'Message is required'},
                    status=400,
                )
            if len(message) > 2000:
                return JsonResponse(
                    {'success': False, 'error': 'Message too long'},
                    status=400,
                )

            # ============================================================
            # SINGLE CONVERSATIONAL GATEWAY (Phase 0A). The gateway resolves
            # runtime ownership ONCE — ChatGPT CoS when use_chatgpt_cos=True,
            # else legacy Beth (which preserves the day-start briefing + legacy
            # generation task) — and dispatches the correct generation. This
            # view only builds the SSE relay from the returned job id. No
            # conversational surface decides runtime ownership itself.
            # ============================================================
            from apps.ai.cos_gateway import CoSGateway, SURFACE_CHAT_STREAM
            envelope = CoSGateway.respond(
                user=request.user,
                surface=SURFACE_CHAT_STREAM,
                message=message,
                page_context=page_context,
                stream=True,
            )
            response = StreamingHttpResponse(
                _chat_relay_stream(envelope.stream_job_id, request.user.id),
                content_type='text/event-stream',
            )
            response['Cache-Control'] = 'no-cache'
            response['X-Accel-Buffering'] = 'no'
            return response

        except json.JSONDecodeError:
            return JsonResponse(
                {'success': False, 'error': 'Invalid JSON'}, status=400,
            )
        except Exception as e:
            logger.error("Stream setup error: %s", e, exc_info=True)
            return JsonResponse(
                {'success': False, 'error': 'Failed to start stream'},
                status=500,
            )


class AssistantChatResumeView(LoginRequiredMixin, AssistantMixin, View):
    """
    Reconnect to an in-progress (or just-finished) chat generation by job_id.

    GET /assistant/api/chat/stream/resume/<job_id>/
    Response: text/event-stream (same framing as the initial stream)

    Security: the snapshot records the user id that created the job; a
    mismatch returns 403 (requirement 7). An expired/unknown job returns 410
    so the client falls back to loading the completed message from history.
    """

    def get(self, request, *args, **kwargs):
        from django.http import StreamingHttpResponse
        from apps.ai import chat_stream_bus as bus

        from apps.ai.chatgpt_cos.telemetry import beth_lifecycle

        job_id = kwargs.get('job_id')
        snap = bus.read(job_id)
        if snap is None:
            logger.info(
                "CHAT_RESUME_FROM_PERSISTED job=%s user=%s — snapshot "
                "expired; client loads completed message from history",
                job_id, request.user.id,
            )
            beth_lifecycle("BETH_JOB_RESUMED", job_id=job_id,
                           user_id=request.user.id, src="server",
                           extra="result=410_expired")
            return JsonResponse(
                {'success': False, 'status': 'expired'}, status=410,
            )
        if snap.get('owner') != request.user.id:
            logger.warning(
                "CHAT_RESUME_FORBIDDEN job=%s user=%s owner=%s",
                job_id, request.user.id, snap.get('owner'),
            )
            beth_lifecycle("BETH_JOB_RESUMED", job_id=job_id,
                           user_id=request.user.id, src="server",
                           extra="result=403_forbidden")
            return JsonResponse(
                {'success': False, 'error': 'Forbidden'}, status=403,
            )

        logger.info(
            "CHAT_RESUME_ATTACHED job=%s user=%s status=%s",
            job_id, request.user.id, snap.get('status'),
        )
        beth_lifecycle("BETH_JOB_RESUMED", job_id=job_id,
                       user_id=request.user.id, src="server",
                       extra=f"result=attached status={snap.get('status')}")
        response = StreamingHttpResponse(
            _chat_relay_stream(job_id, request.user.id),
            content_type='text/event-stream',
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response


class BethTelemetryView(View):
    """Instrumentation-only beacon. The frontend reports BETH_* lifecycle stages
    here via navigator.sendBeacon (which survives navigation-away), so client-side
    stages land in production logs alongside the server stages, all keyed by the
    same `cid`. Logs only — no state change, no behavior change, no recovery."""

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        from django.http import HttpResponse
        try:
            if not request.user.is_authenticated:
                return HttpResponse(status=204)
            from apps.ai.chatgpt_cos.telemetry import (
                BETH_LIFECYCLE_STAGES, beth_lifecycle,
            )
            data = json.loads(request.body or b"{}")
            stage = data.get("stage")
            if stage in BETH_LIFECYCLE_STAGES:
                beth_lifecycle(
                    stage,
                    cid=data.get("cid"),
                    job_id=data.get("job_id"),
                    conversation_id=data.get("conversation_id"),
                    message_id=data.get("message_id"),
                    user_id=request.user.id,
                    src="client",
                    extra=data.get("extra"),
                )
        except Exception:
            pass
        return HttpResponse(status=204)


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

            messages = conversation.messages.order_by('created_at').prefetch_related('images')

            # Process messages to include image data URLs and quick replies
            messages_list = []
            for msg in messages:
                msg_data = {
                    'id': msg.id,
                    'role': msg.role,
                    'content': msg.content,
                    'message_type': msg.message_type,
                    'created_at': msg.created_at,
                    'was_helpful': msg.was_helpful,
                    'is_proactive': getattr(msg, 'is_proactive', False),
                }
                # Collect all image data URLs (legacy + multi-image)
                image_urls = msg.all_image_data_urls
                if image_urls:
                    msg_data['image_data_url'] = image_urls[0]  # backward compat
                    msg_data['image_data_urls'] = image_urls     # multi-image
                # Add quick replies if present and not already used
                if msg.quick_replies and not msg.quick_reply_used:
                    msg_data['quick_replies'] = msg.quick_replies
                elif msg.quick_reply_used:
                    msg_data['quick_reply_used'] = msg.quick_reply_used
                # Phase 6.7: surface lifecycle metadata (request_id,
                # status, stream_interrupted) so the client can recover
                # interrupted requests after navigation or disconnect.
                if msg.role == 'assistant' and msg.metadata:
                    _lifecycle = {
                        k: msg.metadata.get(k)
                        for k in (
                            'request_id', 'status',
                            'stream_interrupted', 'intent_locked',
                        )
                        if k in msg.metadata
                    }
                    if _lifecycle:
                        msg_data['lifecycle'] = _lifecycle
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
        from apps.ai.cos_gateway import CoSGateway, SURFACE_PRIORITIES
        enabled, error = self.check_personal_assistant_enabled()
        force_refresh = request.GET.get('refresh') == 'true'

        def _legacy():
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
            return JsonResponse({'success': True, 'ai_enabled': enabled,
                                 'priorities': list(priorities)})

        def _suppressed(reason):
            return JsonResponse({'success': True, 'ai_enabled': enabled,
                                 'priorities': [], 'suppressed_reason': reason})

        try:
            return CoSGateway.structured(
                user=request.user, surface=SURFACE_PRIORITIES,
                legacy=_legacy, suppressed=_suppressed,
            )
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
        from apps.ai.cos_gateway import CoSGateway, SURFACE_STATE_ASSESSMENT
        force_refresh = request.GET.get('refresh') == 'true'

        def _legacy():
            assistant = self.get_assistant()
            state = assistant.assess_current_state(force_refresh)
            return JsonResponse({'success': True, 'state': state})

        def _suppressed(reason):
            # CoS user: the legacy LLM assessment narrator is NOT invoked.
            return JsonResponse({'success': True, 'state': None,
                                 'suppressed_reason': reason})

        try:
            return CoSGateway.structured(
                user=request.user, surface=SURFACE_STATE_ASSESSMENT,
                legacy=_legacy, suppressed=_suppressed,
            )
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
        from apps.ai.cos_gateway import CoSGateway, SURFACE_WEEKLY
        enabled, error = self.check_personal_assistant_enabled()
        force_refresh = request.GET.get('refresh') == 'true'

        def _legacy():
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
            return JsonResponse({
                'success': True,
                'analysis': None,
                'message': 'Not enough data for weekly analysis',
            })

        def _suppressed(reason):
            # CoS user: generate_weekly_analysis (LLM summary) is NOT invoked.
            return JsonResponse({'success': True, 'analysis': None,
                                 'suppressed_reason': reason})

        try:
            return CoSGateway.structured(
                user=request.user, surface=SURFACE_WEEKLY,
                legacy=_legacy, suppressed=_suppressed,
            )
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
        from apps.ai.cos_gateway import CoSGateway, SURFACE_MONTHLY
        enabled, error = self.check_personal_assistant_enabled()
        force_refresh = request.GET.get('refresh') == 'true'

        def _legacy():
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
            return JsonResponse({
                'success': True,
                'analysis': None,
                'message': 'Not enough data for monthly analysis',
            })

        def _suppressed(reason):
            # CoS user: generate_monthly_analysis (LLM summary) is NOT invoked.
            return JsonResponse({'success': True, 'analysis': None,
                                 'suppressed_reason': reason})

        try:
            return CoSGateway.structured(
                user=request.user, surface=SURFACE_MONTHLY,
                legacy=_legacy, suppressed=_suppressed,
            )
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
        from apps.ai.cos_gateway import CoSGateway, SURFACE_DRIFT

        def _legacy():
            tracker = self.get_tracker()
            drift_areas = tracker.detect_intention_drift()
            return JsonResponse({'success': True, 'drift_areas': drift_areas})

        def _suppressed(reason):
            return JsonResponse({'success': True, 'drift_areas': [],
                                 'suppressed_reason': reason})

        try:
            return CoSGateway.structured(
                user=request.user, surface=SURFACE_DRIFT,
                legacy=_legacy, suppressed=_suppressed,
            )
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
        from apps.ai.cos_gateway import CoSGateway, SURFACE_GOALS

        def _legacy():
            tracker = self.get_tracker()
            report = tracker.get_goal_progress_report()
            return JsonResponse({'success': True, 'report': report})

        def _suppressed(reason):
            return JsonResponse({'success': True, 'report': None,
                                 'suppressed_reason': reason})

        try:
            return CoSGateway.structured(
                user=request.user, surface=SURFACE_GOALS,
                legacy=_legacy, suppressed=_suppressed,
            )
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
        from apps.ai.cos_gateway import CoSGateway, SURFACE_REFLECTION
        context = request.GET.get('context', 'general')

        def _legacy():
            assistant = self.get_assistant()
            prompt = assistant.generate_reflection_prompt(context)
            return JsonResponse({'success': True, 'prompt': prompt,
                                 'context': context})

        def _suppressed(reason):
            return JsonResponse({'success': True, 'prompt': None,
                                 'context': context, 'suppressed_reason': reason})

        try:
            return CoSGateway.structured(
                user=request.user, surface=SURFACE_REFLECTION,
                legacy=_legacy, suppressed=_suppressed,
            )
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

            # Make the message id available to handlers that need it (e.g. 'dismiss'
            # persists the dismissal keyed by the message's guidance identity).
            if isinstance(params, dict):
                params.setdefault('message_id', message_id)

            # Handle the quick reply ACTION (truth/action handler — runs for
            # every runtime; the action is not conversational).
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

            # Gateway-owned conversational confirmation: legacy text for legacy
            # users; SUPPRESSED for CoS users (the action already executed).
            from apps.ai.cos_gateway import CoSGateway, SURFACE_QUICK_REPLY
            nar = CoSGateway.narrative(
                user=request.user, surface=SURFACE_QUICK_REPLY,
                legacy_producer=lambda: result.get('message', ''),
            )
            message_text = '' if nar.suppressed else nar.text

            # Persist the assistant confirmation only when NOT suppressed.
            if result.get('success') and message_text:
                conversation = AssistantConversation.get_or_create_active(request.user)
                AssistantMessage.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=message_text,
                    message_type='text',
                )

            payload = {
                'success': result.get('success', False),
                'message': message_text,
                'data': result.get('data', {}),
            }
            if nar.suppressed:
                payload['suppressed_reason'] = nar.suppressed_reason
            return JsonResponse(payload)

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
            # The reflection is SAVED inside process_reflection_answer (action);
            # only its conversational 'message' is gated by the gateway.
            result = process_reflection_answer(user, reflection_id, answer_text)
            from apps.ai.cos_gateway import CoSGateway, SURFACE_EVENT_REFLECTION
            nar = CoSGateway.narrative(
                user=user, surface=SURFACE_EVENT_REFLECTION,
                legacy_producer=lambda: (
                    result.get('message') if isinstance(result, dict) else ''
                ) or '',
            )
            if nar.suppressed and isinstance(result, dict):
                result = dict(result)
                result['message'] = None
                result['suppressed_reason'] = nar.suppressed_reason
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


# ---------------------------------------------------------------------------
# CoS Decision Mode API — deterministic, no LLM
# ---------------------------------------------------------------------------

class CosDecisionView(LoginRequiredMixin, AssistantMixin, View):
    """
    Deterministic CoS decision endpoint for the three decision modes.

    GET  /assistant/api/cos/decision/?mode=execution
    GET  /assistant/api/cos/decision/?mode=risk
    GET  /assistant/api/cos/decision/?mode=fix

    Returns a structured decision payload built from the shared
    execution_state contract. NO LLM is called; the answer is derived
    from the same Today Engine / active-block / prioritizer pipeline
    that powers the Action Center.

    Response shape:
        {
            "success": true,
            "mode": "execution" | "risk" | "fix",
            "primary_action": {...} | null,
            "reason": str,
            "follow_on": {...} | null,
            "message": str
        }
    """

    def get(self, request, *args, **kwargs):
        enabled, error = self.check_personal_assistant_enabled()
        if not enabled:
            return JsonResponse({
                'success': False,
                'error': error,
            }, status=403)

        mode_param = request.GET.get('mode', '')
        try:
            from apps.ai.cos_mode_router import normalize_mode
            from apps.core.execution.execution_state import (
                build_execution_state,
            )
            from apps.core.execution.selectors import select as run_selector

            mode = normalize_mode(mode_param)
            state = build_execution_state(request.user)
            decision = run_selector(mode, state)

            return JsonResponse({
                'success': True,
                'mode': decision.get('mode'),
                'primary_action': decision.get('primary_action'),
                'reason': decision.get('reason'),
                'follow_on': decision.get('follow_on'),
                'message': decision.get('message'),
            })
        except Exception:
            logger.error(
                "CoS decision endpoint failed mode=%s", mode_param,
                exc_info=True,
            )
            return JsonResponse({
                'success': False,
                'error': 'Failed to compute CoS decision.',
            }, status=500)
