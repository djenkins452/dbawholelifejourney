"""Slice 3 tests — People, Places, Media (browse, profiles, CRUD, upload, links)."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import (
    Contributor, Media, Memory, Person, Place, Relationship,
)

User = get_user_model()


def _make_user(email="keeper@example.com"):
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class PeopleTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.other = _make_user("other@example.com")
        self.client.force_login(self.user)

    def test_browse_and_search(self):
        Person.objects.create(user=self.user, display_name="Walter Ellison")
        Person.objects.create(user=self.user, display_name="Aunt Carol")
        r = self.client.get(reverse("legacy:people"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Walter Ellison")
        r2 = self.client.get(reverse("legacy:people"), {"q": "carol"})
        self.assertContains(r2, "Aunt Carol")
        self.assertNotContains(r2, "Walter Ellison")

    def test_empty_state(self):
        r = self.client.get(reverse("legacy:people"))
        self.assertContains(r, "will gather here")

    def test_create_person(self):
        r = self.client.post(reverse("legacy:person_new"),
                             {"display_name": "Grandpa", "also_known_as": "", "relationship_label": "your grandfather",
                              "birth_year": "", "death_year": "", "bio": "A quiet man."})
        self.assertEqual(r.status_code, 302)
        p = Person.objects.get(display_name="Grandpa")
        self.assertEqual(p.user, self.user)
        self.assertEqual(p.created_via, Person.CREATED_VIA_MANUAL)

    def test_edit_person(self):
        p = Person.objects.create(user=self.user, display_name="Bob")
        self.client.post(reverse("legacy:person_edit", args=[p.pk]),
                        {"display_name": "Robert", "also_known_as": "", "relationship_label": "",
                         "birth_year": "", "death_year": "", "bio": ""})
        p.refresh_from_db()
        self.assertEqual(p.display_name, "Robert")

    def test_profile_shows_related(self):
        person = Person.objects.create(user=self.user, display_name="Dad")
        place = Place.objects.create(user=self.user, name="The shop")
        contrib = Contributor.objects.create(user=self.user, name="Sarah")
        m = Memory.objects.create(user=self.user, title="Opening day", contributor=contrib)
        m.people.add(person); m.places.add(place)
        other = Person.objects.create(user=self.user, display_name="Grandpa")
        Relationship.objects.create(user=self.user, from_person=person, to_person=other,
                                    relationship_type="son of")
        r = self.client.get(reverse("legacy:person_detail", args=[person.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Opening day")   # related memory
        self.assertContains(r, "The shop")      # related place
        self.assertContains(r, "Grandpa")       # relationship
        self.assertContains(r, "Sarah")         # contributor attribution

    def test_cannot_view_others_person(self):
        p = Person.objects.create(user=self.other, display_name="Secret")
        r = self.client.get(reverse("legacy:person_detail", args=[p.pk]))
        self.assertEqual(r.status_code, 404)

    def test_archive_and_restore(self):
        p = Person.objects.create(user=self.user, display_name="Temp")
        self.client.post(reverse("legacy:person_archive", args=[p.pk]))
        p.refresh_from_db(); self.assertEqual(p.status, "archived")
        self.client.post(reverse("legacy:person_restore", args=[p.pk]))
        p.refresh_from_db(); self.assertEqual(p.status, "active")

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("legacy:people")).status_code, 302)


class PlacesTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def test_browse_search_create(self):
        Place.objects.create(user=self.user, name="Lake house")
        r = self.client.get(reverse("legacy:places"), {"q": "lake"})
        self.assertContains(r, "Lake house")
        self.client.post(reverse("legacy:place_new"),
                        {"name": "Soddy Daisy", "location_text": "TN", "description": ""})
        self.assertTrue(Place.objects.filter(name="Soddy Daisy").exists())

    def test_profile_shows_people_and_timeline(self):
        place = Place.objects.create(user=self.user, name="The cabin")
        person = Person.objects.create(user=self.user, display_name="Mom")
        import datetime
        m = Memory.objects.create(user=self.user, title="Summer of 72",
                                  occurred_on=datetime.date(1972, 7, 1))
        m.places.add(place); m.people.add(person)
        r = self.client.get(reverse("legacy:place_detail", args=[place.pk]))
        self.assertContains(r, "Summer of 72")
        self.assertContains(r, "Mom")
        self.assertContains(r, "Across the years")

    def test_archive_restore(self):
        p = Place.objects.create(user=self.user, name="X")
        self.client.post(reverse("legacy:place_archive", args=[p.pk]))
        p.refresh_from_db(); self.assertEqual(p.status, "archived")
        self.client.post(reverse("legacy:place_restore", args=[p.pk]))
        p.refresh_from_db(); self.assertEqual(p.status, "active")


class MediaTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.other = _make_user("other2@example.com")
        self.client.force_login(self.user)

    def test_library_filter_and_search(self):
        Media.objects.create(user=self.user, media_type=Media.MediaType.PHOTO, caption="wedding photo")
        Media.objects.create(user=self.user, media_type=Media.MediaType.AUDIO, caption="grandpa voice")
        r = self.client.get(reverse("legacy:media"), {"type": "audio"})
        self.assertContains(r, "grandpa voice")
        self.assertNotContains(r, "wedding photo")
        r2 = self.client.get(reverse("legacy:media"), {"q": "wedding"})
        self.assertContains(r2, "wedding photo")

    def test_empty_state(self):
        r = self.client.get(reverse("legacy:media"))
        self.assertContains(r, "Bring your photos")

    def test_upload(self):
        f = SimpleUploadedFile("clip.mp3", b"audiodata", content_type="audio/mpeg")
        r = self.client.post(reverse("legacy:media_upload"), {"file": f})
        self.assertEqual(r.status_code, 302)
        media = Media.objects.get(user=self.user)
        self.assertEqual(media.media_type, Media.MediaType.AUDIO)

    def test_detail_shows_memory_links(self):
        media = Media.objects.create(user=self.user, media_type=Media.MediaType.PHOTO, caption="pic")
        m = Memory.objects.create(user=self.user, title="Linked memory")
        m.media.add(media)
        r = self.client.get(reverse("legacy:media_detail", args=[media.pk]))
        self.assertContains(r, "Linked memory")

    def test_cannot_view_others_media(self):
        md = Media.objects.create(user=self.other, media_type=Media.MediaType.PHOTO)
        self.assertEqual(self.client.get(reverse("legacy:media_detail", args=[md.pk])).status_code, 404)


class EditorLinkingTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def test_save_links_people_and_places(self):
        person = Person.objects.create(user=self.user, display_name="Dad")
        place = Place.objects.create(user=self.user, name="The shop")
        m = Memory.objects.create(user=self.user, title="Day one")
        self.client.post(reverse("legacy:memory_save"), {
            "pk": m.pk, "title": "Day one", "body": "text", "action": "draft",
            "people": [person.pk], "places": [place.pk],
        })
        m.refresh_from_db()
        self.assertIn(person, m.people.all())
        self.assertIn(place, m.places.all())
