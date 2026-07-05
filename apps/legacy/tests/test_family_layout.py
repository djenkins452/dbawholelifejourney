"""Family-unit layout — the acceptance test uses Danny's family shape."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.legacy.models import Person, Relationship
from apps.legacy.services import family_tree

User = get_user_model()


def _u(email="k@x.com", first="Danny", last="Jenkins"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!", first_name=first, last_name=last)
    TermsAcceptance.objects.create(user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True; u.preferences.save()
    return u


class LayoutTests(TestCase):
    def setUp(self):
        self.user = _u()

    def _p(self, name, **kw):
        return Person.objects.create(user=self.user, display_name=name, **kw)

    def _rel(self, a, b, t):
        Relationship.objects.create(user=self.user, from_person=a, to_person=b, relationship_type=t)

    def _family(self):
        self.danny = self._p("Danny Ray Jenkins", is_self=True, birth_year=1971)
        self.heather = self._p("Heather Puller", birth_year=1974)
        self.haley = self._p("Haley Jenkins", birth_year=2002)
        self.marvin = self._p("Marvin Jenkins", birth_year=1937)
        self.barbara = self._p("Barbara Dorff", birth_year=1939)
        self.gloria = self._p("Gloria Jenkins", birth_year=1945)
        self.julie = self._p("Julie Mae Jenkins", birth_year=1966)
        self.lynne = self._p("Lynne Anne Jenkins", birth_year=1964)
        self._rel(self.danny, self.heather, "married to")
        self._rel(self.danny, self.haley, "parent of")
        self._rel(self.heather, self.haley, "parent of")
        self._rel(self.marvin, self.danny, "parent of")     # biological father
        self._rel(self.barbara, self.danny, "parent of")     # biological mother (never married Marvin)
        self._rel(self.marvin, self.gloria, "married to")    # stepmother = Marvin's wife
        self._rel(self.marvin, self.julie, "parent of"); self._rel(self.barbara, self.julie, "parent of")
        self._rel(self.marvin, self.lynne, "parent of"); self._rel(self.barbara, self.lynne, "parent of")
        return family_tree.build_family_view(self.user, focus_pk=self.danny.pk)

    def test_focus_row_holds_focus_spouse_and_siblings(self):
        g = self._family()
        by = {n["name"]: n for n in g["nodes"]}
        fy = by["Danny Ray Jenkins"]["y"]
        self.assertEqual(by["Heather Puller"]["y"], fy)         # spouse beside
        self.assertEqual(by["Julie Mae Jenkins"]["y"], fy)      # sibling on the SAME row
        self.assertEqual(by["Lynne Anne Jenkins"]["y"], fy)     # not floated up

    def test_spouse_adjacent_and_child_centered(self):
        g = self._family()
        by = {n["name"]: n for n in g["nodes"]}
        d, h, hal = by["Danny Ray Jenkins"], by["Heather Puller"], by["Haley Jenkins"]
        self.assertLess(abs(d["cx"] - h["cx"]), family_tree.COL_STRIDE)   # close couple
        self.assertGreater(hal["y"], d["y"])                              # child below
        self.assertLessEqual(abs(hal["cx"] - (d["cx"] + h["cx"]) / 2), 2) # centered under couple

    def test_parents_above_focus(self):
        g = self._family()
        by = {n["name"]: n for n in g["nodes"]}
        self.assertLess(by["Marvin Jenkins"]["y"], by["Danny Ray Jenkins"]["y"])
        self.assertLess(by["Barbara Dorff"]["y"], by["Danny Ray Jenkins"]["y"])

    def test_non_couple_parents_have_no_couple_line(self):
        g = self._family()
        couple_pairs = set()
        cx = {n["id"]: n["cx"] for n in g["nodes"]}
        cy = {n["id"]: n["cy"] for n in g["nodes"]}
        for e in g["edges"]:
            if e["type"].startswith("couple"):
                # record which nodes this couple line connects (by coord)
                couple_pairs.add((e["x1"], e["y1"], e["x2"], e["y2"]))
        # Marvin↔Gloria ARE married → a couple line exists
        self.assertTrue(any(e["type"] == "couple-married" for e in g["edges"]))
        # Marvin↔Barbara were never a couple → no couple edge between them
        m, b = self.marvin, self.barbara
        pair = tuple(sorted(((cx[m.pk], cy[m.pk]), (cx[b.pk], cy[b.pk]))))
        for e in g["edges"]:
            if e["type"].startswith("couple"):
                epair = tuple(sorted(((e["x1"], e["y1"]), (e["x2"], e["y2"]))))
                self.assertNotEqual(epair, pair)

    def test_connectors_present(self):
        g = self._family()
        types = {e["type"] for e in g["edges"]}
        self.assertIn("link", types)            # orthogonal parent→child T-connectors
        self.assertIn("couple-married", types)  # Danny↔Heather and Marvin↔Gloria

    def test_step_parent_drawn_with_dashed_connector(self):
        # A step / adoptive / guardian bond must render dashed, a biological one solid.
        me = self._p("Kid", birth_year=2000)
        dad = self._p("Bio Dad", birth_year=1970)
        stepdad = self._p("Step Dad", birth_year=1972)
        self._rel(dad, me, "parent of")
        self._rel(stepdad, me, "step-parent of")
        types = {e["type"] for e in family_tree.build_family_view(self.user, focus_pk=me.pk)["edges"]}
        self.assertIn("link", types)          # the biological bond is solid
        self.assertIn("link-dashed", types)   # the step bond is dashed

    def test_no_two_cards_overlap(self):
        # The headline acceptance criterion: the tree never overlaps people.
        g = self._family()
        nodes = g["nodes"]
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]
                # cards are 176×96; overlap only if BOTH axes overlap
                dx = abs(a["cx"] - b["cx"]) < family_tree.CARD_W
                dy = abs(a["cy"] - b["cy"]) < family_tree.CARD_H
                self.assertFalse(dx and dy,
                                 "%s overlaps %s" % (a["name"], b["name"]))

    def test_only_three_generations_grandparents_and_grandchildren_excluded(self):
        # STRICT 3-generation window: grandparents and grandchildren must NOT appear
        # when Danny is the focus — only parents, Danny+spouse+siblings, children.
        self._family()
        gpa = self._p("Ada Jenkins", birth_year=1910)
        self._rel(gpa, self.marvin, "parent of")      # Danny's grandmother
        grand = self._p("Milo Jenkins", birth_year=2028)
        self._rel(self.haley, grand, "parent of")     # Danny's grandchild
        names = {n["name"] for n in
                 family_tree.build_family_view(self.user, focus_pk=self.danny.pk)["nodes"]}
        self.assertNotIn("Ada Jenkins", names)        # grandparent excluded
        self.assertNotIn("Milo Jenkins", names)       # grandchild excluded
        # The immediate family IS present.
        for who in ["Marvin Jenkins", "Barbara Dorff", "Gloria Jenkins",
                    "Heather Puller", "Haley Jenkins", "Julie Mae Jenkins"]:
            self.assertIn(who, names)
        # Navigating to Marvin brings HIS parent (Ada) into view — 3 gens around Marvin.
        marvin_names = {n["name"] for n in
                        family_tree.build_family_view(self.user, focus_pk=self.marvin.pk)["nodes"]}
        self.assertIn("Ada Jenkins", marvin_names)

    def test_tree_builds_even_when_category_not_backfilled(self):
        # Real-data safety: relationships imported before the relationship_category
        # backfill have a blank category. The tree must STILL populate (self-heal
        # from the familial relationship_type), not collapse to just the focus.
        self._family()
        Relationship.objects.filter(user=self.user).update(relationship_category="")
        g = family_tree.build_family_view(self.user, focus_pk=self.danny.pk)
        names = {n["name"] for n in g["nodes"]}
        self.assertIn("Heather Puller", names)      # spouse still present
        self.assertIn("Marvin Jenkins", names)      # parent still present
        self.assertIn("Haley Jenkins", names)       # child still present
        self.assertTrue(any(e["type"] == "couple-married" for e in g["edges"]))

    def test_clicking_rebuilds_around_new_focus(self):
        # Re-centering on the father makes HIM the focus (gen 0), not a panned view.
        self._family()
        g = family_tree.build_family_view(self.user, focus_pk=self.marvin.pk)
        self.assertEqual(g["focus"], self.marvin.pk)
        by = {n["name"]: n for n in g["nodes"]}
        # Danny is now a CHILD of the focus → below Marvin.
        self.assertGreater(by["Danny Ray Jenkins"]["y"], by["Marvin Jenkins"]["y"])
        self.assertTrue(by["Marvin Jenkins"]["is_focus"])

    def test_half_siblings_render_as_separate_family_units(self):
        # Barbara had children by several fathers. Each COUPLE is its own family unit;
        # the focus appears ONLY with his full siblings, half-siblings cluster apart.
        danny = self._p("Danny", is_self=True, birth_year=1971)
        barbara = self._p("Barbara", sex="F", birth_year=1939)
        marvin = self._p("Marvin", sex="M", birth_year=1937)
        donald = self._p("Donald", sex="M", birth_year=1934)
        lynne = self._p("Lynne", sex="F", birth_year=1964)      # full sibling (Marvin+Barbara)
        cheryl = self._p("Cheryl", sex="F", birth_year=1962)    # half (Donald+Barbara)
        karen = self._p("Karen", sex="F", birth_year=1966)      # half (Donald+Barbara)
        for c in (danny, lynne):
            self._rel(marvin, c, "biological father of"); self._rel(barbara, c, "biological mother of")
        for c in (cheryl, karen):
            self._rel(donald, c, "biological father of"); self._rel(barbara, c, "biological mother of")
        g = family_tree.build_family_view(self.user, focus_pk=danny.pk)
        pos = {n["name"]: n["cx"] for n in g["nodes"]}

        # Danny's cluster (Danny + Lynne) is contiguous and does NOT include the half-sibs.
        full = sorted([pos["Danny"], pos["Lynne"]])
        half = sorted([pos["Cheryl"], pos["Karen"]])
        self.assertLess(max(full), min(half))                   # full-sib cluster is separated
        # The half-sib cluster is tight (Cheryl & Karen adjacent), apart from the full sibs.
        self.assertLess(half[1] - half[0], family_tree.CARD_W * 2)
        self.assertGreater(min(half) - max(full), family_tree.CARD_W)   # a real gap between clusters
        # Donald sits over his own children, not over Danny's.
        self.assertGreater(pos["Donald"], max(full))

    def test_half_sibling_scenario_never_overlaps(self):
        danny = self._p("Danny", is_self=True, birth_year=1971)
        barbara = self._p("Barbara", sex="F", birth_year=1939)
        marvin = self._p("Marvin", sex="M", birth_year=1937)
        william = self._p("William", sex="M", birth_year=1938)
        fred = self._p("Fred", sex="M", birth_year=1940)
        kids = {}
        for nm, dad, by in [("Lynne", marvin, 1964), ("Vicki", william, 1961),
                            ("James", william, 1969), ("Anthony", fred, 1968), ("Gary", fred, 1963)]:
            kids[nm] = self._p(nm, birth_year=by)
            self._rel(dad, kids[nm], "biological father of")
            self._rel(barbara, kids[nm], "biological mother of")
        self._rel(marvin, danny, "biological father of"); self._rel(barbara, danny, "biological mother of")
        nodes = family_tree.build_family_view(self.user, focus_pk=danny.pk)["nodes"]
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]
                self.assertFalse(abs(a["cx"] - b["cx"]) < family_tree.CARD_W
                                 and abs(a["cy"] - b["cy"]) < family_tree.CARD_H,
                                 "%s overlaps %s" % (a["name"], b["name"]))

    def test_co_parent_families_get_independent_connectors(self):
        """No generation-wide bus: each family unit owns a compact connector, and a
        shared parent is DUPLICATED (ghost) beside each co-parent family so the eye reads
        'these children belong to these parents', not one large family."""
        danny = self._p("Danny", is_self=True, birth_year=1971)
        barbara = self._p("Barbara", sex="F", birth_year=1939)
        marvin = self._p("Marvin", sex="M", birth_year=1937)
        fred = self._p("Fred", sex="M", birth_year=1940)
        lynne = self._p("Lynne", birth_year=1964)        # full sibling (Marvin + Barbara)
        halfsib = self._p("HalfSib", birth_year=1968)    # half sibling (Barbara + Fred)
        self._rel(marvin, danny, "biological father of"); self._rel(barbara, danny, "biological mother of")
        self._rel(marvin, lynne, "biological father of"); self._rel(barbara, lynne, "biological mother of")
        self._rel(barbara, halfsib, "biological mother of"); self._rel(fred, halfsib, "biological father of")
        g = family_tree.build_family_view(self.user, focus_pk=danny.pk)
        # The shared parent (Barbara) is duplicated as a ghost beside the co-parent family.
        ghosts = [n for n in g["nodes"] if n.get("is_ghost")]
        self.assertTrue(any(n["name"] == "Barbara" for n in ghosts))
        self.assertFalse(any(n.get("is_ghost") and n["name"] == "Marvin" for n in g["nodes"]))
        pos = {}
        for n in g["nodes"]:
            pos.setdefault(n["name"], []).append(n["cx"])
        lo, hi = sorted([min(pos["Danny"]), min(pos["HalfSib"])])
        # No horizontal child-connector spans from the focus siblings all the way to the
        # distant half-sibling — that continuous bus is exactly what merged the families.
        for e in g["edges"]:
            if e["y1"] == e["y2"] and "couple" not in e["type"]:
                a, b = sorted([e["x1"], e["x2"]])
                self.assertFalse(a <= lo + 5 and b >= hi - 5,
                                 "a connector still spans the whole generation")
