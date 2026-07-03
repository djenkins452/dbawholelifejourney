"""Persistent Story Connections panel (after Apply) + Place profile map link."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import (
    LifeMilestone, Media, Memory, MemoryDiscovery, Person, Place, Relationship,
)
from apps.legacy.views import build_story_connections

User = get_user_model()


def _make_user(email="keeper@example.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _keys(sections):
    return [s["key"] for s in sections]


class BuildConnectionsTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.memory = Memory.objects.create(user=self.user, title="Wedding day")

    def test_reflects_attached_relations_with_counts(self):
        p1 = Person.objects.create(user=self.user, display_name="Heather", relationship_label="wife")
        p2 = Person.objects.create(user=self.user, display_name="Tom")
        place = Place.objects.create(user=self.user, name="The chapel")
        ms = LifeMilestone.objects.create(user=self.user, title="Married", kind="marriage", year=1997)
        media = Media.objects.create(user=self.user, media_type=Media.MediaType.PHOTO)
        self.memory.people.add(p1, p2)
        self.memory.places.add(place)
        self.memory.milestones.add(ms)
        self.memory.media.add(media)

        sections = build_story_connections(self.memory)
        by_key = {s["key"]: s for s in sections}
        self.assertEqual(by_key["people"]["count"], 2)
        self.assertEqual(by_key["places"]["count"], 1)
        self.assertEqual(by_key["milestones"]["count"], 1)
        self.assertEqual(by_key["media"]["count"], 1)
        # People items carry a profile URL.
        self.assertEqual(by_key["people"]["items"][0]["url"],
                         reverse("legacy:person_detail", args=[p1.pk]))
        self.assertEqual(by_key["places"]["items"][0]["url"],
                         reverse("legacy:place_detail", args=[place.pk]))

    def test_empty_relationships_section_is_omitted(self):
        p = Person.objects.create(user=self.user, display_name="Corey")
        self.memory.people.add(p)   # a mention, NOT a relationship
        self.assertNotIn("relationships", _keys(build_story_connections(self.memory)))

    def test_real_relationship_appears(self):
        a = Person.objects.create(user=self.user, display_name="Corey")
        b = Person.objects.create(user=self.user, display_name="Elizabeth")
        self.memory.people.add(a, b)
        Relationship.objects.create(user=self.user, from_person=a, to_person=b,
                                    relationship_type="coworker")
        self.assertIn("relationships", _keys(build_story_connections(self.memory)))

    def test_accepted_enriched_discoveries_become_chips(self):
        MemoryDiscovery.objects.create(memory=self.memory, kind="theme", label="Family",
                                       status=MemoryDiscovery.Status.ACCEPTED)
        MemoryDiscovery.objects.create(memory=self.memory, kind="human_time",
                                       label="Summer 1997", status=MemoryDiscovery.Status.ACCEPTED)
        # A still-proposed one must NOT show as a connection.
        MemoryDiscovery.objects.create(memory=self.memory, kind="quote", label="unapproved",
                                       status=MemoryDiscovery.Status.PROPOSED)
        sections = build_story_connections(self.memory)
        by_key = {s["key"]: s for s in sections}
        self.assertIn("Family", by_key["themes"]["chips"])
        self.assertIn("Summer 1997", by_key["time"]["chips"])
        self.assertNotIn("quotes", by_key)

    def test_nothing_connected_returns_empty(self):
        self.assertEqual(build_story_connections(self.memory), [])


class EditorConnectionsViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def test_connections_render_and_persist_on_reload(self):
        m = Memory.objects.create(user=self.user, title="Trip")
        p = Person.objects.create(user=self.user, display_name="Dad")
        m.people.add(p)
        r = self.client.get(reverse("legacy:editor", args=[m.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "storyConnections")
        self.assertContains(r, "Dad")
        self.assertContains(r, "Now part of this story")

    def test_attached_media_shows_on_reload(self):
        m = Memory.objects.create(user=self.user, title="Trip")
        media = Media.objects.create(user=self.user, media_type=Media.MediaType.PHOTO)
        m.media.add(media)
        r = self.client.get(reverse("legacy:editor", args=[m.pk]))
        # Media appears both in the drag-drop card grid and the connections panel.
        self.assertContains(r, "editorMediaGrid")
        self.assertContains(r, reverse("legacy:media_detail", args=[media.pk]))


class PlaceMapLinkTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def test_map_link_from_coordinates(self):
        place = Place.objects.create(user=self.user, name="Marie Callender's",
                                     latitude="33.84", longitude="-117.95")
        r = self.client.get(reverse("legacy:place_detail", args=[place.pk]))
        self.assertContains(r, "https://www.google.com/maps?q=33.84")
        self.assertContains(r, "Open in Google Maps")

    def test_map_link_from_address_when_no_coords(self):
        place = Place.objects.create(user=self.user, name="The chapel",
                                     location_text="Tuscaloosa, Alabama")
        r = self.client.get(reverse("legacy:place_detail", args=[place.pk]))
        self.assertContains(r, "google.com/maps/search")

    def test_no_map_link_without_location(self):
        place = Place.objects.create(user=self.user, name="Grandma's house")
        r = self.client.get(reverse("legacy:place_detail", args=[place.pk]))
        self.assertNotContains(r, "Open in Google Maps")
