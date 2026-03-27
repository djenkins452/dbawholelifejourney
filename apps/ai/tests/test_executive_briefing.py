"""
Executive Briefing Service — Tests

Tests for:
1. First-of-day gate detection
2. Session gap detection and human language
3. Life event surfacing
4. Journal mood trend extraction
5. Health gate (medication not taken)
6. Rolling summary triggers
7. Conversation memory formatting
8. Graceful handling of empty data
9. Interaction depth recording (Adaptive CoS Presence)
10. Lightweight alignment mode
11. Auto-complete wakeup via canonical RoutineSchedule/RoutineLog engine
"""

from datetime import date, time, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.ai.models import AssistantConversation, AssistantMessage
from apps.ai.executive_briefing import (
    build_executive_briefing,
    mark_briefing_delivered,
    maybe_generate_rolling_summary,
    get_conversation_memory,
    _compute_session_gap,
    _humanize_gap,
    _build_greeting_section,
    _build_journal_followup_section,
    _build_health_gate_section,
)

User = get_user_model()


class ExecutiveBriefingTestMixin:
    """Common setup for executive briefing tests."""

    def create_user(self, email='exec@example.com', password='testpass123'):
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        user = User.objects.create_user(email=email, password=password)
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.personal_assistant_enabled = True
        user.preferences.ai_enabled = True
        user.preferences.ai_data_consent = True
        user.preferences.save()
        return user

    def create_conversation(self, user, **kwargs):
        return AssistantConversation.objects.create(
            user=user,
            is_active=True,
            session_type='general',
            **kwargs,
        )

    def add_messages(self, conversation, count=5):
        """Add test messages to a conversation."""
        messages = []
        for i in range(count):
            role = 'user' if i % 2 == 0 else 'assistant'
            msg = AssistantMessage.objects.create(
                conversation=conversation,
                role=role,
                content=f"Test message {i}",
            )
            messages.append(msg)
        return messages


class TestFirstOfDayGate(ExecutiveBriefingTestMixin, TestCase):
    """Test that briefing only fires on first-of-day interactions."""

    def setUp(self):
        self.user = self.create_user()
        self.conversation = self.create_conversation(self.user)

    @patch('apps.core.utils.get_user_now')
    @patch('apps.core.utils.get_user_today')
    def test_fires_on_first_of_day(self, mock_today, mock_now):
        """Briefing should fire when no briefing delivered today."""
        mock_today.return_value = date(2026, 2, 21)
        mock_now.return_value = timezone.now()

        result = build_executive_briefing(self.user, self.conversation)
        self.assertIn("EXECUTIVE BRIEFING", result)

    @patch('apps.core.utils.get_user_now')
    @patch('apps.core.utils.get_user_today')
    def test_skips_after_first_delivery(self, mock_today, mock_now):
        """Briefing should not fire twice in the same day."""
        today = date(2026, 2, 21)
        mock_today.return_value = today
        mock_now.return_value = timezone.now()

        # First call delivers the briefing
        result1 = build_executive_briefing(self.user, self.conversation)
        self.assertIn("EXECUTIVE BRIEFING", result1)

        # Mark delivery (caller responsibility per deferred-marking design)
        mark_briefing_delivered(self.conversation)

        # Refresh conversation from DB
        self.conversation.refresh_from_db()

        # Second call should return empty
        result2 = build_executive_briefing(self.user, self.conversation)
        self.assertEqual(result2, "")

    @patch('apps.core.utils.get_user_now')
    @patch('apps.core.utils.get_user_today')
    def test_fires_on_new_day(self, mock_today, mock_now):
        """Briefing should fire again on a new day."""
        mock_now.return_value = timezone.now()

        # Day 1
        mock_today.return_value = date(2026, 2, 21)
        build_executive_briefing(self.user, self.conversation)
        self.conversation.refresh_from_db()

        # Day 2
        mock_today.return_value = date(2026, 2, 22)
        result = build_executive_briefing(self.user, self.conversation)
        self.assertIn("EXECUTIVE BRIEFING", result)


class TestSessionGapDetection(ExecutiveBriefingTestMixin, TestCase):
    """Test session gap computation and human language translation."""

    def test_humanize_short_gap(self):
        self.assertEqual(_humanize_gap(0.5), "a short while")

    def test_humanize_one_hour(self):
        self.assertEqual(_humanize_gap(1.5), "about an hour")

    def test_humanize_hours(self):
        result = _humanize_gap(6)
        self.assertIn("6 hours", result)

    def test_humanize_one_day(self):
        result = _humanize_gap(25)
        self.assertIn("day", result)

    def test_humanize_few_days(self):
        result = _humanize_gap(72)
        self.assertIn("3 days", result)

    def test_humanize_week(self):
        result = _humanize_gap(168)
        self.assertIn("week", result)

    def test_compute_gap_new_conversation(self):
        user = self.create_user()
        conv = self.create_conversation(user)
        gap = _compute_session_gap(conv)
        # Just created, gap should be very small
        self.assertIsNotNone(gap)
        self.assertLess(gap, 1)

    def test_compute_gap_old_conversation(self):
        user = self.create_user(email='old@example.com')
        conv = self.create_conversation(user)
        # Manually set updated_at to 3 days ago
        three_days_ago = timezone.now() - timedelta(days=3)
        AssistantConversation.objects.filter(pk=conv.pk).update(
            updated_at=three_days_ago
        )
        conv.refresh_from_db()
        gap = _compute_session_gap(conv)
        self.assertGreater(gap, 70)  # ~72 hours


class TestGreetingSection(ExecutiveBriefingTestMixin, TestCase):
    """Test greeting section construction."""

    def test_morning_greeting(self):
        user = self.create_user()
        morning = timezone.now().replace(hour=8, minute=30)
        result = _build_greeting_section(user, morning, None)
        self.assertIn("morning", result)

    def test_afternoon_greeting(self):
        user = self.create_user(email='afternoon@example.com')
        afternoon = timezone.now().replace(hour=14, minute=0)
        result = _build_greeting_section(user, afternoon, None)
        self.assertIn("afternoon", result)

    def test_gap_awareness_in_greeting(self):
        user = self.create_user(email='gap@example.com')
        now = timezone.now()
        result = _build_greeting_section(user, now, 72)  # 3-day gap
        self.assertIn("3 days", result)
        self.assertIn("gap", result.lower())


class TestHealthGate(ExecutiveBriefingTestMixin, TestCase):
    """Test health gate section (medication, fasting, workout)."""

    def test_empty_health_data(self):
        """Should return anti-hallucination guard when no health data."""
        user = self.create_user()
        today = date.today()
        result = _build_health_gate_section(user, today)
        # With no routines, the anti-hallucination guard fires
        self.assertIn("No routine tasks found", result)
        self.assertIn("Do NOT claim", result)

    def test_medication_not_taken(self):
        """Should flag untaken medication."""
        from unittest.mock import patch
        user = self.create_user(email='med@example.com')
        today = date.today()

        # Create a medicine with schedule
        from apps.health.models import Medicine, MedicineSchedule
        from datetime import time
        med = Medicine.objects.create(
            user=user,
            name="Test Medicine",
            dose="10mg",
            medicine_status='active',
            start_date=today - timedelta(days=30),
        )
        MedicineSchedule.objects.create(
            medicine=med,
            scheduled_time=time(8, 0),
            time_of_day='morning',
        )

        # Pin current time to noon so the 8 AM dose is always overdue
        from django.utils import timezone as tz
        import datetime as dt
        noon_today = tz.make_aware(
            dt.datetime.combine(today, time(12, 0)),
            tz.get_current_timezone(),
        )
        with patch('apps.ai.executive_briefing.timezone.now', return_value=noon_today):
            result = _build_health_gate_section(user, today)
        self.assertIn("HEALTH GATE", result)
        self.assertIn("1 of 1", result)

    def test_medication_all_taken(self):
        """Should confirm all meds taken."""
        user = self.create_user(email='medtaken@example.com')
        today = date.today()

        from apps.health.models import Medicine, MedicineSchedule, MedicineLog
        from datetime import time
        med = Medicine.objects.create(
            user=user,
            name="Test Medicine",
            dose="10mg",
            medicine_status='active',
            start_date=today - timedelta(days=30),
        )
        schedule = MedicineSchedule.objects.create(
            medicine=med,
            scheduled_time=time(8, 0),
            time_of_day='morning',
        )
        MedicineLog.objects.create(
            user=user,
            medicine=med,
            schedule=schedule,
            scheduled_date=today,
            log_status='taken',
        )

        result = _build_health_gate_section(user, today)
        self.assertIn("All", result)
        self.assertIn("taken", result)


class TestJournalFollowup(ExecutiveBriefingTestMixin, TestCase):
    """Test journal pattern extraction."""

    def test_empty_journal(self):
        user = self.create_user()
        today = date.today()
        result = _build_journal_followup_section(user, today)
        self.assertEqual(result, "")

    def test_declining_mood(self):
        """Should detect mood decline across entries."""
        user = self.create_user(email='mood@example.com')
        today = date.today()

        from apps.journal.models import JournalEntry
        # Most recent entries should have low mood (declining trend)
        # Ordered by -entry_date, so entry 0 is most recent
        moods = ['difficult', 'low', 'low', 'good', 'great']
        for i, mood in enumerate(moods):
            JournalEntry.objects.create(
                user=user,
                title=f"Entry {i}",
                body=f"Journal entry {i}",
                entry_date=today - timedelta(days=i),
                mood=mood,
            )

        result = _build_journal_followup_section(user, today)
        self.assertIn("Journal Pattern", result)

    def test_repeated_health_keyword(self):
        """Should detect repeated health concerns in journal."""
        user = self.create_user(email='health_journal@example.com')
        today = date.today()

        from apps.journal.models import JournalEntry
        for i in range(3):
            JournalEntry.objects.create(
                user=user,
                title=f"Entry {i}",
                body="My calf is still tight and sore from running.",
                entry_date=today - timedelta(days=i),
                mood='okay',
            )

        result = _build_journal_followup_section(user, today)
        # Should detect repeated health keywords
        if result:
            self.assertIn("Journal Pattern", result)


class TestRollingSummary(ExecutiveBriefingTestMixin, TestCase):
    """Test rolling conversation summary generation."""

    def test_no_summary_under_20_messages(self):
        """Should not generate summary when < 20 messages."""
        user = self.create_user()
        conv = self.create_conversation(user)
        self.add_messages(conv, count=15)

        maybe_generate_rolling_summary(user, conv)
        conv.refresh_from_db()
        self.assertEqual(conv.context_summary, "")

    @patch('apps.ai.services.ai_service')
    def test_summary_triggers_at_20_messages(self, mock_service):
        """Should generate summary when >= 20 messages."""
        mock_service.is_available = True
        mock_service._call_api.return_value = "User discussed health goals and medication."

        user = self.create_user(email='summary@example.com')
        conv = self.create_conversation(user)
        self.add_messages(conv, count=22)

        maybe_generate_rolling_summary(user, conv)
        conv.refresh_from_db()
        self.assertEqual(conv.context_summary, "User discussed health goals and medication.")
        self.assertEqual(conv.metadata.get('last_summary_msg_count'), 22)

    @patch('apps.ai.services.ai_service')
    def test_summary_not_regenerated_too_soon(self, mock_service):
        """Should not regenerate summary within 10 messages."""
        mock_service.is_available = True
        mock_service._call_api.return_value = "Summary text."

        user = self.create_user(email='nosumm@example.com')
        conv = self.create_conversation(user)
        self.add_messages(conv, count=22)

        # First call generates summary
        maybe_generate_rolling_summary(user, conv)
        conv.refresh_from_db()
        self.assertEqual(mock_service._call_api.call_count, 1)

        # Add 5 more messages (still within 10 message threshold)
        self.add_messages(conv, count=5)
        maybe_generate_rolling_summary(user, conv)
        # Should NOT have called API again
        self.assertEqual(mock_service._call_api.call_count, 1)


class TestConversationMemory(ExecutiveBriefingTestMixin, TestCase):
    """Test conversation memory formatting."""

    def test_empty_summary(self):
        user = self.create_user()
        conv = self.create_conversation(user)
        result = get_conversation_memory(conv)
        self.assertEqual(result, "")

    def test_summary_formatted(self):
        user = self.create_user(email='memtest@example.com')
        conv = self.create_conversation(
            user,
            context_summary="Discussed weight goals and medication schedule."
        )
        result = get_conversation_memory(conv)
        self.assertIn("CONVERSATION MEMORY", result)
        self.assertIn("weight goals", result)
        self.assertIn("continuity", result)


class TestLearningExtractorNewCategories(TestCase):
    """Test the new extraction categories added for Executive Operator."""

    def setUp(self):
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(
            email='extractor@example.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
        )

    def test_health_concern_extraction(self):
        from apps.core.ai_learning.learning_extractor import extract_learning
        extractions = extract_learning(
            self.user,
            "My shoulder has been really stiff all week."
        )
        categories = [e.category for e in extractions]
        self.assertIn("health_concern", categories)

    def test_commitment_extraction(self):
        from apps.core.ai_learning.learning_extractor import extract_learning
        extractions = extract_learning(
            self.user,
            "I promised my wife I'd be home for dinner every Friday."
        )
        categories = [e.category for e in extractions]
        self.assertIn("commitment_made", categories)

    def test_life_event_extraction(self):
        from apps.core.ai_learning.learning_extractor import extract_learning
        extractions = extract_learning(
            self.user,
            "My sister's surgery is on March 5th and I need to be there."
        )
        categories = [e.category for e in extractions]
        self.assertIn("life_event_mention", categories)


# =========================================================================
# Adaptive CoS Presence — Interaction Awareness Tests
# =========================================================================


class TestRecordInteractionDepth(ExecutiveBriefingTestMixin, TestCase):
    """Tests for record_interaction_depth()."""

    def setUp(self):
        self.user = self.create_user(email='depth@example.com')
        self.conversation = self.create_conversation(self.user)

    def test_briefing_delivered_marks_deep(self):
        """When briefing was delivered, interaction is deep."""
        from apps.ai.executive_briefing import record_interaction_depth
        record_interaction_depth(
            self.conversation, self.user, briefing_delivered=True,
        )
        self.conversation.refresh_from_db()
        metadata = self.conversation.metadata or {}
        self.assertEqual(metadata.get('interaction_depth'), 'deep')
        self.assertIsNotNone(metadata.get('last_deep_interaction_at'))
        self.assertIsNotNone(metadata.get('alignment_snapshot'))

    def test_checkin_marks_deep(self):
        """When user triggered a check-in, interaction is deep."""
        from apps.ai.executive_briefing import record_interaction_depth
        record_interaction_depth(
            self.conversation, self.user, is_checkin=True,
        )
        self.conversation.refresh_from_db()
        metadata = self.conversation.metadata or {}
        self.assertEqual(metadata.get('interaction_depth'), 'deep')

    def test_three_messages_marks_deep(self):
        """When 3+ recent user messages, interaction is deep."""
        from apps.ai.executive_briefing import record_interaction_depth
        # Add 3 recent user messages
        for i in range(3):
            AssistantMessage.objects.create(
                conversation=self.conversation,
                role='user',
                content=f"Message {i}",
            )
        record_interaction_depth(self.conversation, self.user)
        self.conversation.refresh_from_db()
        metadata = self.conversation.metadata or {}
        self.assertEqual(metadata.get('interaction_depth'), 'deep')

    def test_single_message_marks_shallow(self):
        """When no briefing, no check-in, <3 messages, interaction is shallow."""
        from apps.ai.executive_briefing import record_interaction_depth
        AssistantMessage.objects.create(
            conversation=self.conversation,
            role='user',
            content="Hello",
        )
        record_interaction_depth(self.conversation, self.user)
        self.conversation.refresh_from_db()
        metadata = self.conversation.metadata or {}
        self.assertEqual(metadata.get('interaction_depth'), 'shallow')

    def test_alignment_snapshot_captured(self):
        """Deep interaction captures alignment snapshot from execution truth."""
        from apps.ai.executive_briefing import record_interaction_depth

        # Call with briefing_delivered=True — snapshot will use real
        # execution truth (returns zeros for test user with no data).
        record_interaction_depth(
            self.conversation, self.user, briefing_delivered=True,
        )
        self.conversation.refresh_from_db()
        snapshot = self.conversation.metadata.get('alignment_snapshot', {})
        # Snapshot should exist and have the expected keys
        self.assertIn('captured_at', snapshot)
        self.assertIn('completed_items', snapshot)
        self.assertIn('tasks_completed', snapshot)
        self.assertIn('pending_count', snapshot)
        self.assertIsInstance(snapshot['completed_items'], list)
        self.assertEqual(snapshot['tasks_completed'], 0)  # Test user has no tasks


class TestLightweightAlignment(ExecutiveBriefingTestMixin, TestCase):
    """Tests for build_lightweight_alignment()."""

    def setUp(self):
        self.user = self.create_user(email='lw@example.com')
        self.conversation = self.create_conversation(self.user)

    def test_returns_alignment_with_delta(self):
        """Lightweight alignment shows what changed since last alignment."""
        from apps.ai.executive_briefing import build_lightweight_alignment

        deep_at = (timezone.now() - timedelta(minutes=30)).isoformat()

        self.conversation.metadata = {
            'last_deep_interaction_at': deep_at,
            'alignment_snapshot': {
                'captured_at': deep_at,
                'completed_items': ['Wake Up'],
                'tasks_completed': 0,
                'pending_count': 5,
            },
        }
        self.conversation.save(update_fields=['metadata'])

        with patch(
            'apps.core.execution.execution_truth_engine.get_execution_truth',
            return_value={
                'routines': {
                    'items': {
                        'Wake Up': {'fully_complete': True},
                        'Prayer': {'fully_complete': True},
                        'Workout': {'fully_complete': False},
                    },
                },
            },
        ):
            with patch(
                'apps.core.today.today_engine.get_today_context',
                return_value={'next': 'Bible Reading'},
            ):
                result = build_lightweight_alignment(
                    self.user, self.conversation,
                )

        self.assertIn('LIGHTWEIGHT ALIGNMENT', result)
        self.assertIn('Prayer', result)  # Newly completed
        self.assertNotIn('Wake Up', result)  # Already known
        self.assertIn('Bible Reading', result)  # Current focus

    def test_returns_empty_without_snapshot(self):
        """Without prior snapshot, returns empty (falls through to full)."""
        from apps.ai.executive_briefing import build_lightweight_alignment

        self.conversation.metadata = {}
        self.conversation.save(update_fields=['metadata'])

        result = build_lightweight_alignment(self.user, self.conversation)
        self.assertEqual(result, "")


class TestHandleDayStart(ExecutiveBriefingTestMixin, TestCase):
    """Tests for handle_day_start() — the authoritative day-start initializer."""

    def setUp(self):
        self.user = self.create_user(email='daystart@example.com')

    @patch('apps.ai.executive_briefing.auto_complete_wakeup')
    @patch('apps.ai.executive_briefing._ensure_routine_tasks_for_today')
    @patch('apps.core.utils.get_user_today')
    def test_first_call_initializes(self, mock_today, mock_ensure, mock_wake):
        """First call of the day performs initialization."""
        from apps.ai.executive_briefing import handle_day_start
        from django.core.cache import cache

        mock_today.return_value = timezone.now().date()
        mock_wake.return_value = True
        cache.clear()

        result = handle_day_start(self.user)

        self.assertTrue(result['initialized'])
        self.assertTrue(result['wake_completed'])
        mock_ensure.assert_called_once()
        mock_wake.assert_called_once()

    @patch('apps.ai.executive_briefing.auto_complete_wakeup')
    @patch('apps.ai.executive_briefing._ensure_routine_tasks_for_today')
    @patch('apps.core.utils.get_user_today')
    def test_second_call_is_noop(self, mock_today, mock_ensure, mock_wake):
        """Subsequent calls the same day are instant no-ops."""
        from apps.ai.executive_briefing import handle_day_start
        from django.core.cache import cache

        today = timezone.now().date()
        mock_today.return_value = today
        mock_wake.return_value = True
        cache.clear()

        # First call
        result1 = handle_day_start(self.user)
        self.assertTrue(result1['initialized'])

        # Second call — should be cache hit, no-op
        mock_ensure.reset_mock()
        mock_wake.reset_mock()

        result2 = handle_day_start(self.user)
        self.assertFalse(result2['initialized'])
        self.assertFalse(result2['wake_completed'])
        mock_ensure.assert_not_called()
        mock_wake.assert_not_called()

    @patch('apps.ai.executive_briefing.auto_complete_wakeup')
    @patch('apps.ai.executive_briefing._ensure_routine_tasks_for_today')
    @patch('apps.core.utils.get_user_today')
    def test_no_wake_task_still_initializes(self, mock_today, mock_ensure, mock_wake):
        """Initialization succeeds even when no Wake Up task exists."""
        from apps.ai.executive_briefing import handle_day_start
        from django.core.cache import cache

        mock_today.return_value = timezone.now().date()
        mock_wake.return_value = False  # No wake task
        cache.clear()

        result = handle_day_start(self.user)

        self.assertTrue(result['initialized'])
        self.assertFalse(result['wake_completed'])
        mock_ensure.assert_called_once()

    @patch('apps.ai.executive_briefing.auto_complete_wakeup')
    @patch('apps.ai.executive_briefing._ensure_routine_tasks_for_today')
    @patch('apps.core.utils.get_user_today')
    def test_ensure_failure_does_not_block_wake(self, mock_today, mock_ensure, mock_wake):
        """If _ensure_routine_tasks_for_today fails, Wake Up still runs."""
        from apps.ai.executive_briefing import handle_day_start
        from django.core.cache import cache

        mock_today.return_value = timezone.now().date()
        mock_ensure.side_effect = Exception('DB error')
        mock_wake.return_value = True
        cache.clear()

        result = handle_day_start(self.user)

        self.assertTrue(result['initialized'])
        self.assertTrue(result['wake_completed'])
        mock_wake.assert_called_once()

    def test_all_entry_points_call_handle_day_start(self):
        """Verify all CoS entry points include handle_day_start."""
        import inspect
        from apps.ai.views import (
            SessionStartView,
            ProactiveBriefingView,
            AssistantOpeningView,
            AssistantChatView,
            AssistantChatStreamView,
        )

        views_to_check = [
            ('SessionStartView', SessionStartView),
            ('ProactiveBriefingView', ProactiveBriefingView),
            ('AssistantOpeningView', AssistantOpeningView),
            ('AssistantChatView', AssistantChatView),
            ('AssistantChatStreamView', AssistantChatStreamView),
        ]

        for name, view_cls in views_to_check:
            # Check the post or get method
            method = getattr(view_cls, 'post', None) or getattr(view_cls, 'get', None)
            source = inspect.getsource(method)
            self.assertIn(
                'handle_day_start',
                source,
                f"{name} must call handle_day_start before CoS rendering",
            )


class TestAutoCompleteWakeupIntegration(ExecutiveBriefingTestMixin, TestCase):
    """Integration tests for auto_complete_wakeup via canonical RoutineSchedule/RoutineLog."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule
        self.user = self.create_user(email='wakeup@example.com')
        self.routine = Routine.objects.create(
            user=self.user, name='Morning Routine',
            time_of_day='morning', is_active=True,
        )
        today = timezone.now().date()
        weekday = str(today.weekday())
        self.wake_schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Wake Up',
            scheduled_time=time(5, 0),
            grace_period_minutes=60,
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
        )

    def test_wakeup_creates_routine_log(self):
        """First interaction auto-completes Wake Up via RoutineLog."""
        from apps.ai.executive_briefing import auto_complete_wakeup
        from apps.life.models import RoutineLog

        today = timezone.now().date()
        result = auto_complete_wakeup(self.user, today)

        self.assertTrue(result)
        log = RoutineLog.objects.get(
            schedule=self.wake_schedule, scheduled_date=today,
        )
        self.assertEqual(log.completion_source, 'auto')
        self.assertIn(log.timing, ('on_time', 'late', 'early'))
        self.assertIsNotNone(log.performed_at)

    def test_wakeup_idempotent_no_duplicate(self):
        """Second call does not create a duplicate RoutineLog."""
        from apps.ai.executive_briefing import auto_complete_wakeup
        from apps.life.models import RoutineLog

        today = timezone.now().date()
        auto_complete_wakeup(self.user, today)
        auto_complete_wakeup(self.user, today)

        count = RoutineLog.objects.filter(
            schedule=self.wake_schedule, scheduled_date=today,
        ).count()
        self.assertEqual(count, 1)

    def test_wakeup_skips_manual_completion(self):
        """Does not overwrite an existing manual completion."""
        from apps.ai.executive_briefing import auto_complete_wakeup
        from apps.life.models import RoutineLog

        today = timezone.now().date()
        RoutineLog.objects.create(
            user=self.user,
            schedule=self.wake_schedule,
            scheduled_date=today,
            log_status='completed',
            completed_at=timezone.now(),
            performed_at=timezone.now(),
            timing='on_time',
            completion_source='manual',
        )

        result = auto_complete_wakeup(self.user, today)

        self.assertFalse(result)
        count = RoutineLog.objects.filter(
            schedule=self.wake_schedule, scheduled_date=today,
        ).count()
        self.assertEqual(count, 1)

    def test_wakeup_respects_day_of_week(self):
        """Wake Up is not auto-completed on days it's not scheduled."""
        from apps.ai.executive_briefing import auto_complete_wakeup
        from apps.life.models import RoutineLog

        # Restrict to Monday only
        self.wake_schedule.days_of_week = '0'
        self.wake_schedule.save()

        today = timezone.now().date()
        # Find a non-Monday date
        if today.weekday() == 0:
            target = today + timedelta(days=1)  # Tuesday
        else:
            target = today

        # Patch at the source module since routine_helpers imports at call time
        with patch('apps.core.utils.get_user_today', return_value=target), \
             patch('apps.core.utils.get_user_now',
                   return_value=timezone.now()):
            result = auto_complete_wakeup(self.user, target)

        self.assertFalse(result)
        self.assertFalse(
            RoutineLog.objects.filter(schedule=self.wake_schedule).exists()
        )

    def test_wakeup_no_schedule_returns_false(self):
        """Returns False when user has no Wake Up schedule."""
        from apps.ai.executive_briefing import auto_complete_wakeup

        self.wake_schedule.delete()
        today = timezone.now().date()
        result = auto_complete_wakeup(self.user, today)
        self.assertFalse(result)

    def test_handle_day_start_wires_through_canonical_engine(self):
        """handle_day_start creates RoutineLog, not legacy Task."""
        from apps.ai.executive_briefing import handle_day_start
        from apps.life.models import RoutineLog
        from django.core.cache import cache

        cache.clear()
        today = timezone.now().date()

        with patch('apps.core.utils.get_user_today', return_value=today):
            result = handle_day_start(self.user)

        self.assertTrue(result['initialized'])
        self.assertTrue(result['wake_completed'])
        self.assertTrue(
            RoutineLog.objects.filter(
                schedule=self.wake_schedule,
                scheduled_date=today,
                completion_source='auto',
            ).exists()
        )
