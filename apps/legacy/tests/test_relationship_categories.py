"""Relationship category — one stored classifier; Family = the family/romantic subset."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import Person, Relationship, classify_category
from apps.legacy.services import family_tree
from apps.legacy.services.import_engine import commit_genealogy, create_batch
from apps.legacy.tests.test_gedcom import SAMPLE

User = get_user_model()


def _u(email="k@x.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True; u.preferences.save()
    return u


class ClassifierTests(TestCase):
    def test_mapping(self):
        cases = {
            "father of": "family", "parent of": "family", "sibling of": "family",
            "step-parent of": "family", "guardian of": "family",
            "married to": "romantic", "former spouse of": "romantic",
            "partner of": "romantic", "boyfriend of": "romantic", "had a relationship with": "romantic",
            "coworker of": "professional", "manager of": "professional", "mentor of": "professional",
            "pastor of": "faith", "teacher of": "education", "neighbor of": "community",
            "friend of": "social", "related to": "other", "": "unknown",
        }
        for t, expected in cases.items():
            self.assertEqual(classify_category(t), expected, t)

    def test_family_tree_categories(self):
        self.assertEqual(Relationship.FAMILY_TREE_CATEGORIES, frozenset({"family", "romantic"}))


class StoredCategoryTests(TestCase):
    def setUp(self):
        self.user = _u()
        self.a = Person.objects.create(user=self.user, display_name="A")
        self.b = Person.objects.create(user=self.user, display_name="B")

    def test_save_stores_category(self):
        r = Relationship.objects.create(user=self.user, from_person=self.a, to_person=self.b,
                                        relationship_type="married to")
        self.assertEqual(r.relationship_category, "romantic")
        r.relationship_type = "coworker of"; r.save()
        r.refresh_from_db()
        self.assertEqual(r.relationship_category, "professional")

    def test_update_fields_still_syncs_category(self):
        r = Relationship.objects.create(user=self.user, from_person=self.a, to_person=self.b,
                                        relationship_type="friend of")
        r.relationship_type = "pastor of"
        r.save(update_fields=["relationship_type"])
        r.refresh_from_db()
        self.assertEqual(r.relationship_category, "faith")   # category re-synced despite update_fields

    def test_gedcom_commit_categorizes(self):
        commit_genealogy(create_batch(self.user, "T", "gedcom", SAMPLE,
                                      classifier=lambda x: (_ for _ in ()).throw(AssertionError())))
        self.assertTrue(Relationship.objects.filter(user=self.user, relationship_type="married to",
                                                    relationship_category="romantic").exists())
        self.assertTrue(Relationship.objects.filter(user=self.user, relationship_type="parent of",
                                                    relationship_category="family").exists())


class ConsumerTests(TestCase):
    def setUp(self):
        self.user = _u()
        self.client.force_login(self.user)

    def _p(self, n): return Person.objects.create(user=self.user, display_name=n)

    def test_family_view_ignores_non_family_categories(self):
        me = self._p("Me"); sp = self._p("Sp"); boss = self._p("Boss")
        Relationship.objects.create(user=self.user, from_person=me, to_person=sp, relationship_type="married to")
        Relationship.objects.create(user=self.user, from_person=me, to_person=boss, relationship_type="manager of")
        parents, children, spouses, couples, link_style = family_tree._edges(self.user)
        self.assertIn(sp.pk, spouses[me.pk])          # spouse (romantic) is in the family graph
        self.assertNotIn(boss.pk, spouses[me.pk])     # manager (professional) is NOT
        self.assertEqual(children[me.pk], set())      # boss not treated as a child either

    def test_hub_browses_actual_relationships_by_role(self):
        me = self._p("Me"); me.is_self = True; me.save(update_fields=["is_self"])
        dad = self._p("Dad Jones"); sp = self._p("Spouse Jones"); c = self._p("Coworker")
        Relationship.objects.create(user=self.user, from_person=dad, to_person=me, relationship_type="parent of")
        Relationship.objects.create(user=self.user, from_person=me, to_person=sp, relationship_type="married to")
        Relationship.objects.create(user=self.user, from_person=me, to_person=c, relationship_type="coworker of")
        r = self.client.get(reverse("legacy:relationships"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Open Family view")     # family launches the visualization
        # The ACTUAL relationships appear, grouped by role from the focal person.
        browse = r.context["browse"]
        self.assertEqual(browse["focal"]["name"], "Me")
        groups = {g["label"]: [it["name"] for it in g["items"]] for g in browse["groups"]}
        self.assertIn("Dad Jones", groups.get("Parents", []))
        self.assertIn("Spouse Jones", groups.get("Spouse", []))
        self.assertIn("Coworker", groups.get("Professional", []))
        self.assertContains(r, "Dad Jones")            # rendered, not just counted

    def test_hub_can_focus_another_person(self):
        me = self._p("Me"); me.is_self = True; me.save(update_fields=["is_self"])
        dad = self._p("Dad"); Relationship.objects.create(
            user=self.user, from_person=dad, to_person=me, relationship_type="parent of")
        r = self.client.get(reverse("legacy:relationships") + "?person=%d" % dad.pk)
        browse = r.context["browse"]
        self.assertEqual(browse["focal"]["name"], "Dad")
        groups = {g["label"]: [it["name"] for it in g["items"]] for g in browse["groups"]}
        self.assertIn("Me", groups.get("Children", []))   # oriented from Dad's view
