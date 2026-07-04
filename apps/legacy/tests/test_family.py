"""Family View — GEDCOM → canonical People/Relationships + the graph builder."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import Person, Relationship
from apps.legacy.services import family_tree
from apps.legacy.services.import_engine import commit_genealogy, create_batch
from apps.legacy.tests.test_gedcom import SAMPLE

User = get_user_model()


def _make_user(email="keeper@example.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _boom(units):
    raise AssertionError("classifier must not run for structured GEDCOM")


class GenealogyCommitTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_commit_creates_people_and_relationships(self):
        batch = create_batch(self.user, "Tree", "gedcom", SAMPLE, classifier=_boom)
        people, links = commit_genealogy(batch)
        self.assertEqual(people, 3)
        self.assertEqual(links, 3)   # 1 marriage + 2 parent links
        marvin = Person.objects.get(user=self.user, display_name="Marvin Jenkins")
        self.assertEqual(marvin.birth_year, 1945)
        self.assertEqual(marvin.death_year, 2010)
        self.assertTrue(Relationship.objects.filter(
            user=self.user, from_person=marvin, relationship_type="married to").exists())
        danny = Person.objects.get(user=self.user, display_name="Danny Jenkins")
        self.assertEqual(Relationship.objects.filter(
            user=self.user, to_person=danny, relationship_type="parent of").count(), 2)

    def test_commit_is_idempotent(self):
        batch = create_batch(self.user, "Tree", "gedcom", SAMPLE, classifier=_boom)
        commit_genealogy(batch)
        people2, links2 = commit_genealogy(batch)
        self.assertEqual((people2, links2), (0, 0))
        self.assertEqual(Person.objects.filter(user=self.user).count(), 3)

    def test_commit_view_redirects_to_family(self):
        self.client.force_login(self.user)
        batch = create_batch(self.user, "Tree", "gedcom", SAMPLE, classifier=_boom)
        r = self.client.post(reverse("legacy:import_commit_genealogy", args=[batch.pk]))
        self.assertRedirects(r, reverse("legacy:family"))
        self.assertEqual(Person.objects.filter(user=self.user).count(), 3)


class FamilyGraphTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_empty(self):
        g = family_tree.build_family_graph(self.user)
        self.assertEqual(g["count"], 0)
        self.assertEqual(g["nodes"], [])

    def test_generations_and_edges(self):
        batch = create_batch(self.user, "Tree", "gedcom", SAMPLE, classifier=_boom)
        commit_genealogy(batch)
        g = family_tree.build_family_graph(self.user)
        self.assertEqual(g["count"], 3)
        by_name = {n["name"]: n for n in g["nodes"]}
        # Parents on the top row, child one generation below.
        self.assertEqual(by_name["Marvin Jenkins"]["y"], by_name["Betty Jenkins"]["y"])
        self.assertGreater(by_name["Danny Jenkins"]["y"], by_name["Marvin Jenkins"]["y"])
        # Living vs deceased from death_year.
        self.assertFalse(by_name["Marvin Jenkins"]["living"])
        self.assertTrue(by_name["Danny Jenkins"]["living"])
        kinds = {e["type"] for e in g["edges"]}
        self.assertIn("parent", kinds)
        self.assertIn("spouse", kinds)

    def test_family_view_renders(self):
        self.client.force_login(self.user)
        batch = create_batch(self.user, "Tree", "gedcom", SAMPLE, classifier=_boom)
        commit_genealogy(batch)
        r = self.client.get(reverse("legacy:family"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Marvin Jenkins")
        self.assertContains(r, "fam-node")
