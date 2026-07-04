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
        self.assertIn("up", types)              # parent → focus lines
        self.assertIn("down", types)            # focus → child line
        self.assertIn("couple-married", types)  # Danny↔Heather and Marvin↔Gloria
