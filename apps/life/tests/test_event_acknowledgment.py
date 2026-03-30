"""
Tests for deterministic significant event acknowledgment.

Verifies:
1. Acknowledgment builder generates correct text for each event type
2. Relationship priority affects acknowledgment wording
3. Multiple events are combined
4. No events = no acknowledgment
5. Idempotent injection (no duplicate if LLM already included)
"""
import datetime

from django.conf import settings
from django.test import TestCase

from apps.users.models import User, TermsAcceptance


def _create_test_user(email="ack_test@example.com"):
    """Create a test user with required onboarding."""
    user = User.objects.create_user(
        email=email, password="testpass123",
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class TestBuildEventAcknowledgment(TestCase):
    """Test the deterministic acknowledgment builder."""

    def setUp(self):
        self.user = _create_test_user()

    def test_no_events_returns_none(self):
        """No significant events today → None."""
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )
        result = build_event_acknowledgment(self.user)
        self.assertIsNone(result)

    def test_birthday_today_acknowledged(self):
        """A birthday today returns acknowledgment text."""
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="Mom's Birthday",
            event_type="birthday",
            event_date=today,
            person_name="Mom",
            original_year=1960,
        )

        result = build_event_acknowledgment(self.user)
        self.assertIsNotNone(result)
        self.assertIn("Mom", result)
        self.assertIn("birthday", result.lower())

    def test_self_birthday_today(self):
        """User's own birthday gets warm acknowledgment."""
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="My Birthday",
            event_type="birthday",
            event_date=today,
            person_name="Danny",
            original_year=1981,
        )

        result = build_event_acknowledgment(self.user)
        self.assertIsNotNone(result)
        self.assertIn("Happy birthday", result)
        self.assertIn("Danny", result)

    def test_anniversary_today(self):
        """Anniversary today is acknowledged."""
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="Wedding Anniversary",
            event_type="anniversary",
            event_date=today,
            person_name="",
            original_year=2016,
        )

        result = build_event_acknowledgment(self.user)
        self.assertIsNotNone(result)
        self.assertIn("anniversary", result.lower())
        years = today.year - 2016
        self.assertIn(str(years), result)

    def test_memorial_today(self):
        """Memorial event today is respectfully acknowledged."""
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="Dad's Memorial",
            event_type="memorial",
            event_date=today,
            person_name="Dad",
        )

        result = build_event_acknowledgment(self.user)
        self.assertIsNotNone(result)
        self.assertIn("Remembering", result)
        self.assertIn("Dad", result)

    def test_multiple_events_combined(self):
        """Multiple today events are all acknowledged."""
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="Mom's Birthday",
            event_type="birthday",
            event_date=today,
            person_name="Mom",
        )
        SignificantEvent.objects.create(
            user=self.user,
            title="Wedding Anniversary",
            event_type="anniversary",
            event_date=today,
            person_name="",
        )

        result = build_event_acknowledgment(self.user)
        self.assertIsNotNone(result)
        self.assertIn("Mom", result)
        self.assertIn("anniversary", result.lower())

    def test_future_event_not_included(self):
        """Event tomorrow should not generate acknowledgment."""
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )

        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        SignificantEvent.objects.create(
            user=self.user,
            title="Future Event",
            event_type="birthday",
            event_date=tomorrow,
            person_name="Someone",
        )

        result = build_event_acknowledgment(self.user)
        self.assertIsNone(result)


class TestFormatAcknowledgment(TestCase):
    """Test the acknowledgment text formatter."""

    def test_ordinal_suffix(self):
        """Ordinal suffixes are correct."""
        from apps.life.services.event_acknowledgment import _ordinal

        self.assertEqual(_ordinal(1), "1st")
        self.assertEqual(_ordinal(2), "2nd")
        self.assertEqual(_ordinal(3), "3rd")
        self.assertEqual(_ordinal(4), "4th")
        self.assertEqual(_ordinal(11), "11th")
        self.assertEqual(_ordinal(12), "12th")
        self.assertEqual(_ordinal(13), "13th")
        self.assertEqual(_ordinal(21), "21st")
        self.assertEqual(_ordinal(22), "22nd")
        self.assertEqual(_ordinal(23), "23rd")
        self.assertEqual(_ordinal(100), "100th")
        self.assertEqual(_ordinal(101), "101st")
        self.assertEqual(_ordinal(111), "111th")


class TestInjectionIdempotency(TestCase):
    """Test that acknowledgment injection is idempotent."""

    def setUp(self):
        self.user = _create_test_user(email="idem_test@example.com")

    def test_no_duplicate_when_llm_already_included(self):
        """If LLM response already contains the ack, don't inject again."""
        from apps.life.models import SignificantEvent

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="Mom's Birthday",
            event_type="birthday",
            event_date=today,
            person_name="Mom",
        )

        from apps.ai.personal_assistant import PersonalAssistant
        pa = PersonalAssistant(self.user)

        # LLM response already mentions the birthday
        llm_response = "Today is Mom's birthday! Here's your morning status..."
        result = pa._inject_event_acknowledgment(llm_response)

        # Should NOT double up
        self.assertEqual(result.count("Mom"), llm_response.count("Mom"))

    def test_injection_when_llm_missed(self):
        """If LLM response doesn't mention the event, inject it."""
        from apps.life.models import SignificantEvent

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="Mom's Birthday",
            event_type="birthday",
            event_date=today,
            person_name="Mom",
        )

        from apps.ai.personal_assistant import PersonalAssistant
        pa = PersonalAssistant(self.user)

        # LLM response doesn't mention the birthday at all
        llm_response = "Good morning! Here's your daily status."
        result = pa._inject_event_acknowledgment(llm_response)

        # Should be prepended
        self.assertIn("Mom", result)
        self.assertIn("birthday", result.lower())
        self.assertTrue(result.index("Mom") < result.index("Good morning"))

    def test_no_events_no_change(self):
        """No events → response returned unchanged."""
        from apps.ai.personal_assistant import PersonalAssistant
        pa = PersonalAssistant(self.user)

        llm_response = "Good morning! Here's your daily status."
        result = pa._inject_event_acknowledgment(llm_response)

        self.assertEqual(result, llm_response)
