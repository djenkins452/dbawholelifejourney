"""
CosPromptService — Proactive Prompting Engine for CoS v2.

Schedules and delivers pre/post activity prompts across ALL activity types.
Handles the Yes/No response flow and routes reflections to the correct module.

Integration points:
- ISE: Scheduler scans for due prompts every N minutes
- DNE: Delivery via multi-channel notification engine
- CosActionRegistry: Routes reflections to module-specific contracts
- CosPromptSchedule: Persists prompt state and response tracking
"""

import datetime as dt
import logging
from typing import Dict, List, Optional

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone as dj_timezone

from apps.cos.models import CosPromptSchedule, CosReflection
from apps.cos.services.prompt_templates import (
    detect_activity_type,
    get_lead_minutes,
    get_post_delay_minutes,
    get_post_event_template,
    get_pre_event_template,
    render_template,
)

logger = logging.getLogger(__name__)


class CosPromptService:
    """
    Manages the lifecycle of proactive prompts:
    schedule → deliver → respond → (optional) reflect
    """

    def __init__(self, user):
        self.user = user

    # ── Scheduling ────────────────────────────────────────

    def schedule_prompts_for_event(
        self,
        source_object,
        activity_type: Optional[str] = None,
        pre_lead_minutes: Optional[int] = None,
        post_delay_minutes: Optional[int] = None,
        skip_pre: bool = False,
        skip_post: bool = False,
        occurrence_date=None,
        override_start_dt=None,
        override_end_dt=None,
    ) -> List[CosPromptSchedule]:
        """
        Schedule both pre- and post-event prompts for a source object.

        The source object must have start_dt and end_dt (or equivalent).

        Args:
            source_object: The entity to attach prompts to (CalendarEvent, etc.)
            activity_type: Override detected type. If None, auto-detected from title.
            pre_lead_minutes: Minutes before event start. If None, uses default.
            post_delay_minutes: Minutes after event end. If None, uses default.
            skip_pre: Don't schedule pre-event prompt.
            skip_post: Don't schedule post-event prompt.
            occurrence_date: For recurring events, the specific date (dedup key).
            override_start_dt: Use instead of source_object.start_dt (for occurrences).
            override_end_dt: Use instead of source_object.end_dt (for occurrences).

        Returns:
            List of created CosPromptSchedule instances.
        """
        # Auto-detect activity type from title if not provided
        title = getattr(source_object, "title", "Activity")
        if not activity_type:
            activity_type = detect_activity_type(title)

        start_dt = override_start_dt or getattr(source_object, "start_dt", None)
        end_dt = override_end_dt or getattr(source_object, "end_dt", None)

        if not start_dt:
            logger.warning(
                "Cannot schedule prompts: source_object has no start_dt "
                "(user=%s, type=%s)",
                self.user.id, type(source_object).__name__,
            )
            return []

        ct = ContentType.objects.get_for_model(source_object)
        created = []

        # ── Pre-event prompt ──────────────────────────────
        if not skip_pre and start_dt > dj_timezone.now():
            lead = pre_lead_minutes or get_lead_minutes(activity_type)
            scheduled_for = start_dt - dt.timedelta(minutes=lead)

            # Don't schedule in the past
            if scheduled_for > dj_timezone.now():
                # Dedup: don't create if one already exists
                existing_pre = CosPromptSchedule.objects.filter(
                    user=self.user,
                    content_type=ct,
                    object_id=source_object.pk,
                    timing=CosPromptSchedule.TIMING_PRE,
                    status=CosPromptSchedule.STATUS_PENDING,
                    occurrence_date=occurrence_date,
                ).exists()

                if not existing_pre:
                    template = get_pre_event_template(activity_type)
                    prompt_text = render_template(
                        template,
                        title=title,
                        lead_minutes=lead,
                    )
                    pre_prompt = CosPromptSchedule.objects.create(
                        user=self.user,
                        content_type=ct,
                        object_id=source_object.pk,
                        timing=CosPromptSchedule.TIMING_PRE,
                        scheduled_for=scheduled_for,
                        lead_minutes=lead,
                        activity_type=activity_type,
                        prompt_text=prompt_text,
                        occurrence_date=occurrence_date,
                    )
                    created.append(pre_prompt)
                    logger.debug(
                        "Scheduled pre-event prompt: user=%s activity=%s at=%s occ=%s",
                        self.user.id, activity_type, scheduled_for, occurrence_date,
                    )

        # ── Post-event prompt ─────────────────────────────
        if not skip_post and end_dt:
            delay = post_delay_minutes or get_post_delay_minutes(activity_type)
            scheduled_for = end_dt + dt.timedelta(minutes=delay)

            # Dedup
            existing_post = CosPromptSchedule.objects.filter(
                user=self.user,
                content_type=ct,
                object_id=source_object.pk,
                timing=CosPromptSchedule.TIMING_POST,
                status=CosPromptSchedule.STATUS_PENDING,
                occurrence_date=occurrence_date,
            ).exists()

            if not existing_post:
                template = get_post_event_template(activity_type)
                prompt_text = render_template(template, title=title)
                post_prompt = CosPromptSchedule.objects.create(
                    user=self.user,
                    content_type=ct,
                    object_id=source_object.pk,
                    timing=CosPromptSchedule.TIMING_POST,
                    scheduled_for=scheduled_for,
                    lead_minutes=0,
                    activity_type=activity_type,
                    prompt_text=prompt_text,
                    occurrence_date=occurrence_date,
                )
                created.append(post_prompt)
                logger.debug(
                    "Scheduled post-event prompt: user=%s activity=%s at=%s occ=%s",
                    self.user.id, activity_type, scheduled_for, occurrence_date,
                )

        return created

    def cancel_prompts_for_event(self, source_object) -> int:
        """
        Cancel all pending prompts for a source object.

        Used when an event is deleted or canceled.
        Returns the number of prompts canceled.
        """
        ct = ContentType.objects.get_for_model(source_object)
        prompts = CosPromptSchedule.objects.filter(
            user=self.user,
            content_type=ct,
            object_id=source_object.pk,
            status=CosPromptSchedule.STATUS_PENDING,
        )
        count = prompts.count()
        for prompt in prompts:
            prompt.cancel()
        return count

    # ── Delivery ──────────────────────────────────────────

    def get_due_prompts(self) -> List[CosPromptSchedule]:
        """
        Get all pending prompts that are due for delivery.

        Called by the scheduler task to find prompts ready to deliver.
        """
        now = dj_timezone.now()
        return list(
            CosPromptSchedule.objects.filter(
                user=self.user,
                status=CosPromptSchedule.STATUS_PENDING,
                scheduled_for__lte=now,
            ).select_related("content_type").order_by("scheduled_for")
        )

    def deliver_prompt(self, prompt: CosPromptSchedule) -> bool:
        """
        Deliver a single prompt.

        Applies tone modifier, marks as delivered, and optionally routes
        through DNE. Returns True if delivered successfully.
        """
        if prompt.status != CosPromptSchedule.STATUS_PENDING:
            return False

        try:
            # Apply tone modifier to prompt text before delivery
            self._apply_tone_modifier(prompt)

            prompt.mark_delivered()

            # Route through DNE if available
            self._deliver_via_dne(prompt)

            return True
        except Exception as e:
            logger.error(
                "Failed to deliver prompt %s for user %s: %s",
                prompt.pk, self.user.id, e,
            )
            return False

    def deliver_all_due(self) -> Dict[str, int]:
        """
        Deliver all due prompts for this user.

        Returns: {"delivered": N, "skipped": N, "failed": N}
        """
        result = {"delivered": 0, "skipped": 0, "failed": 0}
        due = self.get_due_prompts()

        for prompt in due:
            if self.deliver_prompt(prompt):
                result["delivered"] += 1
            else:
                result["failed"] += 1

        return result

    def expire_stale_prompts(self, max_age_hours: int = 4) -> int:
        """
        Expire pending prompts that are older than max_age_hours.

        Prevents prompts from firing long after the event ended.
        Returns number of prompts expired.
        """
        cutoff = dj_timezone.now() - dt.timedelta(hours=max_age_hours)
        stale = CosPromptSchedule.objects.filter(
            user=self.user,
            status=CosPromptSchedule.STATUS_PENDING,
            scheduled_for__lt=cutoff,
        )
        count = stale.count()
        for prompt in stale:
            prompt.mark_expired()
        return count

    # ── Response Handling ─────────────────────────────────

    def handle_response(
        self,
        prompt_id: int,
        positive: bool,
        response_text: str = "",
    ) -> Dict:
        """
        Handle a user's response to a prompt.

        Flow:
        - Yes (positive=True) → optionally capture reflection, return follow-up
        - No (positive=False) → mark responded, stop (no nagging)

        Returns dict with response status and optional follow-up.
        """
        try:
            prompt = CosPromptSchedule.objects.get(
                pk=prompt_id, user=self.user,
            )
        except CosPromptSchedule.DoesNotExist:
            return {"success": False, "error": "Prompt not found"}

        prompt.mark_responded(positive=positive, text=response_text)

        result = {
            "success": True,
            "prompt_id": prompt.pk,
            "positive": positive,
            "follow_up": None,
        }

        if positive and prompt.timing == CosPromptSchedule.TIMING_POST:
            # Route completion to source object (habit entry, goal, milestone)
            try:
                from apps.cos.services.completion_service import CosCompletionService
                CosCompletionService.handle_completion_from_prompt(prompt)
            except Exception as e:
                logger.warning(
                    "Completion routing failed for prompt %s: %s",
                    prompt.pk, e,
                )

            # Capture reflection if text provided
            if response_text:
                self._capture_reflection_from_response(prompt, response_text)

            # Offer follow-up for "How did it go?" responses
            result["follow_up"] = {
                "type": "reflection_prompt",
                "text": "Anything else you want to note about this?",
                "capture_as_reflection": True,
            }

        # No follow-up for negative responses — respect "No"
        return result

    def handle_follow_up(
        self,
        prompt_id: int,
        follow_up_text: str,
    ) -> Dict:
        """
        Handle the optional follow-up after a positive response.

        Captures the follow-up text as a reflection.
        """
        try:
            prompt = CosPromptSchedule.objects.get(
                pk=prompt_id, user=self.user,
            )
        except CosPromptSchedule.DoesNotExist:
            return {"success": False, "error": "Prompt not found"}

        if follow_up_text:
            self._capture_reflection_from_response(prompt, follow_up_text)

        return {"success": True, "captured": bool(follow_up_text)}

    # ── Trigger-Aware Scheduling ─────────────────────────

    def schedule_trigger_aware_prompts(
        self,
        source_object,
        activity_type: Optional[str] = None,
        occurrence_date=None,
        override_start_dt=None,
        override_end_dt=None,
    ) -> List[CosPromptSchedule]:
        """
        Schedule prompts with trigger event detection.

        If the event matches a trigger pattern (social, dining, travel),
        uses trigger-aware templates that include strategy suggestions
        and structured A/B/C follow-up.

        Falls back to standard scheduling for non-trigger events.
        """
        from apps.cos.services.prompt_templates import (
            detect_trigger_event,
            get_pre_event_trigger_template,
            get_post_event_trigger_template,
            render_template as render_tmpl,
        )

        title = getattr(source_object, "title", "Activity")
        is_trigger = detect_trigger_event(title)

        if not is_trigger:
            # Standard scheduling for non-trigger events
            return self.schedule_prompts_for_event(
                source_object=source_object,
                activity_type=activity_type,
                occurrence_date=occurrence_date,
                override_start_dt=override_start_dt,
                override_end_dt=override_end_dt,
            )

        # Trigger-aware scheduling with enhanced templates
        start_dt = override_start_dt or getattr(source_object, "start_dt", None)
        end_dt = override_end_dt or getattr(source_object, "end_dt", None)

        if not start_dt:
            return []

        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(source_object)
        created = []
        lead = 120  # 2 hours pre-event for trigger events

        # Pre-event trigger prompt
        if start_dt > dj_timezone.now():
            scheduled_for = start_dt - dt.timedelta(minutes=lead)
            if scheduled_for > dj_timezone.now():
                existing = CosPromptSchedule.objects.filter(
                    user=self.user,
                    content_type=ct,
                    object_id=source_object.pk,
                    timing=CosPromptSchedule.TIMING_PRE,
                    status=CosPromptSchedule.STATUS_PENDING,
                    occurrence_date=occurrence_date,
                ).exists()
                if not existing:
                    template = get_pre_event_trigger_template()
                    prompt_text = render_tmpl(
                        template, title=title, lead_minutes=lead,
                    )
                    pre_prompt = CosPromptSchedule.objects.create(
                        user=self.user,
                        content_type=ct,
                        object_id=source_object.pk,
                        timing=CosPromptSchedule.TIMING_PRE,
                        scheduled_for=scheduled_for,
                        lead_minutes=lead,
                        activity_type=activity_type or "social",
                        prompt_text=prompt_text,
                        occurrence_date=occurrence_date,
                        metadata={"trigger_event": True},
                    )
                    created.append(pre_prompt)

        # Post-event A/B/C prompt
        if end_dt:
            delay = 60  # 1 hour post-event for trigger events
            scheduled_for = end_dt + dt.timedelta(minutes=delay)
            existing = CosPromptSchedule.objects.filter(
                user=self.user,
                content_type=ct,
                object_id=source_object.pk,
                timing=CosPromptSchedule.TIMING_POST,
                status=CosPromptSchedule.STATUS_PENDING,
                occurrence_date=occurrence_date,
            ).exists()
            if not existing:
                template = get_post_event_trigger_template()
                prompt_text = render_tmpl(template, title=title)
                post_prompt = CosPromptSchedule.objects.create(
                    user=self.user,
                    content_type=ct,
                    object_id=source_object.pk,
                    timing=CosPromptSchedule.TIMING_POST,
                    scheduled_for=scheduled_for,
                    lead_minutes=0,
                    activity_type=activity_type or "social",
                    prompt_text=prompt_text,
                    occurrence_date=occurrence_date,
                    metadata={"trigger_event": True, "abc_response": True},
                )
                created.append(post_prompt)

        return created

    # ── Overdue Habit Detection ───────────────────────────

    def schedule_overdue_habit_prompts(self) -> List[CosPromptSchedule]:
        """
        Detect overdue daily habits and schedule frictionless confirmation prompts.

        Scans for habits that should have been completed by now but haven't
        been marked. Creates one-tap confirmation prompts.

        Returns:
            List of created CosPromptSchedule instances.
        """
        from apps.cos.services.prompt_templates import (
            get_overdue_habit_template,
            get_overdue_medication_template,
            render_template as render_tmpl,
        )

        created = []
        now = dj_timezone.now()

        # Check for overdue calendar events (habits/tasks that should be done)
        try:
            from apps.calendar_engine.models import CalendarEvent
            from django.contrib.contenttypes.models import ContentType

            today = now.date()
            overdue_events = CalendarEvent.objects.filter(
                user=self.user,
                start_dt__date=today,
                end_dt__lt=now,
                status=CalendarEvent.STATUS_SCHEDULED,
                source_type__in=[
                    CalendarEvent.SOURCE_HABIT,
                    CalendarEvent.SOURCE_TASK,
                ],
            ).exclude(
                # Skip events that already have pending prompts
                pk__in=CosPromptSchedule.objects.filter(
                    user=self.user,
                    status=CosPromptSchedule.STATUS_PENDING,
                    metadata__contains='"overdue_check"',
                ).values_list("object_id", flat=True)
            )[:5]  # Limit to 5 to avoid prompt fatigue

            ct = ContentType.objects.get_for_model(CalendarEvent)
            for event in overdue_events:
                # Check if we already prompted for this today
                already_prompted = CosPromptSchedule.objects.filter(
                    user=self.user,
                    content_type=ct,
                    object_id=event.pk,
                    occurrence_date=today,
                    metadata__contains='"overdue_check"',
                ).exists()
                if already_prompted:
                    continue

                template = get_overdue_habit_template()
                prompt_text = render_tmpl(template, title=event.title)

                prompt = CosPromptSchedule.objects.create(
                    user=self.user,
                    content_type=ct,
                    object_id=event.pk,
                    timing=CosPromptSchedule.TIMING_POST,
                    scheduled_for=now,
                    lead_minutes=0,
                    activity_type=detect_activity_type(event.title),
                    prompt_text=prompt_text,
                    occurrence_date=today,
                    metadata={"overdue_check": True, "abc_response": True},
                )
                created.append(prompt)
        except Exception as e:
            logger.warning(
                "Overdue habit detection failed for user %s: %s",
                self.user.id, e,
            )

        return created

    # ── A/B/C Response Handler ────────────────────────────

    def handle_abc_response(
        self,
        prompt_id: int,
        choice: str,
        response_text: str = "",
    ) -> Dict:
        """
        Handle a structured A/B/C response to a trigger event or overdue habit.

        Args:
            prompt_id: The prompt being responded to.
            choice: "A", "B", or "C"
            response_text: Optional additional text from user.

        Returns:
            Dict with response status and follow-up message.
        """
        from apps.cos.services.prompt_templates import get_abc_follow_up

        try:
            prompt = CosPromptSchedule.objects.get(
                pk=prompt_id, user=self.user,
            )
        except CosPromptSchedule.DoesNotExist:
            return {"success": False, "error": "Prompt not found"}

        is_trigger = (prompt.metadata or {}).get("trigger_event", False)
        is_overdue = (prompt.metadata or {}).get("overdue_check", False)

        positive = choice.upper() == "A"
        prompt.mark_responded(positive=positive, text=response_text)

        result = {
            "success": True,
            "prompt_id": prompt.pk,
            "choice": choice.upper(),
            "follow_up": None,
        }

        if is_trigger:
            follow_up_text = get_abc_follow_up(choice.upper(), "trigger_event")
            result["follow_up"] = {
                "type": "coaching_response",
                "text": follow_up_text,
            }
            # Capture reflection
            if response_text:
                self._capture_reflection_from_response(prompt, response_text)

        elif is_overdue:
            if choice.upper() == "A":
                # Mark the source event as completed
                try:
                    from apps.cos.services.completion_service import CosCompletionService
                    CosCompletionService.handle_completion_from_prompt(prompt)
                except Exception as e:
                    logger.warning("Completion routing failed: %s", e)
                result["follow_up"] = {
                    "type": "confirmation",
                    "text": get_abc_follow_up("A", "overdue_habit"),
                }
            elif choice.upper() == "B":
                result["follow_up"] = {
                    "type": "reschedule_prompt",
                    "text": get_abc_follow_up("B_prompt", "overdue_habit"),
                }
            elif choice.upper() == "C":
                result["follow_up"] = {
                    "type": "reschedule_prompt",
                    "text": get_abc_follow_up("C_prompt", "overdue_habit"),
                }

        return result

    # ── Static delivery runner ────────────────────────────

    @staticmethod
    def deliver_all_due_for_all_users() -> Dict[str, int]:
        """
        Batch delivery for all users with due prompts.

        Called by ISE scheduler task. Finds all users with pending
        due prompts and delivers them.
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()
        now = dj_timezone.now()

        # Find distinct users with due prompts
        user_ids = set(
            CosPromptSchedule.objects.filter(
                status=CosPromptSchedule.STATUS_PENDING,
                scheduled_for__lte=now,
            )
            .values_list("user_id", flat=True)
        )

        totals = {"delivered": 0, "skipped": 0, "failed": 0, "users": 0}

        for user_id in user_ids:
            try:
                user = User.objects.get(pk=user_id)
                # Check CoS v2 feature flag
                if not getattr(user.preferences, "cos_v2_enabled", False):
                    continue

                svc = CosPromptService(user)
                result = svc.deliver_all_due()
                totals["delivered"] += result["delivered"]
                totals["failed"] += result["failed"]
                totals["users"] += 1

                # Also expire stale prompts
                svc.expire_stale_prompts()
            except Exception as e:
                logger.error(
                    "Prompt delivery failed for user %s: %s",
                    user_id, e,
                )
                totals["failed"] += 1

        return totals

    # ── Chat flow injection ────────────────────────────────

    @staticmethod
    def get_pending_prompt_injection(user) -> str:
        """
        Build a system prompt injection for pending/upcoming CoS prompts.

        Injected into both streaming fast-path and full-path so CoS can
        naturally mention upcoming activities when the user interacts.

        Returns:
            str — formatted injection, or "" if nothing pending.
        """
        now = dj_timezone.now()
        # Look ahead 30 minutes for upcoming prompts + all overdue
        lookahead = now + dt.timedelta(minutes=30)

        pending = CosPromptSchedule.objects.filter(
            user=user,
            status=CosPromptSchedule.STATUS_PENDING,
            scheduled_for__lte=lookahead,
        ).select_related("content_type").order_by("scheduled_for")[:5]

        if not pending:
            return ""

        lines = ["--- PENDING ACTIVITY PROMPTS ---"]
        for prompt in pending:
            delta_seconds = (prompt.scheduled_for - now).total_seconds()
            minutes_until = delta_seconds / 60
            if minutes_until <= 0:
                tag = "[DUE NOW]"
            elif minutes_until <= 15:
                tag = "[SOON]"
            else:
                tag = f"[in ~{int(minutes_until)} min]"

            activity_label = prompt.activity_type.replace("_", " ").title()
            lines.append(f"  {tag} {activity_label}: {prompt.prompt_text[:150]}")

        lines.append(
            "Weave these naturally into conversation. Don't list them — "
            "mention the most urgent one as a friendly nudge."
        )
        lines.append("--- END PENDING PROMPTS ---")
        return "\n".join(lines)

    # ── Private helpers ───────────────────────────────────

    def _deliver_via_dne(self, prompt: CosPromptSchedule):
        """
        Route prompt delivery through the DNE (Delivery & Notification Engine).

        Gracefully degrades if DNE is not available.
        """
        try:
            from apps.core.ai_delivery.delivery_engine import deliver_single

            payload = {
                "title": f"CoS: {prompt.activity_type.replace('_', ' ').title()}",
                "message": prompt.prompt_text[:300],
                "action_url": "/assistant/",
                "icon": self._get_activity_icon(prompt.activity_type),
                "priority": 3,  # Normal priority
            }

            deliver_single(
                user=self.user,
                source_engine="COS",
                source_object=prompt,
                payload=payload,
            )
        except ImportError:
            logger.debug("DNE not available, prompt delivered in-model only")
        except Exception as e:
            logger.debug("DNE delivery failed (non-fatal): %s", e)

    def _capture_reflection_from_response(
        self, prompt: CosPromptSchedule, text: str
    ):
        """
        Create a CosReflection from a prompt response.

        Uses CosReflectionService for auto-sentiment detection and
        SLCME integration (long-term context memory).
        """
        try:
            from apps.cos.services.reflection_service import CosReflectionService

            source_entity = prompt.source_entity
            if not source_entity:
                # Fallback: create directly if source entity is gone
                activity_date = prompt.scheduled_for.date()
                CosReflection.objects.create(
                    user=self.user,
                    content_type=prompt.content_type,
                    object_id=prompt.object_id,
                    text=text,
                    activity_date=activity_date,
                    activity_type=prompt.activity_type,
                    prompt_text=prompt.prompt_text,
                )
                return

            svc = CosReflectionService(self.user)
            svc.create_reflection(
                source_entity=source_entity,
                text=text,
                activity_type=prompt.activity_type,
                prompt_text=prompt.prompt_text,
            )
        except Exception as e:
            logger.error(
                "Failed to capture reflection from prompt %s: %s",
                prompt.pk, e,
            )

    def _apply_tone_modifier(self, prompt: CosPromptSchedule):
        """
        Apply tone modifier to prompt text based on context.

        Uses CosToneService to select context-appropriate tone and
        prepends the tone instruction to the prompt_text metadata.
        The tone is stored on the prompt for audit/analytics.
        """
        try:
            from apps.cos.services.tone_service import CosToneService

            tone_svc = CosToneService(self.user)
            tone_key, tone_instruction = tone_svc.select_tone_for_prompt(prompt)

            # Store the selected tone on the prompt metadata
            if not prompt.metadata:
                prompt.metadata = {}
            prompt.metadata["tone"] = tone_key
            if tone_instruction:
                prompt.metadata["tone_instruction"] = tone_instruction

            # Get response style instruction too
            style_instruction = tone_svc.get_response_style_instruction()
            if style_instruction:
                prompt.metadata["response_style_instruction"] = style_instruction

            prompt.save(update_fields=["metadata"])
        except Exception as e:
            logger.debug("Tone modifier not applied (non-fatal): %s", e)

    @staticmethod
    def _get_activity_icon(activity_type: str) -> str:
        """Get emoji icon for activity type."""
        icons = {
            "meeting": "📅",
            "workout": "💪",
            "bible_study": "📖",
            "prayer": "🙏",
            "devotional": "✝️",
            "journaling": "📝",
            "appointment": "🏥",
            "task": "✅",
            "default": "📌",
        }
        return icons.get(activity_type, "📌")
