"""Slice 3 tests — People, Places, Media (browse, profiles, CRUD, upload, links)."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import (
    Contributor, LifeMilestone, Media, Memory, Person, Place, Relationship,
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

    def test_upload_skips_narrative_text(self):
        # A memoir .txt should be guided to Import, never filed as media.
        f = SimpleUploadedFile("memoir.txt", b"Chapter 1", content_type="text/plain")
        self.client.post(reverse("legacy:media_upload"), {"file": f})
        self.assertEqual(Media.objects.filter(user=self.user).count(), 0)

    def test_detail_shows_memory_links(self):
        media = Media.objects.create(user=self.user, media_type=Media.MediaType.PHOTO, caption="pic")
        m = Memory.objects.create(user=self.user, title="Linked memory")
        m.media.add(media)
        r = self.client.get(reverse("legacy:media_detail", args=[media.pk]))
        self.assertContains(r, "Linked memory")

    def test_cannot_view_others_media(self):
        md = Media.objects.create(user=self.other, media_type=Media.MediaType.PHOTO)
        self.assertEqual(self.client.get(reverse("legacy:media_detail", args=[md.pk])).status_code, 404)

    def test_two_stage_delete(self):
        md = Media.objects.create(user=self.user, media_type=Media.MediaType.PHOTO)
        # Delete forever is refused until it's set aside.
        self.client.post(reverse("legacy:media_delete_forever", args=[md.pk]))
        self.assertTrue(Media.all_objects.filter(pk=md.pk).exists())
        # Set aside → drops out of the active library.
        self.client.post(reverse("legacy:media_archive", args=[md.pk]))
        md.refresh_from_db(); self.assertEqual(md.status, "archived")
        self.assertNotIn(md, Media.objects.all())
        # Archived view surfaces it.
        r = self.client.get(reverse("legacy:media"), {"status": "archived"})
        self.assertContains(r, "Set aside")
        # Now delete forever removes it for good.
        self.client.post(reverse("legacy:media_delete_forever", args=[md.pk]))
        self.assertFalse(Media.all_objects.filter(pk=md.pk).exists())

    def test_restore(self):
        md = Media.objects.create(user=self.user, media_type=Media.MediaType.PHOTO)
        md.archive()
        self.client.post(reverse("legacy:media_restore", args=[md.pk]))
        md.refresh_from_db(); self.assertEqual(md.status, "active")


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


class EditorMediaWorkflowTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def test_multi_upload_returns_json_and_attaches(self):
        m = Memory.objects.create(user=self.user, title="Wedding")
        f1 = SimpleUploadedFile("a.jpg", b"img", content_type="image/jpeg")
        f2 = SimpleUploadedFile("b.jpg", b"img", content_type="image/jpeg")
        r = self.client.post(reverse("legacy:memory_media_add", args=[m.pk]),
                             {"file": [f1, f2]},
                             HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(m.media.count(), 2)
        # First photo becomes the primary.
        m.refresh_from_db()
        self.assertIsNotNone(m.primary_media_id)

    def test_upload_skips_narrative_text_with_guidance(self):
        m = Memory.objects.create(user=self.user, title="Story")
        f = SimpleUploadedFile("journal.md", b"# My life", content_type="text/markdown")
        r = self.client.post(reverse("legacy:memory_media_add", args=[m.pk]),
                             {"file": f}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        data = r.json()
        self.assertEqual(len(data["items"]), 0)
        self.assertTrue(data["skipped"])
        self.assertEqual(m.media.count(), 0)

    def test_remove_detaches_but_keeps_media(self):
        m = Memory.objects.create(user=self.user, title="Story")
        media = Media.objects.create(user=self.user, media_type=Media.MediaType.PHOTO)
        m.media.add(media); m.primary_media = media; m.save()
        r = self.client.post(
            reverse("legacy:memory_media_remove", args=[m.pk, media.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertTrue(r.json()["ok"])
        m.refresh_from_db()
        self.assertEqual(m.media.count(), 0)
        self.assertIsNone(m.primary_media_id)
        # Media itself is not deleted — it may belong to other stories.
        self.assertTrue(Media.objects.filter(pk=media.pk).exists())


class ImportValidationTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def test_import_rejects_photo_without_500(self):
        f = SimpleUploadedFile("photo.jpg", b"\xff\xd8\xff", content_type="image/jpeg")
        r = self.client.post(reverse("legacy:import_new"),
                             {"source_name": "x", "source_type": "plain_text", "file": f})
        self.assertEqual(r.status_code, 200)          # re-renders, never 500
        self.assertContains(r, "Add Photos &amp; Media")
        from apps.legacy.models import ImportBatch
        self.assertEqual(ImportBatch.objects.filter(user=self.user).count(), 0)


class TimelineTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.other = _make_user("tl_other@example.com")
        self.client.force_login(self.user)

    def test_timeline_and_milestone_detail(self):
        ms = LifeMilestone.objects.create(user=self.user, title="Married Heather", kind="marriage", year=1997)
        m = Memory.objects.create(user=self.user, title="Wedding day")
        m.milestones.add(ms)
        r = self.client.get(reverse("legacy:timeline"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Married Heather")
        self.assertContains(r, "1997")
        r2 = self.client.get(reverse("legacy:milestone_detail", args=[ms.pk]))
        self.assertContains(r2, "Wedding day")   # story appears in the chapter

    def test_empty_timeline(self):
        r = self.client.get(reverse("legacy:timeline"))
        self.assertContains(r, "chapters will gather here")

    def test_cannot_view_others_milestone(self):
        ms = LifeMilestone.objects.create(user=self.other, title="Theirs")
        self.assertEqual(self.client.get(reverse("legacy:milestone_detail", args=[ms.pk])).status_code, 404)

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("legacy:timeline")).status_code, 302)
