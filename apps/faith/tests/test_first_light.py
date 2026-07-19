"""Tests for the First Light — Formation Faith experience.

Covers the deterministic presenters (season, Today, Mirror), the honest-language
guarantee of the Mirror, and the flag dispatch (First Light vs classic).
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from apps.faith.first_light.season import season_note, _easter
from apps.faith.first_light.today import build_today
from apps.faith.first_light import mirror as mirror_mod
from apps.faith.models import FaithMilestone, PrayerRequest, SavedVerse

User = get_user_model()


def _make_user(email="fl@example.com", first_light=True):
    user = User.objects.create_user(email=email, password="x-passphrase-123")
    prefs = user.preferences
    prefs.faith_enabled = True
    ff = dict(prefs.faith_features or {})
    ff["first_light"] = first_light
    prefs.faith_features = ff
    prefs.save()
    return user


class SeasonTests(TestCase):
    def test_easter_known_years(self):
        self.assertEqual(_easter(2025), datetime.date(2025, 4, 20))
        self.assertEqual(_easter(2026), datetime.date(2026, 4, 5))

    def test_lent_and_holy_week(self):
        # 2025 Easter = Apr 20; Ash Wednesday = Mar 5; Palm Sunday = Apr 13.
        self.assertTrue(season_note(datetime.date(2025, 3, 10)).startswith("Lent"))
        self.assertEqual(season_note(datetime.date(2025, 4, 15)), "Holy Week")
        self.assertEqual(season_note(datetime.date(2025, 4, 20)), "Easter")

    def test_advent_and_ordinary(self):
        self.assertEqual(season_note(datetime.date(2025, 12, 10)), "Advent")
        self.assertEqual(season_note(datetime.date(2025, 12, 27)), "Christmastide")
        # A plain summer day is Ordinary Time -> no note.
        self.assertIsNone(season_note(datetime.date(2025, 7, 15)))


class BuildTodayTests(TestCase):
    def test_shape_for_bare_user(self):
        user = _make_user()
        t = build_today(user)
        for key in ("greeting", "name", "weekday", "still", "continue",
                    "journey_map", "companion", "invitation", "has_started"):
            self.assertIn(key, t)
        self.assertIn(t["greeting"], ("Good morning", "Good afternoon", "Good evening"))
        self.assertIn("text", t["still"])
        self.assertIn("ref", t["still"])

    def test_companion_silent_without_grounding(self):
        # No journey, no recent prayers -> the companion stays silent (presence only).
        user = _make_user()
        t = build_today(user)
        self.assertIsNone(t["companion"])
        self.assertFalse(t["has_started"])


class MirrorTests(TestCase):
    def test_empty_walk(self):
        user = _make_user()
        m = mirror_mod.compute_mirror(user)
        self.assertFalse(m["has_content"])
        self.assertEqual(m["journeys"], [])
        self.assertEqual(m["answered_prayers"]["count"], 0)

    def test_reflects_real_truth(self):
        user = _make_user()
        p = PrayerRequest.objects.create(user=user, title="Peace about the move",
                                         person_or_situation="the move")
        p.mark_answered("A door opened we didn't expect.")
        SavedVerse.objects.create(user=user, reference="Philippians 4:6-7",
                                  text="Do not be anxious about anything.", translation="WEB",
                                  book_name="Philippians", book_order=50, chapter=4,
                                  verse_start=6, verse_end=7)
        FaithMilestone.objects.create(user=user, title="Baptized",
                                      milestone_type="other", date=datetime.date(2024, 6, 1))
        m = mirror_mod.compute_mirror(user)
        self.assertTrue(m["has_content"])
        self.assertEqual(m["answered_prayers"]["count"], 1)
        self.assertEqual(len(m["verses"]), 1)
        self.assertEqual(len(m["milestones"]), 1)
        self.assertIsNotNone(m["began"])

    def test_cache_reader_is_request_path_safe(self):
        # get_cached_mirror never computes: None until the cache is warmed.
        user = _make_user()
        cache.delete(mirror_mod.cache_key(user.id))
        self.assertIsNone(mirror_mod.get_cached_mirror(user))
        mirror_mod.compute_and_cache(user)
        self.assertIsNotNone(mirror_mod.get_cached_mirror(user))


class MirrorTemplateHonestyTests(TestCase):
    """The Mirror must never claim what God did — the person draws that conclusion."""

    FORBIDDEN = ["God changed you", "God transformed", "God has changed",
                 "God made you", "God grew you"]

    def _onboard(self, user):
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user, terms_version=settings.WLJ_SETTINGS["TERMS_VERSION"]
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def test_no_sovereignty_claims_in_rendered_mirror(self):
        user = _make_user(email="fl-mirror@example.com")
        self._onboard(user)
        PrayerRequest.objects.create(user=user, title="A", person_or_situation="a").mark_answered("done")
        SavedVerse.objects.create(user=user, reference="John 3:16", text="For God so loved",
                                  translation="WEB", book_name="John", book_order=43,
                                  chapter=3, verse_start=16)
        mirror_mod.compute_and_cache(user)
        c = Client()
        c.force_login(user)
        html = c.get("/faith/mirror/").content.decode()
        self.assertIn("record of grace", html)
        for phrase in self.FORBIDDEN:
            self.assertNotIn(phrase, html, f"Mirror must not claim: {phrase!r}")


class DispatchTests(TestCase):
    def _onboard(self, user):
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user, terms_version=settings.WLJ_SETTINGS["TERMS_VERSION"]
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def test_first_light_on_serves_today(self):
        user = _make_user(email="fl-on@example.com", first_light=True)
        self._onboard(user)
        c = Client()
        c.force_login(user)
        html = c.get("/faith/").content.decode()
        self.assertIn("fl-today", html)
        self.assertIn("fl-threshold", html)

    def test_first_light_off_serves_classic(self):
        user = _make_user(email="fl-off@example.com", first_light=False)
        self._onboard(user)
        c = Client()
        c.force_login(user)
        html = c.get("/faith/").content.decode()
        self.assertNotIn("fl-today", html)
