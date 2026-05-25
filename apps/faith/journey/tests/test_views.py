"""
View tests for the Journey reading flow.

Scoped: exercises only Journey views + the annotation reuse endpoints.
Does not exercise the existing reading-plan views.
"""

import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.faith.models import BibleHighlight, BibleBookmark, BibleStudyNote, SavedVerse
from apps.faith.journey.models import JourneyPath, JourneyArc, JourneyDay, UserJourney
from apps.faith.journey.services import (
    can_view_day,
    get_active_journey,
    get_current_day,
    parse_reference,
)


User = get_user_model()


def _make_user(email="t1@example.com"):
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class JourneyDayViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Load the real Arc 1 (Creation → Egypt) to test end-to-end with authored content.
        call_command("load_journey_path", "walking_with_god")
        cls.path = JourneyPath.objects.get(slug="walking_with_god")
        cls.arc = JourneyArc.objects.get(slug="creation_to_egypt")
        cls.day = JourneyDay.objects.get(arc=cls.arc, day_number=1)

    def setUp(self):
        self.user = _make_user("view-tester@example.com")
        self.client = Client()
        self.client.force_login(self.user)

    def _start_journey(self):
        """Helper — create an active UserJourney for the test user."""
        return UserJourney.objects.create(
            user=self.user,
            journey_path=self.path,
            current_arc=self.arc,
            current_day_number=1,
            journey_status="active",
            preferred_difficulty="standard",
        )

    def test_today_with_no_journey_renders_start_screen(self):
        # Path defaults to is_active=False so users can't start it yet.
        resp = self.client.get(reverse("journey:today"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Walking With God Through Scripture", resp.content)

    def test_today_with_active_journey_renders_current_day(self):
        self._start_journey()
        resp = self.client.get(reverse("journey:today"))
        self.assertEqual(resp.status_code, 200)
        # Locator
        self.assertIn(b"Day 1", resp.content)
        # Scripture content
        self.assertIn(b"Genesis", resp.content)
        # Section labels (quiet typography)
        self.assertIn(b"Setting the scene", resp.content)
        self.assertIn(b"Plain English", resp.content)

        # Verify reverence: scope to the journey reading surface itself
        # (page chrome / shared nav may legitimately mention streaks elsewhere).
        import re
        content = resp.content.decode("utf-8")
        m = re.search(r'<div class="journey-wrap"[^>]*data-testid="journey-day"[^>]*>(.*?)</div>\s*<script', content, re.DOTALL)
        self.assertIsNotNone(m, "journey-wrap with data-testid=journey-day not found")
        journey_surface = m.group(1).lower()
        # No streak language on the reading surface itself
        self.assertNotIn("streak", journey_surface)
        # No Beth / chat affordance on this surface in Phase 1
        self.assertNotIn("ask the assistant", journey_surface)
        self.assertNotIn("chief of staff", journey_surface)

    def test_today_serves_user_preferred_difficulty(self):
        uj = self._start_journey()
        uj.preferred_difficulty = "deeper"
        uj.save()
        resp = self.client.get(reverse("journey:today"))
        self.assertEqual(resp.status_code, 200)
        # Deeper tier mentions Hebrew vocabulary (bara) — proof of tier selection
        self.assertIn(b"bara", resp.content)

    def test_review_route_renders_past_day(self):
        self._start_journey()
        resp = self.client.get(reverse("journey:review_day", args=[self.arc.slug, 1]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Day 1", resp.content)

    def test_review_route_forbids_future_day(self):
        # User on day 15; trying to access day 16 should 403 (no future days authored anyway).
        uj = self._start_journey()
        # Manually create a future authored day to test the guard.
        future_day = JourneyDay.objects.create(
            arc=self.arc,
            day_number=99,
            scripture_refs=["Exodus 99:1"],
            scripture_content={"translation": "WEB", "blocks": [{"ref": "Ex 99:1", "verse": 1, "text": "x", "red_letter": False}]},
            context_before="x",
            plain_english_simple="x",
            plain_english_standard="x",
            plain_english_deeper="x",
            key_insight="x",
            reflection_prompt="x",
            application_action="x",
            confusion_topics=[{"topic": "a", "plain_english_answer": "b"}, {"topic": "c", "plain_english_answer": "d"}, {"topic": "e", "plain_english_answer": "f"}],
            retention_anchor="x",
        )
        self.assertFalse(can_view_day(uj, future_day))
        resp = self.client.get(reverse("journey:review_day", args=[self.arc.slug, 99]))
        self.assertEqual(resp.status_code, 403)

    def test_settings_page_renders(self):
        self._start_journey()
        resp = self.client.get(reverse("journey:settings"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Difficulty", resp.content)
        self.assertIn(b"Daily reminder", resp.content)

    def test_complete_day_advances(self):
        uj = self._start_journey()
        resp = self.client.post(
            reverse("journey:complete_day", args=[self.arc.slug, 1]),
            {"reflection_notes": "First reflection.", "application_committed": "on"},
        )
        # Redirects to today/
        self.assertEqual(resp.status_code, 302)
        uj.refresh_from_db()
        # Arc 1 has 7 days authored — completing Day 1 advances to Day 2.
        # Journey stays active (no arc completion yet, no next arc to spawn).
        self.assertEqual(uj.journey_status, "active")
        self.assertEqual(uj.current_day_number, 2)


class WelcomeBackTests(TestCase):
    """Welcome-back banner appears when ≥3 days since last_visited_at."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_journey_path", "walking_with_god")

    def setUp(self):
        self.user = _make_user("welcomeback@example.com")
        self.client = Client()
        self.client.force_login(self.user)
        from datetime import timedelta
        from django.utils import timezone
        self.uj = UserJourney.objects.create(
            user=self.user,
            journey_path=JourneyPath.objects.get(slug="walking_with_god"),
            current_arc=JourneyArc.objects.get(slug="creation_to_egypt"),
            current_day_number=1,
            last_visited_at=timezone.now() - timedelta(days=5),
        )

    def test_banner_renders_after_three_day_gap(self):
        resp = self.client.get(reverse("journey:today"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Welcome back", resp.content)
        # No guilt language
        body = resp.content.lower()
        self.assertNotIn(b"you missed", body)
        self.assertNotIn(b"you're behind", body)
        self.assertNotIn(b"haven't read", body)
        # Banner is data-testid-tagged
        self.assertIn(b'data-testid="journey-welcome-back"', resp.content)

    def test_banner_does_not_render_on_first_visit(self):
        # first visit: last_visited_at None — no welcome-back
        self.uj.last_visited_at = None
        self.uj.save(update_fields=["last_visited_at"])
        resp = self.client.get(reverse("journey:today"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'data-testid="journey-welcome-back"', resp.content)

    def test_last_visited_at_updated_on_view(self):
        from django.utils import timezone
        resp = self.client.get(reverse("journey:today"))
        self.assertEqual(resp.status_code, 200)
        self.uj.refresh_from_db()
        delta = (timezone.now() - self.uj.last_visited_at).total_seconds()
        self.assertLess(delta, 5)

    def test_last_engaged_at_NOT_updated_on_view(self):
        """Opening the page must not mask the reading gap."""
        from django.utils import timezone
        from datetime import timedelta
        five_days_ago = timezone.now() - timedelta(days=5)
        self.uj.last_engaged_at = five_days_ago
        self.uj.save(update_fields=["last_engaged_at"])
        self.client.get(reverse("journey:today"))
        self.uj.refresh_from_db()
        self.assertAlmostEqual(self.uj.last_engaged_at.timestamp(), five_days_ago.timestamp(), places=1)


class StuckSurfaceTests(TestCase):
    """The 'I'm stuck' deterministic surface renders authored confusion topics."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_journey_path", "walking_with_god")

    def setUp(self):
        self.user = _make_user("stuck-tester@example.com")
        self.client = Client()
        self.client.force_login(self.user)
        UserJourney.objects.create(
            user=self.user,
            journey_path=JourneyPath.objects.get(slug="walking_with_god"),
            current_arc=JourneyArc.objects.get(slug="creation_to_egypt"),
            current_day_number=1,
        )

    def test_confusion_topics_render(self):
        resp = self.client.get(reverse("journey:today"))
        self.assertEqual(resp.status_code, 200)
        # Day 1 has 4 authored confusion topics; at least one familiar string must appear.
        self.assertIn(b"image of God", resp.content)
        self.assertIn(b"science", resp.content)


class AnnotationReuseTests(TestCase):
    """Annotation endpoints create rows in the existing four annotation models."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_journey_path", "walking_with_god")

    def setUp(self):
        self.user = _make_user("anno-tester@example.com")
        self.client = Client()
        self.client.force_login(self.user)
        UserJourney.objects.create(
            user=self.user,
            journey_path=JourneyPath.objects.get(slug="walking_with_god"),
            current_arc=JourneyArc.objects.get(slug="creation_to_egypt"),
            current_day_number=1,
        )

    def _post_json(self, url_name, body):
        return self.client.post(
            reverse(url_name),
            data=json.dumps(body),
            content_type="application/json",
        )

    def test_highlight_creates_bible_highlight(self):
        resp = self._post_json("journey:annotation_highlight", {
            "reference": "Leviticus 1:5",
            "text": "He shall kill the bull before Yahweh...",
            "color": "yellow",
        })
        self.assertEqual(resp.status_code, 200)
        h = BibleHighlight.objects.get(user=self.user)
        self.assertEqual(h.book_name, "Leviticus")
        self.assertEqual(h.book_order, 3)
        self.assertEqual(h.chapter, 1)
        self.assertEqual(h.verse_start, 5)
        self.assertEqual(h.color, "yellow")
        self.assertEqual(h.translation, "WEB")

    def test_bookmark_creates_bible_bookmark(self):
        resp = self._post_json("journey:annotation_bookmark", {
            "reference": "Leviticus 1:1",
            "include_verse": True,
            "title": "Where Leviticus begins",
        })
        self.assertEqual(resp.status_code, 200)
        b = BibleBookmark.objects.get(user=self.user)
        self.assertEqual(b.book_name, "Leviticus")
        self.assertEqual(b.verse, 1)

    def test_save_verse_creates_saved_verse(self):
        resp = self._post_json("journey:annotation_save_verse", {
            "reference": "Leviticus 1:9",
            "text": "The priest shall burn all of it on the altar...",
            "is_memory_verse": False,
        })
        self.assertEqual(resp.status_code, 200)
        sv = SavedVerse.objects.get(user=self.user)
        self.assertEqual(sv.chapter, 1)
        self.assertEqual(sv.verse_start, 9)

    def test_note_creates_bible_study_note(self):
        resp = self._post_json("journey:annotation_note", {
            "reference": "Leviticus 1:4",
            "content": "The hand-laying gesture — substitution.",
            "title": "Substitution",
        })
        self.assertEqual(resp.status_code, 200)
        n = BibleStudyNote.objects.get(user=self.user)
        self.assertEqual(n.title, "Substitution")
        self.assertIn("substitution", n.content.lower())

    def test_invalid_reference_returns_400(self):
        resp = self._post_json("journey:annotation_highlight", {
            "reference": "Nonbook 99:1",
            "text": "x",
        })
        self.assertEqual(resp.status_code, 400)


class ReferenceParserTests(TestCase):
    def test_parses_simple_reference(self):
        p = parse_reference("Leviticus 1:5")
        self.assertEqual((p.book_name, p.book_order, p.chapter, p.verse_start, p.verse_end), ("Leviticus", 3, 1, 5, None))

    def test_parses_range(self):
        p = parse_reference("Leviticus 1:5-9")
        self.assertEqual(p.verse_start, 5)
        self.assertEqual(p.verse_end, 9)

    def test_parses_numbered_book(self):
        p = parse_reference("1 Samuel 17:1-11")
        self.assertEqual(p.book_name, "1 Samuel")
        self.assertEqual(p.book_order, 9)

    def test_rejects_unknown_book(self):
        with self.assertRaises(ValueError):
            parse_reference("Nonbook 1:1")
