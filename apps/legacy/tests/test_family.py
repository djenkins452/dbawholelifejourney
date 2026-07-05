"""Family View — GEDCOM → canonical People/Relationships + the graph builder."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import Person, Relationship
from apps.legacy.services import family_tree
from apps.legacy.services.family_tree import build_family_view
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
        betty = Person.objects.get(user=self.user, display_name="Betty Jenkins")
        # Parents are typed from SEX evidence — never left generic "Parent".
        self.assertTrue(Relationship.objects.filter(
            user=self.user, from_person=marvin, to_person=danny,
            relationship_type="biological father of").exists())
        self.assertTrue(Relationship.objects.filter(
            user=self.user, from_person=betty, to_person=danny,
            relationship_type="biological mother of").exists())

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
        self.assertIn("link", kinds)   # orthogonal parent→child connectors
        self.assertTrue(any(k.startswith("couple") for k in kinds))   # typed spouse connector

    def test_family_view_renders(self):
        self.client.force_login(self.user)
        batch = create_batch(self.user, "Tree", "gedcom", SAMPLE, classifier=_boom)
        commit_genealogy(batch)
        r = self.client.get(reverse("legacy:family"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Marvin Jenkins")
        self.assertContains(r, "fam-node")

    def test_children_centered_under_parents(self):
        batch = create_batch(self.user, "Tree", "gedcom", SAMPLE, classifier=_boom)
        commit_genealogy(batch)
        by = {n["name"]: n for n in family_tree.build_family_graph(self.user)["nodes"]}
        mid = (by["Marvin Jenkins"]["cx"] + by["Betty Jenkins"]["cx"]) / 2
        self.assertLessEqual(abs(by["Danny Jenkins"]["cx"] - mid), 2)   # child centered under couple

    def test_search_text_on_nodes(self):
        batch = create_batch(self.user, "Tree", "gedcom", SAMPLE, classifier=_boom)
        commit_genealogy(batch)
        marvin = next(n for n in family_tree.build_family_graph(self.user)["nodes"]
                      if n["name"] == "Marvin Jenkins")
        self.assertIn("marvin jenkins", marvin["search"])


class SelfMeTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def _tree(self):
        commit_genealogy(create_batch(self.user, "Tree", "gedcom", SAMPLE, classifier=_boom))

    def test_is_self_flag_resolves_me(self):
        self._tree()
        danny = Person.objects.get(user=self.user, display_name="Danny Jenkins")
        danny.is_self = True; danny.save()
        g = family_tree.build_family_graph(self.user)
        self.assertEqual(g["me"], danny.pk)
        self.assertGreater(g["me_y"], 0)     # a generation below the roots
        self.assertTrue(next(n for n in g["nodes"] if n["id"] == danny.pk)["is_self"])

    def test_name_match_resolves_me(self):
        self.user.first_name = "Danny"; self.user.last_name = "Jenkins"; self.user.save()
        self._tree()
        danny = Person.objects.get(user=self.user, display_name="Danny Jenkins")
        self.assertEqual(family_tree.build_family_graph(self.user)["me"], danny.pk)

    def test_no_me_when_unknown(self):
        self._tree()
        self.assertIsNone(family_tree.build_family_graph(self.user)["me"])

    def test_set_self_is_exclusive(self):
        self.client.force_login(self.user)
        self._tree()
        danny = Person.objects.get(user=self.user, display_name="Danny Jenkins")
        marvin = Person.objects.get(user=self.user, display_name="Marvin Jenkins")
        marvin.is_self = True; marvin.save()
        self.client.post(reverse("legacy:person_set_self", args=[danny.pk]))
        danny.refresh_from_db(); marvin.refresh_from_db()
        self.assertTrue(danny.is_self)
        self.assertFalse(marvin.is_self)     # only one "me"


class FocalViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def _p(self, name, **kw):
        return Person.objects.create(user=self.user, display_name=name, **kw)

    def _parent(self, parent, child):
        Relationship.objects.create(user=self.user, from_person=parent,
                                    to_person=child, relationship_type="parent of")

    def _spouse(self, a, b):
        Relationship.objects.create(user=self.user, from_person=a,
                                    to_person=b, relationship_type="married to")

    def test_focus_defaults_to_me(self):
        me = self._p("Me", is_self=True)
        dad = self._p("Dad"); self._parent(dad, me)
        g = build_family_view(self.user)
        self.assertEqual(g["focus"], me.pk)
        self.assertIn(dad.pk, {n["id"] for n in g["nodes"]})

    def test_focus_param_recenters(self):
        me = self._p("Me", is_self=True)
        dad = self._p("Dad"); self._parent(dad, me)
        g = build_family_view(self.user, focus_pk=dad.pk)
        self.assertEqual(g["focus"], dad.pk)
        self.assertEqual(next(n for n in g["nodes"] if n["is_focus"])["name"], "Dad")

    def test_neighborhood_is_bounded(self):
        chain = [self._p("G%d" % i) for i in range(6)]      # G0 (top) .. G5 (bottom)
        for i in range(5):
            self._parent(chain[i], chain[i + 1])
        far = build_family_view(self.user, focus_pk=chain[5].pk)
        names = {n["name"] for n in far["nodes"]}
        self.assertIn("G4", names)          # 1 generation up (parents) is included
        self.assertNotIn("G3", names)       # grandparents are NOT shown (3-gen window)
        self.assertNotIn("G0", names)

    def test_siblings_and_spouse_sit_on_the_focus_row(self):
        me = self._p("Me", is_self=True)
        sib = self._p("Sib"); sp = self._p("Sp"); dad = self._p("Dad")
        self._parent(dad, me); self._parent(dad, sib); self._spouse(me, sp)
        g = build_family_view(self.user, focus_pk=me.pk)
        by = {n["name"]: n for n in g["nodes"]}
        self.assertEqual(by["Sib"]["y"], by["Me"]["y"])     # sibling beside
        self.assertEqual(by["Sp"]["y"], by["Me"]["y"])      # spouse beside (not floated up)
        self.assertLess(by["Dad"]["y"], by["Me"]["y"])      # parent above

    def test_children_below_the_couple(self):
        me = self._p("Me", is_self=True); sp = self._p("Sp"); kid = self._p("Kid")
        self._spouse(me, sp); self._parent(me, kid); self._parent(sp, kid)
        g = build_family_view(self.user, focus_pk=me.pk)
        by = {n["name"]: n for n in g["nodes"]}
        self.assertGreater(by["Kid"]["y"], by["Me"]["y"])   # child below
        mid = (by["Me"]["cx"] + by["Sp"]["cx"]) / 2
        self.assertLessEqual(abs(by["Kid"]["cx"] - mid), 2)  # centered under the couple

    def test_search_index_spans_all_people(self):
        for i in range(4):
            self._p("Person%d" % i)
        idx = family_tree.family_search_index(self.user)
        self.assertEqual(len(idx), 4)
        self.assertTrue(all("text" in r and "id" in r and "name" in r for r in idx))

    def test_view_renders_tree_chrome(self):
        self.client.force_login(self.user)
        me = self._p("Me", is_self=True); dad = self._p("Dad"); self._parent(dad, me)
        r = self.client.get(reverse("legacy:family"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "is-focus")
        self.assertContains(r, "famSearchData")     # full-family search index present
        self.assertContains(r, "fam-node-details")  # per-card Details button (opens inspector)
        self.assertContains(r, "fam-genlabel")      # generation labels
        self.assertContains(r, "data-recenter")     # click-card-to-recenter
        self.assertContains(r, "fam-legend")        # relationship-line legend
        self.assertContains(r, "famPanels")         # inspector data for every node
        self.assertContains(r, 'id="famPanel"')     # the inspector (hidden until Details)
        self.assertContains(r, "famPanelClose")     # inspector has a close button

    def test_view_provides_inspector_data_per_node(self):
        me = self._p("Me", is_self=True); dad = self._p("Dad")
        sp = self._p("Sp"); kid = self._p("Kid")
        self._parent(dad, me); self._spouse(me, sp); self._parent(me, kid)
        panels = build_family_view(self.user, focus_pk=me.pk)["panels"]
        # Every rendered node has inspector data; a non-focus person too (dad).
        self.assertIn(me.pk, panels)
        self.assertIn(dad.pk, panels)
        self.assertEqual([r["name"] for r in panels[me.pk]["spouses"]], ["Sp"])
        self.assertEqual([r["name"] for r in panels[me.pk]["children"]], ["Kid"])
        self.assertEqual([r["name"] for r in panels[dad.pk]["children"]], ["Me"])

    def test_panel_lists_focus_relatives(self):
        me = self._p("Me", is_self=True); dad = self._p("Dad"); sp = self._p("Sp")
        kid = self._p("Kid"); sib = self._p("Sib")
        self._parent(dad, me); self._parent(dad, sib); self._spouse(me, sp)
        self._parent(me, kid)
        panel = build_family_view(self.user, focus_pk=me.pk)["panel"]
        self.assertTrue(panel["is_self"])
        self.assertEqual([r["name"] for r in panel["parents"]], ["Dad"])
        self.assertEqual([r["name"] for r in panel["spouses"]], ["Sp"])
        self.assertEqual([r["name"] for r in panel["children"]], ["Kid"])
        self.assertEqual([r["name"] for r in panel["siblings"]], ["Sib"])

    def test_parent_and_child_connectors_present(self):
        me = self._p("Me", is_self=True); dad = self._p("Dad"); kid = self._p("Kid")
        self._parent(dad, me); self._parent(me, kid)
        edges = build_family_view(self.user, focus_pk=me.pk)["edges"]
        kinds = {e["type"] for e in edges}
        self.assertIn("link", kinds)    # orthogonal T-connectors for both parent & child
        # Dad→Me link (above) and Me→Kid link (below) both exist.
        by = {n["name"]: n for n in build_family_view(self.user, focus_pk=me.pk)["nodes"]}
        ys = sorted({e["y1"] for e in edges if e["type"] == "link"}
                    | {e["y2"] for e in edges if e["type"] == "link"})
        self.assertGreaterEqual(len(ys), 3)   # spans dad-row, focus-row, kid-row buses/risers
