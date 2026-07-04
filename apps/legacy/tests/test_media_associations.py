"""Media Library ↔ story associations: one photo, many stories, no duplicates."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import LifeMilestone, Media, Memory, Person, Place
from apps.legacy.views import suggest_stories_for_media

User = get_user_model()


def _make_user(email="keeper@example.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _photo(user):
    return Media.objects.create(
        user=user, media_type=Media.MediaType.PHOTO,
        file=SimpleUploadedFile("p.jpg", b"img", content_type="image/jpeg"))


class AssociateTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.other = _make_user("other@example.com")
        self.client.force_login(self.user)
        self.media = _photo(self.user)
        self.a = Memory.objects.create(user=self.user, title="Story A")
        self.b = Memory.objects.create(user=self.user, title="Story B")
        self.c = Memory.objects.create(user=self.user, title="Story C")

    def test_scenario_2_associate_with_many_stories_no_duplication(self):
        self.client.post(reverse("legacy:media_associate", args=[self.media.pk]),
                         {"story": [self.a.pk, self.b.pk, self.c.pk]})
        for story in (self.a, self.b, self.c):
            self.assertIn(self.media, story.media.all())
        # No duplication — a single Media row shared by three stories.
        self.assertEqual(Media.objects.filter(user=self.user).count(), 1)
        self.assertEqual(self.media.memories.count(), 3)
        # Re-associating is idempotent (no error, no dupes).
        self.client.post(reverse("legacy:media_associate", args=[self.media.pk]),
                         {"story": [self.a.pk]})
        self.assertEqual(self.a.media.count(), 1)

    def test_associate_sets_primary_when_missing(self):
        self.client.post(reverse("legacy:media_associate", args=[self.media.pk]),
                         {"story": [self.a.pk]})
        self.a.refresh_from_db()
        self.assertEqual(self.a.primary_media_id, self.media.pk)

    def test_scenario_3_detach_keeps_other_links_and_media(self):
        for story in (self.a, self.b, self.c):
            story.media.add(self.media)
        self.client.post(reverse("legacy:media_story_detach", args=[self.media.pk, self.b.pk]))
        self.b.refresh_from_db()
        self.assertNotIn(self.media, self.b.media.all())
        self.assertIn(self.media, self.a.media.all())
        self.assertIn(self.media, self.c.media.all())
        # The media itself remains in the library.
        self.assertTrue(Media.objects.filter(pk=self.media.pk).exists())

    def test_cannot_associate_others_media(self):
        theirs = _photo(self.other)
        r = self.client.post(reverse("legacy:media_associate", args=[theirs.pk]),
                             {"story": [self.a.pk]})
        self.assertEqual(r.status_code, 404)


class SuggestionTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.media = _photo(self.user)

    def test_suggests_stories_sharing_a_person_place_or_milestone(self):
        person = Person.objects.create(user=self.user, display_name="Dad")
        place = Place.objects.create(user=self.user, name="The lake")
        attached = Memory.objects.create(user=self.user, title="Attached")
        attached.people.add(person)
        attached.media.add(self.media)

        shares_person = Memory.objects.create(user=self.user, title="Shares person")
        shares_person.people.add(person)
        shares_place = Memory.objects.create(user=self.user, title="Shares place")
        shares_place.places.add(place)   # place not on the attached story → not suggested
        unrelated = Memory.objects.create(user=self.user, title="Unrelated")

        suggestions = suggest_stories_for_media(self.media)
        self.assertIn(shares_person, suggestions)
        self.assertNotIn(unrelated, suggestions)
        self.assertNotIn(attached, suggestions)   # already attached

    def test_no_suggestions_when_media_has_no_stories(self):
        self.assertEqual(suggest_stories_for_media(self.media), [])


class MediaDetailContextTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def test_detail_shows_attached_stories_and_connections(self):
        media = _photo(self.user)
        person = Person.objects.create(user=self.user, display_name="Mom")
        story = Memory.objects.create(user=self.user, title="Linked story")
        story.people.add(person)
        story.media.add(media)
        Memory.objects.create(user=self.user, title="Another story")   # pickable
        r = self.client.get(reverse("legacy:media_detail", args=[media.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Linked story")
        self.assertContains(r, "In these stories")
        self.assertContains(r, "Mom")                     # connected through the story
        self.assertContains(r, "Add to more stories")     # associate picker present
        self.assertContains(r, reverse("legacy:media_story_detach", args=[media.pk, story.pk]))
