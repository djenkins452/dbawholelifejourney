"""Phase 2 tests — Story Discovery Engine (OpenAI call is always mocked)."""

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import MemoryDiscovery, Memory, Person, Place
from apps.legacy.services import discovery as D

User = get_user_model()

FAKE = {
    "people": [
        {"name": "Uncle Joe", "relationship": "uncle", "confidence": 0.9},
        {"name": "Marvin", "relationship": "father", "confidence": 0.85},
    ],
    "places": [{"name": "Soddy Daisy", "confidence": 0.7}],
    "human_time": [{"text": "Summer 1969", "confidence": 0.6}],
    "calendar_time": [{"text": "1969", "year": 1969, "month": None, "precision": "year", "confidence": 0.5}],
    "life_stage": [{"text": "Childhood", "confidence": 0.8}],
    "relative_time": [{"text": "Before high school", "confidence": 0.4}],
    "events": [{"text": "Fishing", "confidence": 0.9}],
    "quotes": [{"text": "Quit swinging from the ass.", "confidence": 0.95}],
    "artifacts": [{"text": "fishing pole", "confidence": 0.6}],
    "media_refs": [],
    "themes": [{"text": "Family", "confidence": 0.7}, {"text": "Adventure", "confidence": 0.6}],
    "values": [{"text": "Hard work", "confidence": 0.5}],
    "traditions": [{"text": "Summer fishing trips", "confidence": 0.5}],
    "emotions": [{"text": "Joy", "confidence": 0.6}],
}


def _make_user(email="keeper@example.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _memory(user):
    return Memory.objects.create(
        user=user, title="Fishing with Uncle Joe",
        body="The summer of 1969 Uncle Joe took me fishing at Soddy Daisy before high school.",
    )


class RunDiscoveryTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.memory = _memory(self.user)

    def test_creates_proposals_across_kinds(self):
        status, props = D.run_discovery(self.memory, extractor=lambda t: FAKE)
        self.assertEqual(status, "ok")
        qs = MemoryDiscovery.objects.filter(memory=self.memory)
        self.assertEqual(qs.filter(kind="person").count(), 2)
        # Relationship is folded into the person (no separate redundant rows).
        self.assertEqual(qs.filter(kind="relationship").count(), 0)
        self.assertEqual(qs.get(kind="person", label="Marvin").detail.get("relationship"), "father")
        self.assertEqual(qs.filter(kind="place").count(), 1)
        self.assertTrue(qs.filter(kind="quote", label="Quit swinging from the ass.").exists())
        self.assertEqual(qs.filter(kind="theme").count(), 2)
        # All start as proposals — nothing canonical.
        self.assertTrue(all(d.status == "proposed" for d in qs))

    def test_confidence_mapping(self):
        D.run_discovery(self.memory, extractor=lambda t: FAKE)
        quote = MemoryDiscovery.objects.get(memory=self.memory, kind="quote")
        self.assertEqual(quote.confidence, "high")   # 0.95
        rel_time = MemoryDiscovery.objects.get(memory=self.memory, kind="relative_time")
        self.assertEqual(rel_time.confidence, "low")  # 0.4

    def test_matches_existing_person(self):
        Person.objects.create(user=self.user, display_name="Uncle Joe")
        D.run_discovery(self.memory, extractor=lambda t: FAKE)
        joe = MemoryDiscovery.objects.get(memory=self.memory, kind="person", label="Uncle Joe")
        self.assertFalse(joe.detail["is_new"])
        self.assertIsNotNone(joe.detail["matched_person_id"])

    def test_possible_duplicate_detection(self):
        Person.objects.create(user=self.user, display_name="Marvin Jenkins")
        D.run_discovery(self.memory, extractor=lambda t: FAKE)
        marvin = MemoryDiscovery.objects.get(memory=self.memory, kind="person", label="Marvin")
        self.assertFalse(marvin.detail["is_new"])
        self.assertIsNone(marvin.detail["matched_person_id"])   # not an exact match
        self.assertTrue(marvin.detail["candidates"])            # but a possible duplicate
        self.assertEqual(marvin.detail["candidates"][0]["name"], "Marvin Jenkins")

    def test_existing_person_carries_stats(self):
        joe = Person.objects.create(user=self.user, display_name="Uncle Joe")
        Memory.objects.create(user=self.user, title="another").people.add(joe)
        D.run_discovery(self.memory, extractor=lambda t: FAKE)
        d = MemoryDiscovery.objects.get(memory=self.memory, kind="person", label="Uncle Joe")
        self.assertIsNotNone(d.detail["matched"])
        self.assertGreaterEqual(d.detail["matched"]["stories"], 1)

    def test_summary_text(self):
        _, _ = D.run_discovery(self.memory, extractor=lambda t: FAKE)
        text = D.summary_text(D.grouped_proposals(self.memory))
        self.assertIn("2 people", text)
        self.assertIn("1 place", text)
        self.assertIn(" and ", text)

    def test_unavailable_when_no_data(self):
        status, props = D.run_discovery(self.memory, extractor=lambda t: None)
        self.assertEqual(status, "unavailable")
        self.assertEqual(MemoryDiscovery.objects.filter(memory=self.memory).count(), 0)

    def test_empty_when_too_short(self):
        m = Memory.objects.create(user=self.user, title="hi", body="")
        status, props = D.run_discovery(m, extractor=lambda t: FAKE)
        self.assertEqual(status, "empty")

    def test_rerun_replaces_proposals_not_accepted(self):
        D.run_discovery(self.memory, extractor=lambda t: FAKE)
        first = MemoryDiscovery.objects.filter(memory=self.memory).count()
        D.run_discovery(self.memory, extractor=lambda t: FAKE)   # re-run
        self.assertEqual(MemoryDiscovery.objects.filter(memory=self.memory).count(), first)


class ConfirmTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.memory = _memory(self.user)
        D.run_discovery(self.memory, extractor=lambda t: FAKE)

    def test_accept_all_promotes_people_and_places(self):
        n = D.confirm_discoveries(self.memory, accept_all=True)
        self.assertGreater(n, 0)
        # Person/Place graph nodes created + linked.
        marvin = Person.objects.get(user=self.user, display_name="Marvin")
        self.assertEqual(marvin.relationship_label, "father")
        self.assertIn(marvin, self.memory.people.all())
        soddy = Place.objects.get(user=self.user, name="Soddy Daisy")
        self.assertIn(soddy, self.memory.places.all())
        # No proposals remain.
        self.assertEqual(MemoryDiscovery.objects.filter(memory=self.memory, status="proposed").count(), 0)

    def test_selective_accept_rejects_the_rest(self):
        joe = MemoryDiscovery.objects.get(memory=self.memory, kind="person", label="Uncle Joe")
        D.confirm_discoveries(self.memory, accepted_ids=[joe.id])
        joe.refresh_from_db()
        self.assertEqual(joe.status, "accepted")
        self.assertTrue(Person.objects.filter(user=self.user, display_name="Uncle Joe").exists())
        # Everything else rejected.
        self.assertFalse(MemoryDiscovery.objects.filter(memory=self.memory, status="proposed").exists())
        self.assertTrue(MemoryDiscovery.objects.filter(memory=self.memory, status="rejected").exists())
        self.assertFalse(Place.objects.filter(user=self.user, name="Soddy Daisy").exists())

    def test_duplicate_resolution_links_chosen_person(self):
        MemoryDiscovery.objects.filter(memory=self.memory).delete()
        existing = Person.objects.create(user=self.user, display_name="Marvin Jenkins")
        D.run_discovery(self.memory, extractor=lambda t: FAKE)
        marvin_d = MemoryDiscovery.objects.get(memory=self.memory, kind="person", label="Marvin")
        # User resolves the possible-match to the existing person.
        D.confirm_discoveries(self.memory, accepted_ids=[marvin_d.id],
                              resolutions={str(marvin_d.id): str(existing.id)})
        # Linked the existing person; did NOT create a second "Marvin".
        self.assertIn(existing, self.memory.people.all())
        self.assertFalse(Person.objects.filter(user=self.user, display_name="Marvin").exists())

    def test_accept_links_existing_person_no_duplicate(self):
        MemoryDiscovery.objects.filter(memory=self.memory).delete()
        Person.objects.create(user=self.user, display_name="Uncle Joe")
        D.run_discovery(self.memory, extractor=lambda t: FAKE)
        joe_d = MemoryDiscovery.objects.get(memory=self.memory, kind="person", label="Uncle Joe")
        D.confirm_discoveries(self.memory, accepted_ids=[joe_d.id])
        self.assertEqual(Person.objects.filter(user=self.user, display_name="Uncle Joe").count(), 1)
        self.assertIn("Uncle Joe", [p.display_name for p in self.memory.people.all()])


class DiscoveryViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.other = _make_user("other@example.com")
        self.client.force_login(self.user)

    def test_discover_endpoint_returns_panel(self):
        with patch.object(D, "is_available", return_value=True), \
             patch.object(D, "_extract", return_value=FAKE):
            r = self.client.post(reverse("legacy:memory_discover"), {
                "pk": "", "title": "Fishing", "body": "Uncle Joe took me fishing at Soddy Daisy in 1969.",
            }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "ok")
        self.assertIn("Uncle Joe", data["html"])
        self.assertTrue(Memory.objects.filter(pk=data["pk"], user=self.user).exists())

    def test_confirm_endpoint_promotes(self):
        m = _memory(self.user)
        D.run_discovery(m, extractor=lambda t: FAKE)
        r = self.client.post(reverse("legacy:discovery_confirm", args=[m.pk]), {"accept_all": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(m.people.exists())
        self.assertTrue(m.places.exists())

    def test_discover_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.post(reverse("legacy:memory_discover"), {}).status_code, 302)

    def test_cannot_confirm_others_memory(self):
        m = _memory(self.other)
        r = self.client.post(reverse("legacy:discovery_confirm", args=[m.pk]), {"accept_all": "1"})
        self.assertEqual(r.status_code, 404)
