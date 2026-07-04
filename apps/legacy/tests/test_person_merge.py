"""Canonical Person merge — everything follows the survivor, no duplicate remains."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import (
    Contributor, Media, Memory, MemoryDiscovery, MemoryPerson, Output,
    Person, Relationship, RelationshipAlias,
)
from apps.legacy.services.person_merge import merge_people

User = get_user_model()


def _make_user(email="keeper@example.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class PersonMergeTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def _p(self, name, **kw):
        return Person.objects.create(user=self.user, display_name=name, **kw)

    def test_holistic_merge_moves_everything(self):
        loser = self._p("Marvin Jenkins", birth_year=1945)
        winner = self._p("Marvin Lynn Jenkins")
        photo = Media.objects.create(user=self.user, media_type=Media.MediaType.PHOTO)
        loser.primary_photo = photo; loser.save()

        story = Memory.objects.create(user=self.user, title="Fishing")
        story.people.add(loser)
        attributed = Memory.objects.create(user=self.user, title="His voice", attributed_to=loser)
        dad = self._p("Dad"); kid = self._p("Kid")
        Relationship.objects.create(user=self.user, from_person=dad, to_person=loser, relationship_type="parent of")
        Relationship.objects.create(user=self.user, from_person=loser, to_person=kid, relationship_type="parent of")
        disc = MemoryDiscovery.objects.create(memory=story, kind="person", label="Marvin", linked_person=loser)
        RelationshipAlias.objects.create(user=self.user, alias="pa", label="Pa", person=loser)
        contrib = Contributor.objects.create(user=self.user, name="C", email="c@x.com",
                                             relationship_label="friend", invite_token="t1", person=loser)
        out = Output.objects.create(user=self.user, title="Bio", output_type="biography",
                                    summary="s", scope_person=loser)

        merge_people(self.user, loser=loser, winner=winner)

        self.assertFalse(Person.all_objects.filter(pk=loser.pk).exists())     # duplicate gone
        self.assertFalse(MemoryPerson.objects.filter(person_id=loser.pk).exists())
        self.assertIn(winner, story.people.all())                            # story moved
        attributed.refresh_from_db(); self.assertEqual(attributed.attributed_to_id, winner.pk)
        self.assertTrue(Relationship.objects.filter(from_person=dad, to_person=winner).exists())
        self.assertTrue(Relationship.objects.filter(from_person=winner, to_person=kid).exists())
        disc.refresh_from_db(); self.assertEqual(disc.linked_person_id, winner.pk)
        self.assertTrue(RelationshipAlias.objects.filter(person=winner, alias="pa").exists())
        contrib.refresh_from_db(); self.assertEqual(contrib.person_id, winner.pk)
        out.refresh_from_db(); self.assertEqual(out.scope_person_id, winner.pk)
        winner.refresh_from_db()
        self.assertEqual(winner.birth_year, 1945)                            # blank fact filled
        self.assertEqual(winner.primary_photo_id, photo.pk)                  # photo filled
        self.assertIn("Marvin Jenkins", winner.also_known_as)               # old name searchable

    def test_dedupes_shared_story(self):
        loser = self._p("A"); winner = self._p("B")
        m = Memory.objects.create(user=self.user, title="Both")
        m.people.add(loser); m.people.add(winner)
        merge_people(self.user, loser=loser, winner=winner)
        self.assertEqual(MemoryPerson.objects.filter(memory=m).count(), 1)   # no duplicate edge

    def test_dedupes_relationship_and_drops_self_loop(self):
        loser = self._p("A"); winner = self._p("B"); dad = self._p("Dad")
        Relationship.objects.create(user=self.user, from_person=dad, to_person=loser, relationship_type="parent of")
        Relationship.objects.create(user=self.user, from_person=dad, to_person=winner, relationship_type="parent of")
        Relationship.objects.create(user=self.user, from_person=loser, to_person=winner, relationship_type="married to")
        merge_people(self.user, loser=loser, winner=winner)
        self.assertEqual(Relationship.objects.filter(from_person=dad, to_person=winner).count(), 1)  # deduped
        self.assertFalse(Relationship.objects.filter(from_person=winner, to_person=winner).exists())  # self-loop gone

    def test_alias_repoints_to_winner(self):
        loser = self._p("A"); winner = self._p("B")
        RelationshipAlias.objects.create(user=self.user, alias="pa", label="Pa", person=loser)
        merge_people(self.user, loser=loser, winner=winner)
        self.assertTrue(RelationshipAlias.objects.filter(person=winner, alias="pa").exists())

    def test_cannot_merge_into_self(self):
        p = self._p("A")
        with self.assertRaises(ValueError):
            merge_people(self.user, loser=p, winner=p)

    def test_view_end_to_end(self):
        self.client.force_login(self.user)
        loser = self._p("Marvin Jenkins"); winner = self._p("Marvin Lynn Jenkins")
        story = Memory.objects.create(user=self.user, title="S"); story.people.add(loser)
        r = self.client.post(reverse("legacy:person_merge", args=[loser.pk]), {"into": winner.pk})
        self.assertRedirects(r, reverse("legacy:person_detail", args=[winner.pk]))
        self.assertFalse(Person.all_objects.filter(pk=loser.pk).exists())
        self.assertIn(winner, story.people.all())

    def test_merge_form_renders(self):
        self.client.force_login(self.user)
        loser = self._p("Dup"); self._p("Real Person")
        r = self.client.get(reverse("legacy:person_merge", args=[loser.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Merge Dup")
        self.assertContains(r, "mergePeople")   # search index for the picker
