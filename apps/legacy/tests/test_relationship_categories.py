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
        # Parents are typed from SEX evidence and categorized family.
        self.assertTrue(Relationship.objects.filter(user=self.user,
                        relationship_type="biological father of",
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
        parents, children, spouses, couples, link_style, step_pairs = family_tree._edges(self.user)
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
        self.assertIn("Dad Jones", groups.get("Biological parents", []))
        self.assertIn("Spouse Jones", groups.get("Spouse", []))
        self.assertIn("Coworker", groups.get("Professional", []))
        self.assertContains(r, "Dad Jones")            # rendered, not just counted

    def test_browser_shows_exact_relationship_types_not_flattened(self):
        me = self._p("Danny"); me.is_self = True; me.save(update_fields=["is_self"])
        dad = self._p("Marvin"); mom = self._p("Barbara"); step = self._p("Gloria")
        Relationship.objects.create(user=self.user, from_person=dad, to_person=me, relationship_type="biological father of")
        Relationship.objects.create(user=self.user, from_person=mom, to_person=me, relationship_type="biological mother of")
        Relationship.objects.create(user=self.user, from_person=step, to_person=me, relationship_type="stepmother of")
        browse = family_tree.browse_person_relationships(self.user, me.pk)
        # New information architecture: biological parents and additional parent
        # relationships live in their own descriptive sections, not one flat "Parents".
        bio = next(g for g in browse["groups"] if g["label"] == "Biological parents")
        add = next(g for g in browse["groups"] if g["label"] == "Additional parent relationships")
        roles = {it["name"]: it["role"] for it in bio["items"] + add["items"]}
        self.assertEqual(roles["Marvin"], "Biological father")   # NOT "Parent"
        self.assertEqual(roles["Barbara"], "Biological mother")
        self.assertEqual(roles["Gloria"], "Stepmother")
        # Gloria (stepmother) is an ADDITIONAL parent relationship, not biological.
        self.assertIn("Gloria", [it["name"] for it in add["items"]])
        self.assertIn("Marvin", [it["name"] for it in bio["items"]])
        # Every displayed relationship is editable (carries its record pk).
        for it in bio["items"] + add["items"]:
            self.assertIsNotNone(it["pk"])

    def test_family_roles_split_by_derived_degree(self):
        """Blended-family readability: siblings split full/half/step and children split
        biological/step/adopted, all derived from Canonical Truth — not one flat group."""
        me = self._p("Danny"); me.is_self = True; me.save(update_fields=["is_self"])
        marvin = self._p("Marvin"); barbara = self._p("Barbara"); gloria = self._p("Gloria")
        donald = self._p("Donald")
        mark = self._p("Mark"); ana = self._p("Ana"); steve = self._p("Steve")
        cole = self._p("Cole"); lily = self._p("Lily"); sam = self._p("Sam")
        beth = self._p("Beth"); heather = self._p("Heather"); jane = self._p("Jane")

        def R(a, b, t):
            Relationship.objects.create(user=self.user, from_person=a, to_person=b, relationship_type=t)

        # Focal's parents: two biological + one step (additional).
        R(marvin, me, "biological father of"); R(barbara, me, "biological mother of")
        R(gloria, me, "stepmother of")
        # Full sibling shares BOTH bio parents; half shares one; step is the step-parent's
        # own child (shares no biological parent with focal).
        R(marvin, mark, "biological father of"); R(barbara, mark, "biological mother of")
        R(barbara, ana, "biological mother of"); R(donald, ana, "biological father of")
        R(gloria, steve, "biological mother of")
        # Focal's children by kind.
        R(me, cole, "biological father of"); R(me, lily, "stepfather of"); R(me, sam, "adoptive father of")
        # Couples: current spouse / former spouse / partner each get their own section.
        R(me, beth, "married to"); R(me, heather, "former spouse of"); R(me, jane, "partner of")

        browse = family_tree.browse_person_relationships(self.user, me.pk)
        g = {x["label"]: {it["name"] for it in x["items"]} for x in browse["groups"]}
        self.assertEqual(g.get("Biological parents"), {"Marvin", "Barbara"})
        self.assertEqual(g.get("Additional parent relationships"), {"Gloria"})
        self.assertEqual(g.get("Full siblings"), {"Mark"})
        self.assertEqual(g.get("Half siblings"), {"Ana"})
        self.assertEqual(g.get("Step siblings"), {"Steve"})
        self.assertEqual(g.get("Children"), {"Cole"})
        self.assertEqual(g.get("Stepchildren"), {"Lily"})
        self.assertEqual(g.get("Adopted children"), {"Sam"})
        self.assertEqual(g.get("Spouse"), {"Beth"})
        self.assertEqual(g.get("Former spouses"), {"Heather"})
        self.assertEqual(g.get("Partners"), {"Jane"})
        # Empty family-role sections never render.
        self.assertNotIn("Friends", g)
        # Ordering keeps the family reading top-to-bottom: parents, siblings, spouse, children.
        order = [x["label"] for x in browse["groups"]]
        self.assertLess(order.index("Biological parents"), order.index("Full siblings"))
        self.assertLess(order.index("Full siblings"), order.index("Children"))

    def test_any_stored_type_stays_editable(self):
        from apps.legacy.forms import RelationshipForm
        a = self._p("A"); b = self._p("B")
        # A type outside the standard vocabulary must not silently reset on edit.
        rel = Relationship.objects.create(
            user=self.user, from_person=a, to_person=b, relationship_type="odd custom bond")
        form = RelationshipForm(instance=rel)
        self.assertTrue(form._is_valid_choice("married to"))
        posted = RelationshipForm({"relationship_type": "odd custom bond"}, instance=rel)
        self.assertTrue(posted.is_valid())        # accepted, not rejected as invalid choice
        posted.save()
        rel.refresh_from_db()
        self.assertEqual(rel.relationship_type, "odd custom bond")

    def test_new_parent_types_style_and_categorize_correctly(self):
        # Canonical truth flows to the tree: bio = solid, step = dashed; all family.
        from apps.legacy.services.family_tree import _link_style
        from apps.legacy.models import classify_category
        self.assertEqual(_link_style("biological father of"), "solid")
        self.assertEqual(_link_style("stepmother of"), "dashed")
        self.assertEqual(_link_style("adoptive mother of"), "dashed")
        self.assertEqual(classify_category("stepmother of"), "family")
        self.assertEqual(classify_category("biological father of"), "family")

    def test_hub_can_focus_another_person(self):
        me = self._p("Me"); me.is_self = True; me.save(update_fields=["is_self"])
        dad = self._p("Dad"); Relationship.objects.create(
            user=self.user, from_person=dad, to_person=me, relationship_type="parent of")
        r = self.client.get(reverse("legacy:relationships") + "?person=%d" % dad.pk)
        browse = r.context["browse"]
        self.assertEqual(browse["focal"]["name"], "Dad")
        groups = {g["label"]: [it["name"] for it in g["items"]] for g in browse["groups"]}
        self.assertIn("Me", groups.get("Children", []))   # oriented from Dad's view
