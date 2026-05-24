"""
Tests for Journey models — basic creation, constraints, and helpers.

Scoped per WLJ testing policy: only Journey models tested here. Does not
exercise reading-plan code.
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from apps.faith.journey.models import (
    JourneyPath,
    JourneyArc,
    JourneyDay,
    UserJourney,
    UserJourneyDayProgress,
)


User = get_user_model()


def _make_path(slug="test_path"):
    return JourneyPath.objects.create(
        slug=slug,
        name="Test Path",
        narrative_overview="...",
        difficulty_default="standard",
        is_active=False,
    )


def _make_arc(path, order=1, slug="test_arc"):
    return JourneyArc.objects.create(
        journey_path=path,
        slug=slug,
        name="Test Arc",
        era_label="Test Era",
        order=order,
        opening_note="...",
        closing_note="...",
        estimated_days=3,
        is_active=False,
    )


def _make_day(arc, day_number=1):
    return JourneyDay.objects.create(
        arc=arc,
        day_number=day_number,
        scripture_refs=["Genesis 1:1"],
        scripture_content={"translation": "WEB", "blocks": [{"ref": "Gen 1:1", "verse": 1, "text": "In the beginning...", "red_letter": False}]},
        context_before="...",
        plain_english_simple="simple version",
        plain_english_standard="standard version",
        plain_english_deeper="deeper version",
        key_insight="A short insight.",
        reflection_prompt="A question?",
        application_action="Do one small thing.",
        confusion_topics=[
            {"topic": "Q1", "plain_english_answer": "A1"},
            {"topic": "Q2", "plain_english_answer": "A2"},
            {"topic": "Q3", "plain_english_answer": "A3"},
        ],
        retention_anchor="Connects to story arc.",
    )


class JourneyPathTests(TestCase):
    def test_create_path(self):
        path = _make_path()
        self.assertEqual(path.slug, "test_path")
        self.assertFalse(path.is_active)  # default False (publish gate)
        self.assertEqual(path.difficulty_default, "standard")

    def test_path_slug_unique(self):
        _make_path(slug="dup")
        with self.assertRaises(IntegrityError):
            _make_path(slug="dup")


class JourneyArcTests(TestCase):
    def test_arc_unique_order_per_path(self):
        path = _make_path()
        _make_arc(path, order=1, slug="arc_a")
        with self.assertRaises(IntegrityError):
            _make_arc(path, order=1, slug="arc_b")

    def test_arc_unique_slug_per_path(self):
        path = _make_path()
        _make_arc(path, order=1, slug="same")
        with self.assertRaises(IntegrityError):
            _make_arc(path, order=2, slug="same")


class JourneyDayTests(TestCase):
    def test_day_unique_per_arc(self):
        path = _make_path()
        arc = _make_arc(path)
        _make_day(arc, day_number=1)
        with self.assertRaises(IntegrityError):
            _make_day(arc, day_number=1)

    def test_plain_english_for_tier(self):
        path = _make_path()
        arc = _make_arc(path)
        day = _make_day(arc)
        self.assertEqual(day.plain_english_for_tier("simple"), "simple version")
        self.assertEqual(day.plain_english_for_tier("standard"), "standard version")
        self.assertEqual(day.plain_english_for_tier("deeper"), "deeper version")
        # Unknown tier falls back to standard.
        self.assertEqual(day.plain_english_for_tier("unknown"), "standard version")


class UserJourneyTests(TestCase):
    def _make_user(self):
        return User.objects.create_user(email="t@example.com", password="x" * 16)

    def test_journey_status_field_avoids_softdelete_collision(self):
        """Confirms the lifecycle field is `journey_status`, not `status`.

        SoftDeleteModel already defines `status` (active/archived/deleted).
        Using `status` for lifecycle would silently overwrite soft-delete state.
        """
        path = _make_path()
        user = self._make_user()
        uj = UserJourney.objects.create(
            user=user,
            journey_path=path,
            journey_status="active",
            preferred_difficulty="standard",
        )
        # journey_status is the lifecycle field
        self.assertEqual(uj.journey_status, "active")
        # status is the soft-delete state, set by SoftDeleteModel
        self.assertEqual(uj.status, "active")
        # Independent — proves they don't shadow each other
        uj.status = "archived"  # archive without touching lifecycle
        uj.save(update_fields=["status"])
        uj.refresh_from_db()
        self.assertEqual(uj.status, "archived")
        self.assertEqual(uj.journey_status, "active")


class UserJourneyDayProgressTests(TestCase):
    def test_unique_per_user_journey_and_day(self):
        path = _make_path()
        arc = _make_arc(path)
        day = _make_day(arc)
        user = User.objects.create_user(email="p@example.com", password="x" * 16)
        uj = UserJourney.objects.create(user=user, journey_path=path)
        UserJourneyDayProgress.objects.create(user=user, user_journey=uj, journey_day=day)
        with self.assertRaises(IntegrityError):
            UserJourneyDayProgress.objects.create(user=user, user_journey=uj, journey_day=day)
