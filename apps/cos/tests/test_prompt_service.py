"""
CoS v2 — Phase 4 Tests: Proactive Prompting Engine

Tests:
1. Prompt templates: detection, rendering, defaults
2. Scheduling: pre/post prompts created with correct timing
3. Dedup: no duplicate prompts for same event
4. Cancellation: cancel prompts when event is deleted
5. Delivery: get_due_prompts, deliver_prompt, deliver_all_due
6. Expiration: stale prompts expired
7. Response flow: Yes → reflection + follow-up, No → stop
8. Follow-up: captures reflection text
9. Batch delivery: deliver_all_due_for_all_users with feature flag
"""

import datetime as dt
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent
from apps.cos.models import CosPromptSchedule, CosReflection
from apps.cos.services.prompt_service import CosPromptService
from apps.cos.services.prompt_templates import (
    detect_activity_type,
    get_lead_minutes,
    get_post_delay_minutes,
    get_post_event_template,
    get_pre_event_template,
    render_template,
)

User = get_user_model()


def _create_test_user(email="cosprompt@example.com"):
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _create_future_event(user, title, hours_from_now=2, duration_hours=1):
    """Create a future calendar event."""
    start = timezone.now() + dt.timedelta(hours=hours_from_now)
    end = start + dt.timedelta(hours=duration_hours)
    return CalendarEvent.objects.create(
        user=user,
        title=title,
        start_dt=start,
        end_dt=end,
        idempotency_key=uuid4().hex,
    )


def _create_past_event(user, title, hours_ago=2, duration_hours=1):
    """Create a past calendar event."""
    end = timezone.now() - dt.timedelta(hours=hours_ago)
    start = end - dt.timedelta(hours=duration_hours)
    return CalendarEvent.objects.create(
        user=user,
        title=title,
        start_dt=start,
        end_dt=end,
        idempotency_key=uuid4().hex,
    )


# ──────────────────────────────────────────────────────────
# Template Tests
# ──────────────────────────────────────────────────────────


class PromptTemplateTests(TestCase):
    """Test activity type detection and template rendering."""

    def test_detect_workout(self):
        self.assertEqual(detect_activity_type("Morning Workout"), "workout")

    def test_detect_gym(self):
        self.assertEqual(detect_activity_type("Hit the gym"), "workout")

    def test_detect_bible_study(self):
        self.assertEqual(detect_activity_type("Bible Study Group"), "bible_study")

    def test_detect_meeting(self):
        self.assertEqual(detect_activity_type("Team Standup"), "meeting")

    def test_detect_prayer(self):
        self.assertEqual(detect_activity_type("Morning Prayer Time"), "prayer")

    def test_detect_appointment(self):
        self.assertEqual(detect_activity_type("Doctor Appointment"), "appointment")

    def test_detect_default(self):
        self.assertEqual(detect_activity_type("Something Random"), "default")

    def test_detect_case_insensitive(self):
        self.assertEqual(detect_activity_type("YOGA CLASS"), "workout")

    def test_pre_event_template_exists(self):
        template = get_pre_event_template("workout")
        self.assertIn("{title}", template)

    def test_post_event_template_exists(self):
        template = get_post_event_template("workout")
        self.assertIn("{title}", template)

    def test_default_template_fallback(self):
        template = get_pre_event_template("unknown_type")
        self.assertIn("{title}", template)

    def test_render_template(self):
        result = render_template(
            'Your "{title}" starts in {lead_minutes} minutes.',
            title="Gym Session",
            lead_minutes=15,
        )
        self.assertEqual(
            result, 'Your "Gym Session" starts in 15 minutes.'
        )

    def test_lead_minutes_per_type(self):
        self.assertEqual(get_lead_minutes("meeting"), 10)
        self.assertEqual(get_lead_minutes("workout"), 15)
        self.assertEqual(get_lead_minutes("prayer"), 5)

    def test_post_delay_per_type(self):
        self.assertEqual(get_post_delay_minutes("workout"), 10)
        self.assertEqual(get_post_delay_minutes("meeting"), 5)


# ──────────────────────────────────────────────────────────
# Scheduling Tests
# ──────────────────────────────────────────────────────────


class PromptSchedulingTests(TestCase):
    """Test CosPromptService.schedule_prompts_for_event()."""

    def setUp(self):
        self.user = _create_test_user("psched@example.com")
        self.svc = CosPromptService(self.user)

    def test_schedule_both_prompts(self):
        """Both pre and post prompts created for a future event."""
        event = _create_future_event(self.user, "Team Meeting", hours_from_now=3)
        prompts = self.svc.schedule_prompts_for_event(event)
        self.assertEqual(len(prompts), 2)
        timings = {p.timing for p in prompts}
        self.assertEqual(timings, {"pre", "post"})

    def test_pre_prompt_scheduled_before_event(self):
        """Pre prompt is scheduled before event start."""
        event = _create_future_event(self.user, "Workout", hours_from_now=3)
        prompts = self.svc.schedule_prompts_for_event(event)
        pre = next(p for p in prompts if p.timing == "pre")
        self.assertLess(pre.scheduled_for, event.start_dt)

    def test_post_prompt_scheduled_after_event(self):
        """Post prompt is scheduled after event end."""
        event = _create_future_event(self.user, "Meeting", hours_from_now=3)
        prompts = self.svc.schedule_prompts_for_event(event)
        post = next(p for p in prompts if p.timing == "post")
        self.assertGreater(post.scheduled_for, event.end_dt)

    def test_activity_type_auto_detected(self):
        """Activity type is auto-detected from title."""
        event = _create_future_event(self.user, "Morning Workout", hours_from_now=3)
        prompts = self.svc.schedule_prompts_for_event(event)
        for p in prompts:
            self.assertEqual(p.activity_type, "workout")

    def test_activity_type_override(self):
        """Activity type can be explicitly overridden."""
        event = _create_future_event(self.user, "Session", hours_from_now=3)
        prompts = self.svc.schedule_prompts_for_event(
            event, activity_type="bible_study"
        )
        for p in prompts:
            self.assertEqual(p.activity_type, "bible_study")

    def test_skip_pre(self):
        """skip_pre=True only creates post prompt."""
        event = _create_future_event(self.user, "Meeting", hours_from_now=3)
        prompts = self.svc.schedule_prompts_for_event(event, skip_pre=True)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0].timing, "post")

    def test_skip_post(self):
        """skip_post=True only creates pre prompt."""
        event = _create_future_event(self.user, "Meeting", hours_from_now=3)
        prompts = self.svc.schedule_prompts_for_event(event, skip_post=True)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0].timing, "pre")

    def test_no_pre_for_past_event(self):
        """No pre prompt for events that already started."""
        event = _create_past_event(self.user, "Past Meeting")
        prompts = self.svc.schedule_prompts_for_event(event)
        timings = {p.timing for p in prompts}
        self.assertNotIn("pre", timings)

    def test_post_still_scheduled_for_past_event(self):
        """Post prompt is still scheduled for past events (for check-in)."""
        event = _create_past_event(self.user, "Past Workout")
        prompts = self.svc.schedule_prompts_for_event(event)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0].timing, "post")

    def test_prompt_text_rendered(self):
        """Prompt text includes the event title."""
        event = _create_future_event(self.user, "Bible Study Group", hours_from_now=3)
        prompts = self.svc.schedule_prompts_for_event(event)
        for p in prompts:
            self.assertIn("Bible Study Group", p.prompt_text)


# ──────────────────────────────────────────────────────────
# Dedup Tests
# ──────────────────────────────────────────────────────────


class PromptDedupTests(TestCase):
    """Test that duplicate prompts are not created."""

    def setUp(self):
        self.user = _create_test_user("pdedup@example.com")
        self.svc = CosPromptService(self.user)

    def test_no_duplicate_prompts(self):
        """Scheduling twice for same event doesn't create duplicates."""
        event = _create_future_event(self.user, "Meeting", hours_from_now=3)
        prompts1 = self.svc.schedule_prompts_for_event(event)
        prompts2 = self.svc.schedule_prompts_for_event(event)
        self.assertEqual(len(prompts1), 2)
        self.assertEqual(len(prompts2), 0)  # Deduped
        total = CosPromptSchedule.objects.filter(
            user=self.user,
            object_id=event.pk,
        ).count()
        self.assertEqual(total, 2)


# ──────────────────────────────────────────────────────────
# Cancellation Tests
# ──────────────────────────────────────────────────────────


class PromptCancellationTests(TestCase):
    """Test prompt cancellation when events are deleted."""

    def setUp(self):
        self.user = _create_test_user("pcancel@example.com")
        self.svc = CosPromptService(self.user)

    def test_cancel_prompts_for_event(self):
        """All pending prompts canceled when event is deleted."""
        event = _create_future_event(self.user, "Meeting", hours_from_now=3)
        self.svc.schedule_prompts_for_event(event)
        canceled = self.svc.cancel_prompts_for_event(event)
        self.assertEqual(canceled, 2)
        pending = CosPromptSchedule.objects.filter(
            user=self.user,
            object_id=event.pk,
            status=CosPromptSchedule.STATUS_PENDING,
        ).count()
        self.assertEqual(pending, 0)

    def test_cancel_only_pending(self):
        """Only pending prompts are canceled, not delivered ones."""
        event = _create_future_event(self.user, "Meeting", hours_from_now=3)
        prompts = self.svc.schedule_prompts_for_event(event)
        # Deliver one
        prompts[0].mark_delivered()
        canceled = self.svc.cancel_prompts_for_event(event)
        self.assertEqual(canceled, 1)


# ──────────────────────────────────────────────────────────
# Delivery Tests
# ──────────────────────────────────────────────────────────


class PromptDeliveryTests(TestCase):
    """Test prompt delivery mechanics."""

    def setUp(self):
        self.user = _create_test_user("pdeliver@example.com")
        self.svc = CosPromptService(self.user)

    def test_get_due_prompts(self):
        """get_due_prompts returns only pending past-due prompts."""
        event = _create_future_event(self.user, "Meeting", hours_from_now=3)
        prompts = self.svc.schedule_prompts_for_event(event)

        # Neither should be due yet (scheduled in future)
        due = self.svc.get_due_prompts()
        self.assertEqual(len(due), 0)

        # Manually set one to past due
        prompts[0].scheduled_for = timezone.now() - dt.timedelta(minutes=5)
        prompts[0].save()

        due = self.svc.get_due_prompts()
        self.assertEqual(len(due), 1)

    def test_deliver_prompt(self):
        """deliver_prompt marks prompt as delivered."""
        event = _create_future_event(self.user, "Workout", hours_from_now=3)
        prompts = self.svc.schedule_prompts_for_event(event)
        prompt = prompts[0]
        prompt.scheduled_for = timezone.now() - dt.timedelta(minutes=1)
        prompt.save()

        success = self.svc.deliver_prompt(prompt)
        self.assertTrue(success)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, CosPromptSchedule.STATUS_DELIVERED)
        self.assertIsNotNone(prompt.delivered_at)

    def test_deliver_already_delivered_fails(self):
        """Can't deliver a prompt that's already delivered."""
        event = _create_future_event(self.user, "Meeting", hours_from_now=3)
        prompts = self.svc.schedule_prompts_for_event(event)
        prompt = prompts[0]
        prompt.mark_delivered()

        success = self.svc.deliver_prompt(prompt)
        self.assertFalse(success)

    def test_deliver_all_due(self):
        """deliver_all_due delivers all past-due prompts."""
        event = _create_future_event(self.user, "Meeting", hours_from_now=3)
        prompts = self.svc.schedule_prompts_for_event(event)
        for p in prompts:
            p.scheduled_for = timezone.now() - dt.timedelta(minutes=1)
            p.save()

        result = self.svc.deliver_all_due()
        self.assertEqual(result["delivered"], 2)


# ──────────────────────────────────────────────────────────
# Expiration Tests
# ──────────────────────────────────────────────────────────


class PromptExpirationTests(TestCase):
    """Test stale prompt expiration."""

    def setUp(self):
        self.user = _create_test_user("pexpire@example.com")
        self.svc = CosPromptService(self.user)

    def test_expire_stale_prompts(self):
        """Prompts scheduled more than 4 hours ago are expired."""
        event = _create_future_event(self.user, "Meeting", hours_from_now=3)
        prompts = self.svc.schedule_prompts_for_event(event)

        # Make one stale
        prompts[0].scheduled_for = timezone.now() - dt.timedelta(hours=5)
        prompts[0].save()

        expired = self.svc.expire_stale_prompts()
        self.assertEqual(expired, 1)
        prompts[0].refresh_from_db()
        self.assertEqual(prompts[0].status, CosPromptSchedule.STATUS_EXPIRED)

    def test_fresh_prompts_not_expired(self):
        """Recent prompts are not expired."""
        event = _create_future_event(self.user, "Meeting", hours_from_now=3)
        self.svc.schedule_prompts_for_event(event)
        expired = self.svc.expire_stale_prompts()
        self.assertEqual(expired, 0)


# ──────────────────────────────────────────────────────────
# Response Flow Tests
# ──────────────────────────────────────────────────────────


class PromptResponseFlowTests(TestCase):
    """Test the Yes/No response flow."""

    def setUp(self):
        self.user = _create_test_user("presponse@example.com")
        self.svc = CosPromptService(self.user)
        self.event = _create_future_event(self.user, "Workout", hours_from_now=3)
        self.prompts = self.svc.schedule_prompts_for_event(self.event)
        # Get the post prompt
        self.post_prompt = next(
            p for p in self.prompts if p.timing == "post"
        )

    def test_positive_response(self):
        """Yes response marks as responded and returns follow-up."""
        result = self.svc.handle_response(
            prompt_id=self.post_prompt.pk,
            positive=True,
            response_text="Great workout!",
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["positive"])
        self.assertIsNotNone(result["follow_up"])

        self.post_prompt.refresh_from_db()
        self.assertEqual(self.post_prompt.status, CosPromptSchedule.STATUS_RESPONDED)
        self.assertTrue(self.post_prompt.response_positive)

    def test_positive_response_captures_reflection(self):
        """Yes with text captures a CosReflection."""
        self.svc.handle_response(
            prompt_id=self.post_prompt.pk,
            positive=True,
            response_text="Felt strong and energized!",
        )
        ct = ContentType.objects.get_for_model(CalendarEvent)
        reflections = CosReflection.objects.filter(
            user=self.user,
            content_type=ct,
            object_id=self.event.pk,
        )
        self.assertEqual(reflections.count(), 1)
        self.assertEqual(reflections.first().text, "Felt strong and energized!")

    def test_negative_response_stops(self):
        """No response marks as responded with no follow-up."""
        result = self.svc.handle_response(
            prompt_id=self.post_prompt.pk,
            positive=False,
        )
        self.assertTrue(result["success"])
        self.assertFalse(result["positive"])
        self.assertIsNone(result["follow_up"])

        self.post_prompt.refresh_from_db()
        self.assertFalse(self.post_prompt.response_positive)

    def test_negative_no_reflection_captured(self):
        """No response does NOT capture a reflection."""
        self.svc.handle_response(
            prompt_id=self.post_prompt.pk,
            positive=False,
        )
        self.assertEqual(CosReflection.objects.filter(user=self.user).count(), 0)

    def test_nonexistent_prompt(self):
        """Responding to nonexistent prompt returns error."""
        result = self.svc.handle_response(
            prompt_id=999999, positive=True,
        )
        self.assertFalse(result["success"])

    def test_follow_up_captures_reflection(self):
        """Follow-up text is captured as reflection."""
        # First respond positively
        self.svc.handle_response(
            prompt_id=self.post_prompt.pk,
            positive=True,
            response_text="Yes!",
        )
        # Then send follow-up
        result = self.svc.handle_follow_up(
            prompt_id=self.post_prompt.pk,
            follow_up_text="I increased my weight on squats today.",
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["captured"])

        # Should have 2 reflections (from response + follow-up)
        ct = ContentType.objects.get_for_model(CalendarEvent)
        reflections = CosReflection.objects.filter(
            user=self.user,
            content_type=ct,
            object_id=self.event.pk,
        )
        self.assertEqual(reflections.count(), 2)


# ──────────────────────────────────────────────────────────
# Batch Delivery Tests
# ──────────────────────────────────────────────────────────


class BatchDeliveryTests(TestCase):
    """Test deliver_all_due_for_all_users with feature flag."""

    def setUp(self):
        # Clean slate — remove any pending prompts from migrations/fixtures
        CosPromptSchedule.objects.all().delete()

    def test_feature_flag_respected(self):
        """Users without cos_v2_enabled are skipped."""
        user = _create_test_user("batch1@example.com")
        # cos_v2_enabled defaults to False
        svc = CosPromptService(user)
        event = _create_future_event(user, "Meeting", hours_from_now=3)
        prompts = svc.schedule_prompts_for_event(event)
        for p in prompts:
            p.scheduled_for = timezone.now() - dt.timedelta(minutes=1)
            p.save()

        result = CosPromptService.deliver_all_due_for_all_users()
        self.assertEqual(result["delivered"], 0)  # Skipped (flag off)

    def test_enabled_users_get_delivery(self):
        """Users with cos_v2_enabled get their prompts delivered."""
        user = _create_test_user("batch2@example.com")
        user.preferences.cos_v2_enabled = True
        user.preferences.save()

        svc = CosPromptService(user)
        event = _create_future_event(user, "Workout", hours_from_now=3)
        prompts = svc.schedule_prompts_for_event(event)
        for p in prompts:
            p.scheduled_for = timezone.now() - dt.timedelta(minutes=1)
            p.save()

        result = CosPromptService.deliver_all_due_for_all_users()
        self.assertEqual(result["delivered"], 2)
        self.assertEqual(result["users"], 1)
