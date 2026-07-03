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


class PlaceLookupParsingTests(TestCase):
    def test_parses_name_and_location_only(self):
        fake_json = (
            b'[{"lat":"33.84","lon":"-117.95",'
            b'"display_name":"Marie Callender\'s, 540, North Euclid Street, Anaheim, CA, USA",'
            b'"namedetails":{"name":"Marie Callender\'s"},'
            b'"address":{"house_number":"540","road":"North Euclid Street",'
            b'"city":"Anaheim","state":"California","country":"United States"}}]')

        class FakeResp:
            def read(self_inner): return fake_json
            def __enter__(self_inner): return self_inner
            def __exit__(self_inner, *a): return False

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            out = PL.lookup_place("Marie Callender's")
        self.assertEqual(len(out), 1)
        c = out[0]
        self.assertEqual(c["name"], "Marie Callender's")
        self.assertEqual(c["city"], "Anaheim")
        self.assertEqual(c["state"], "California")
        self.assertEqual(c["lat"], "33.84")
        self.assertIn("Anaheim", c["display"])

    def test_network_failure_returns_empty(self):
        with patch("urllib.request.urlopen", side_effect=OSError("no network")):
            self.assertEqual(PL.lookup_place("Somewhere"), [])


# ── Phase 3 — Place verification woven into Discovery + Apply ─────────────────
_CANDIDATE = {
    "name": "Marie Callender's", "line1": "540 N Euclid St", "city": "Anaheim",
    "state": "California", "country": "United States",
    "lat": "33.84", "lon": "-117.95", "display": "540 N Euclid St, Anaheim, California",
}


def _place_stub(personal=False, candidates=None):
    return SimpleNamespace(
        is_personal_place=lambda n: personal,
        lookup_place=lambda n, **k: list(candidates or []),
        explicit_location=lambda text, exclude=None: None,
        home_location=lambda user: None,
    )


class PlaceVerificationPipelineTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.memory = Memory.objects.create(
            user=self.user, title="After the wedding",
            body="We ate at Marie Callender's after the wedding.")

    def _run(self, personal=False, candidates=None):
        D.run_discovery(
            self.memory,
            extractor=lambda t: {"places": [{"name": "Marie Callender's", "confidence": 0.9}]},
            place_lookup_fn=_place_stub(personal, candidates))
        return MemoryDiscovery.objects.get(memory=self.memory, kind="place")

    def test_public_place_gets_lookup_candidates(self):
        d = self._run(candidates=[_CANDIDATE])
        self.assertFalse(d.detail["personal"])
        self.assertEqual(len(d.detail["lookup"]), 1)
        self.assertEqual(d.detail["lookup"][0]["city"], "Anaheim")

    def test_personal_place_is_not_looked_up(self):
        self.memory.body = "We sat on the porch at Grandma's house."
        self.memory.save()
        D.run_discovery(
            self.memory,
            extractor=lambda t: {"places": [{"name": "Grandma's house", "confidence": 0.9}]},
            place_lookup_fn=_place_stub(personal=True, candidates=[_CANDIDATE]))
        d = MemoryDiscovery.objects.get(memory=self.memory, kind="place")
        self.assertTrue(d.detail["personal"])
        self.assertEqual(d.detail["lookup"], [])

    def test_personal_place_not_falsely_matched_to_generic_word(self):
        # "Grandma's house" must NOT match an existing "The lake house" on "house".
        Place.objects.create(user=self.user, name="The lake house")
        self.memory.body = "We spent summers at Grandma's house by the water."
        self.memory.save()
        D.run_discovery(
            self.memory,
            extractor=lambda t: {"places": [{"name": "Grandma's house", "confidence": 0.9}]},
            place_lookup_fn=_place_stub(personal=True))
        d = MemoryDiscovery.objects.get(memory=self.memory, kind="place")
        self.assertTrue(d.detail["personal"])
        self.assertEqual(d.detail["existing"], [])
        self.assertIsNone(d.detail["matched_place_id"])

    def test_existing_legacy_place_skips_lookup(self):
        Place.objects.create(user=self.user, name="Marie Callender's")
        called = {"n": 0}

        def counting_lookup(n, **k):
            called["n"] += 1
            return [_CANDIDATE]

        D.run_discovery(
            self.memory,
            extractor=lambda t: {"places": [{"name": "Marie Callender's", "confidence": 0.9}]},
            place_lookup_fn=SimpleNamespace(
                is_personal_place=lambda n: False, lookup_place=counting_lookup,
                explicit_location=lambda text, exclude=None: None,
                home_location=lambda user: None))
        d = MemoryDiscovery.objects.get(memory=self.memory, kind="place")
        self.assertIsNotNone(d.detail["matched_place_id"])
        self.assertEqual(called["n"], 0)   # never looked up — we already have it

    def test_apply_adopts_verified_place_with_coordinates(self):
        d = self._run(candidates=[_CANDIDATE])
        D.confirm_discoveries(self.memory, accepted_ids=[d.id],
                              resolutions={str(d.id): "lookup:0"})
        p = Place.objects.get(user=self.user, name="Marie Callender's")
        self.assertIn("Anaheim", p.location_text)
        self.assertEqual(str(p.latitude), "33.840000")
        self.assertIn(p, self.memory.places.all())

    def test_apply_uses_existing_place_no_duplicate(self):
        existing = Place.objects.create(user=self.user, name="Marie Callender's")
        d = self._run(candidates=[_CANDIDATE])
        # detail.matched_place_id already points at existing (exact name match)
        D.confirm_discoveries(self.memory, accepted_ids=[d.id],
                              resolutions={str(d.id): "existing:%d" % existing.pk})
        self.assertEqual(Place.objects.filter(user=self.user, name="Marie Callender's").count(), 1)
        self.assertIn(existing, self.memory.places.all())

    def test_apply_default_creates_personal_place_name_only(self):
        d = self._run(personal=True)
        D.confirm_discoveries(self.memory, accepted_ids=[d.id])   # no resolution
        p = Place.objects.get(user=self.user, name="Marie Callender's")
        self.assertEqual(p.location_text, "")
        self.assertIsNone(p.latitude)


class PlaceContextResolutionTests(TestCase):
    """Priority order for the search area: story-explicit → other place in the
    story → home. Legacy uses context so the user rarely types a city."""

    def setUp(self):
        self.user = _make_user()

    class _Recording:
        """Delegates the pure helpers to the real module, records lookup calls."""
        def __init__(self, results=None, home=None):
            self.calls = []
            self.results = results or {}
            self._home = home

        def is_personal_place(self, n):
            return PL.is_personal_place(n)

        def explicit_location(self, text, exclude=None):
            return PL.explicit_location(text, exclude)

        def home_location(self, user):
            return self._home

        def lookup_place(self, name, near=None):
            self.calls.append((name, near))
            return list(self.results.get(name, []))

    def _mem(self, body):
        return Memory.objects.create(user=self.user, title="Trip", body=body)

    def _near_for(self, rec, name):
        return dict((n, near) for n, near in rec.calls).get(name)

    def test_explicit_story_location_wins(self):
        m = self._mem("We were visiting Riverside, California and stopped at K's.")
        rec = self._Recording(home={"text": "Maryville, Tennessee", "source": "home"})
        D.run_discovery(m, extractor=lambda t: {"places": [{"name": "K's", "confidence": 0.9}]},
                        place_lookup_fn=rec)
        self.assertEqual(self._near_for(rec, "K's"), "Riverside, California")

    def test_home_used_when_no_story_location(self):
        m = self._mem("I stopped by Nauti K's after work.")
        rec = self._Recording(home={"text": "Maryville, Tennessee", "source": "home"})
        D.run_discovery(m, extractor=lambda t: {"places": [{"name": "Nauti K's", "confidence": 0.9}]},
                        place_lookup_fn=rec)
        self.assertEqual(self._near_for(rec, "Nauti K's"), "Maryville, Tennessee")

    def test_prior_looked_up_place_seeds_context(self):
        m = self._mem("We left UT Medical Center and stopped at Nauti K's.")
        rec = self._Recording(results={
            "UT Medical Center": [{"name": "UT Medical Center", "city": "Knoxville",
                                   "state": "Tennessee", "display": "Knoxville, TN"}]})
        D.run_discovery(m, extractor=lambda t: {"places": [
            {"name": "UT Medical Center", "confidence": 0.9},
            {"name": "Nauti K's", "confidence": 0.9}]}, place_lookup_fn=rec)
        # Nauti K's inherits Knoxville from the place resolved just before it.
        self.assertEqual(self._near_for(rec, "Nauti K's"), "Knoxville, Tennessee")

    def test_existing_legacy_place_seeds_context(self):
        Place.objects.create(user=self.user, name="UT Medical Center",
                             location_text="Knoxville, Tennessee")
        m = self._mem("We left UT Medical Center and stopped at Nauti K's.")
        rec = self._Recording()
        D.run_discovery(m, extractor=lambda t: {"places": [
            {"name": "UT Medical Center", "confidence": 0.9},
            {"name": "Nauti K's", "confidence": 0.9}]}, place_lookup_fn=rec)
        # UT Medical Center already known → its location contexts Nauti K's.
        self.assertEqual(self._near_for(rec, "Nauti K's"), "Knoxville, Tennessee")
        # The known place itself is never looked up.
        self.assertNotIn("UT Medical Center", [c[0] for c in rec.calls])

    def test_confidence_and_search_area_recorded(self):
        m = self._mem("We ate at Marie Callender's.")
        rec = self._Recording(
            results={"Marie Callender's": [_CANDIDATE]},
            home={"text": "Anaheim, California", "source": "home"})
        D.run_discovery(m, extractor=lambda t: {"places": [{"name": "Marie Callender's", "confidence": 0.9}]},
                        place_lookup_fn=rec)
        d = MemoryDiscovery.objects.get(memory=m, kind="place")
        self.assertEqual(d.detail["lookup_confidence"], "verified")
        self.assertEqual(d.detail["search_area"]["source"], "home")


class PlaceHelperTests(TestCase):
    def test_explicit_location_city_state(self):
        self.assertEqual(
            PL.explicit_location("We were visiting Riverside, California today.")["text"],
            "Riverside, California")
        self.assertEqual(
            PL.explicit_location("Grew up in Knoxville, TN.")["text"], "Knoxville, TN")

    def test_explicit_location_bare_city(self):
        self.assertEqual(PL.explicit_location("We stopped in Gatlinburg.")["text"], "Gatlinburg")

    def test_explicit_location_ignores_months_and_people(self):
        self.assertIsNone(PL.explicit_location("We married in June."))
        self.assertIsNone(PL.explicit_location("We drove to Marvin.", exclude={"Marvin"}))

    def test_home_location_from_preferences(self):
        self.user = _make_user("h@example.com")
        self.user.preferences.location_city = "Maryville"
        self.user.preferences.location_country = "United States"
        self.user.preferences.save()
        self.assertEqual(PL.home_location(self.user)["text"], "Maryville")

    def test_lookup_appends_near_to_query(self):
        seen = {}

        class FakeResp:
            def read(self_inner): return b"[]"
            def __enter__(self_inner): return self_inner
            def __exit__(self_inner, *a): return False

        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url
            return FakeResp()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            PL.lookup_place("Nauti K's", near="Knoxville, Tennessee")
        self.assertIn("Knoxville", seen["url"])


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
