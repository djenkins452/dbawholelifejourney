"""Editor refinements — auto-title, media persistence, consistent thumbnail."""

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import Media, Memory
from apps.legacy.services import discovery as D

User = get_user_model()


def _make_user(email="keeper@example.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _photo(user, name="p.jpg"):
    return Media.objects.create(
        user=user, media_type=Media.MediaType.PHOTO,
        file=SimpleUploadedFile(name, b"img", content_type="image/jpeg"))


class AutoTitleTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_proposes_title_when_empty(self):
        m = Memory.objects.create(user=self.user, title="",
                                  body="We went fishing at the lake all afternoon.")
        D.run_discovery(m, extractor=lambda t: {"suggested_title": "Fishing at the Lake",
                                                "places": []})
        m.refresh_from_db()
        self.assertEqual(m.title, "Fishing at the Lake")

    def test_never_overwrites_an_existing_title(self):
        m = Memory.objects.create(user=self.user, title="My own title",
                                  body="We went fishing at the lake all afternoon.")
        D.run_discovery(m, extractor=lambda t: {"suggested_title": "Fishing at the Lake",
                                                "places": []})
        m.refresh_from_db()
        self.assertEqual(m.title, "My own title")

    def test_discover_view_returns_suggestion_only_when_title_blank(self):
        self.client.force_login(self.user)

        def fake_run(memory, **kw):
            if not (memory.title or "").strip():
                memory.title = "A Quiet Afternoon"
                memory.save()
            return ("nothing", [])

        with patch("apps.legacy.services.discovery.run_discovery", side_effect=fake_run):
            r1 = self.client.post(reverse("legacy:memory_discover"),
                                  {"title": "", "body": "A long enough story to discover."},
                                  HTTP_X_REQUESTED_WITH="XMLHttpRequest")
            r2 = self.client.post(reverse("legacy:memory_discover"),
                                  {"title": "Mine", "body": "A long enough story to discover."},
                                  HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r1.json()["suggested_title"], "A Quiet Afternoon")
        self.assertIsNone(r2.json()["suggested_title"])


class CoverMediaTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def test_uses_primary_photo(self):
        m = Memory.objects.create(user=self.user, title="x")
        photo = _photo(self.user)
        m.media.add(photo)
        m.primary_media = photo
        m.save()
        self.assertEqual(m.cover_media(), photo)

    def test_falls_back_to_first_attached_photo(self):
        m = Memory.objects.create(user=self.user, title="x")
        photo = _photo(self.user)
        m.media.add(photo)   # no primary_media set
        self.assertEqual(m.cover_media(), photo)

    def test_none_when_no_photos(self):
        m = Memory.objects.create(user=self.user, title="x")
        audio = Media.objects.create(user=self.user, media_type=Media.MediaType.AUDIO)
        m.media.add(audio)
        self.assertIsNone(m.cover_media())

    def test_removing_primary_promotes_next_photo(self):
        m = Memory.objects.create(user=self.user, title="x")
        a, b = _photo(self.user, "a.jpg"), _photo(self.user, "b.jpg")
        m.media.add(a, b)
        m.primary_media = a
        m.save()
        self.client.post(reverse("legacy:memory_media_remove", args=[m.pk, a.pk]),
                         HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        m.refresh_from_db()
        self.assertEqual(m.primary_media_id, b.pk)   # thumbnail stays consistent
        self.assertEqual(m.cover_media(), b)


class MediaPersistenceTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def test_attached_media_survives_a_save(self):
        m = Memory.objects.create(user=self.user, title="Trip", body="text")
        photo = _photo(self.user)
        m.media.add(photo)
        # A normal editor save (title/body/people/places) must not drop media.
        self.client.post(reverse("legacy:memory_save"), {
            "pk": m.pk, "title": "Trip", "body": "text edited", "action": "draft",
        })
        m.refresh_from_db()
        self.assertIn(photo, m.media.all())
        # And it renders on reopen.
        r = self.client.get(reverse("legacy:editor", args=[m.pk]))
        self.assertContains(r, reverse("legacy:media_detail", args=[photo.pk]))
