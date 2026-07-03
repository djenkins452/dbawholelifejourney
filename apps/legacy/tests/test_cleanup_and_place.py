"""Discovery pipeline Phase 1 (Cleanup) and Phase 3 (Place verification)."""

from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import MemoryDiscovery, Memory, Place
from apps.legacy.services import cleanup as C
from apps.legacy.services import discovery as D
from apps.legacy.services import place_lookup as PL

User = get_user_model()


def _make_user(email="keeper@example.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


# ── Phase 1 — Cleanup ────────────────────────────────────────────────────────
class CleanupServiceTests(TestCase):
    def test_changed_preserves_original_and_lists_kinds(self):
        original = "we ate at maries after teh wedding it was good"
        editor = lambda t: ("We ate at Marie's after the wedding. It was good.",
                            ["Spelling corrected", "Punctuation tidied"])
        r = C.run_cleanup(original, editor=editor)
        self.assertTrue(r["changed"])
        self.assertEqual(r["original"], original)
        self.assertIn("Marie's", r["cleaned"])
        self.assertIn("Spelling corrected", r["changes"])

    def test_safe_when_editor_unavailable(self):
        original = "A short but valid story about my life and times."
        r = C.run_cleanup(original, editor=lambda t: None)
        self.assertFalse(r["changed"])
        self.assertEqual(r["cleaned"], original)

    def test_rejects_large_length_drift(self):
        # A model that "improves" too much is distrusted — voice must be preserved.
        original = "We drove to the lake and sat quietly all afternoon."
        rewrite = original + " " + ("and then many new invented sentences " * 8)
        r = C.run_cleanup(original, editor=lambda t: (rewrite, ["Rewrote"]))
        self.assertFalse(r["changed"])
        self.assertEqual(r["cleaned"], original)

    def test_too_short_is_skipped(self):
        r = C.run_cleanup("Hi", editor=lambda t: ("Hello.", ["x"]))
        self.assertFalse(r["changed"])


# ── Phase 3 — Place verification (heuristics + parsing) ──────────────────────
class PersonalPlaceHeuristicTests(TestCase):
    def test_personal_places_are_recognized(self):
        for name in ["Grandma's House", "The Old Barn", "Dad's Shop",
                     "The Fishing Hole", "Our Cabin", "The Tree House",
                     "my grandmother's kitchen"]:
            self.assertTrue(PL.is_personal_place(name), name)

    def test_public_places_are_not_personal(self):
        for name in ["Marie Callender's", "Lincoln Memorial",
                     "First Baptist Church", "Torrance High School"]:
            self.assertFalse(PL.is_personal_place(name), name)


# ── Phase 3 — Place resolution INLINE from the Discovery OpenAI call ──────────
def _place_stub(personal=False, home=None):
    """place_lookup_fn no longer looks anything up — it only supplies the
    personal-place safety net and the home context handed to the model."""
    return SimpleNamespace(
        is_personal_place=lambda n: personal or PL.is_personal_place(n),
        home_location=lambda user: home,
    )


def _resolved(name="Marie Callender's", **kw):
    """An extractor 'places' entry carrying an inline resolution from OpenAI."""
    d = {"name": name, "confidence": 0.9, "personal": False,
         "official_name": "Marie Callender's", "line1": "540 N Euclid St",
         "city": "Anaheim", "state": "California", "country": "United States",
         "lat": 33.84, "lon": -117.95, "place_confidence": "high",
         "reasoning": "A well-known restaurant near your home."}
    d.update(kw)
    return d


class PlaceResolutionPipelineTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.memory = Memory.objects.create(
            user=self.user, title="After the wedding",
            body="We ate at Marie Callender's after the wedding.")

    def _run(self, place):
        D.run_discovery(self.memory, extractor=lambda t: {"places": [place]},
                        place_lookup_fn=_place_stub())
        return MemoryDiscovery.objects.get(memory=self.memory, kind="place")

    def test_high_confidence_public_place_is_verified(self):
        d = self._run(_resolved(place_confidence="high"))
        self.assertFalse(d.detail["personal"])
        self.assertEqual(len(d.detail["lookup"]), 1)
        self.assertEqual(d.detail["lookup"][0]["city"], "Anaheim")
        self.assertEqual(d.detail["lookup_confidence"], "verified")
        self.assertIn("well-known", d.detail["reasoning"])

    def test_medium_confidence_is_possible_match(self):
        d = self._run(_resolved(place_confidence="medium"))
        self.assertEqual(d.detail["lookup_confidence"], "possible")

    def test_low_confidence_stays_unresolved(self):
        d = self._run(_resolved(place_confidence="low"))
        self.assertEqual(d.detail["lookup"], [])
        self.assertIsNone(d.detail["lookup_confidence"])

    def test_confident_but_no_location_is_unresolved(self):
        d = self._run(_resolved(place_confidence="high", line1=None, city=None, state=None))
        self.assertEqual(d.detail["lookup"], [])

    def test_personal_flag_from_model(self):
        d = self._run({"name": "Marie Callender's", "confidence": 0.9,
                       "personal": True, "place_confidence": None})
        self.assertTrue(d.detail["personal"])
        self.assertEqual(d.detail["lookup"], [])

    def test_personal_heuristic_safety_net(self):
        # Model forgot to flag it, but the name is obviously private.
        self.memory.body = "We sat on the porch at Grandma's house."
        self.memory.save()
        d = self._run({"name": "Grandma's house", "confidence": 0.9,
                       "personal": False, "place_confidence": "high",
                       "line1": "1 Main St", "city": "Nowhere", "state": "TN"})
        self.assertTrue(d.detail["personal"])
        self.assertEqual(d.detail["lookup"], [])

    def test_existing_legacy_place_wins_over_resolution(self):
        Place.objects.create(user=self.user, name="Marie Callender's")
        d = self._run(_resolved())      # model resolved it, but we already have it
        self.assertIsNotNone(d.detail["matched_place_id"])
        self.assertEqual(d.detail["lookup"], [])

    def test_apply_adopts_resolved_place_with_coordinates(self):
        d = self._run(_resolved())
        D.confirm_discoveries(self.memory, accepted_ids=[d.id],
                              resolutions={str(d.id): "lookup:0"})
        p = Place.objects.get(user=self.user, name="Marie Callender's")
        self.assertIn("Anaheim", p.location_text)
        self.assertEqual(str(p.latitude), "33.840000")
        self.assertIn(p, self.memory.places.all())

    def test_apply_default_creates_name_only_place(self):
        d = self._run(_resolved(place_confidence="low"))   # unresolved
        D.confirm_discoveries(self.memory, accepted_ids=[d.id])
        p = Place.objects.get(user=self.user, name="Marie Callender's")
        self.assertEqual(p.location_text, "")
        self.assertIsNone(p.latitude)


class HomeContextTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_home_from_preferences(self):
        self.user.preferences.location_city = "Maryville"
        self.user.preferences.location_country = "United States"
        self.user.preferences.save()
        self.assertEqual(PL.home_location(self.user)["text"], "Maryville")

    def test_home_is_added_to_the_discovery_prompt(self):
        captured = {}

        def fake_create(**kw):
            captured["messages"] = kw["messages"]
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content='{"places":[]}'))])

        fake_client = SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=fake_create)))
        with patch("apps.legacy.services.discovery._client", return_value=fake_client):
            D._extract("We ate at K's.", home="Maryville, Tennessee")
        self.assertIn("Maryville, Tennessee", captured["messages"][1]["content"])

    def test_run_discovery_hands_home_to_the_model(self):
        self.user.preferences.location_city = "Maryville"
        self.user.preferences.save()
        m = Memory.objects.create(user=self.user, title="x",
                                  body="I stopped by Nauti K's after work.")
        seen = {}

        def fake_extract(t, home=None, known_places=None):
            seen["home"] = home
            return {"places": []}

        with patch("apps.legacy.services.discovery.is_available", return_value=True), \
             patch("apps.legacy.services.discovery._extract", side_effect=fake_extract):
            D.run_discovery(m)   # place_lookup_fn defaults to the real home reader
        self.assertEqual(seen["home"], "Maryville")

    def test_known_legacy_places_added_to_prompt(self):
        captured = {}

        def fake_create(**kw):
            captured["messages"] = kw["messages"]
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content='{"places":[]}'))])

        fake_client = SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=fake_create)))
        with patch("apps.legacy.services.discovery._client", return_value=fake_client):
            D._extract("We ate at K's.",
                       known_places="UT Medical Center (Knoxville, TN)")
        self.assertIn("Knoxville", captured["messages"][1]["content"])

    def test_run_discovery_hands_known_places_to_the_model(self):
        Place.objects.create(user=self.user, name="UT Medical Center",
                             location_text="Knoxville, TN")
        m = Memory.objects.create(user=self.user, title="x",
                                  body="We stopped at Nauti K's.")
        seen = {}

        def fake_extract(t, home=None, known_places=None):
            seen["kp"] = known_places
            return {"places": []}

        with patch("apps.legacy.services.discovery.is_available", return_value=True), \
             patch("apps.legacy.services.discovery._extract", side_effect=fake_extract):
            D.run_discovery(m)
        self.assertIn("UT Medical Center", seen["kp"] or "")
        self.assertIn("Knoxville", seen["kp"] or "")


class DiscoverViewCleanupTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def test_discover_applies_cleanup_and_returns_cleaned_body(self):
        cleaned = {"changed": True, "cleaned": "We ate at Marie's. It was good.",
                   "original": "we ate at maries it was good", "changes": ["Spelling corrected"]}
        with patch("apps.legacy.services.cleanup.run_cleanup", return_value=cleaned), \
             patch("apps.legacy.services.discovery.run_discovery", return_value=("nothing", [])):
            r = self.client.post(reverse("legacy:memory_discover"), {
                "title": "Dinner", "body": "we ate at maries it was good",
            }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["cleaned_body"], cleaned["cleaned"])
        m = Memory.objects.get(user=self.user)
        self.assertEqual(m.body, cleaned["cleaned"])
        self.assertEqual(m.cleanup_original_body, cleaned["original"])

    def test_cleanup_undo_restores_original(self):
        m = Memory.objects.create(
            user=self.user, title="x", body="Cleaned version.",
            cleanup_original_body="original messy version")
        r = self.client.post(reverse("legacy:memory_cleanup_undo", args=[m.pk]),
                             HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertTrue(r.json()["ok"])
        m.refresh_from_db()
        self.assertEqual(m.body, "original messy version")
        self.assertEqual(m.cleanup_original_body, "")
