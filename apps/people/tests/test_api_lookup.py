"""The @mention picker API — what the editor needs to label a selection canonically.

The lookup must (a) return each person's canonical display surfaces so the editor can
label an explicit selection from them (never the raw search fragment), and (b) match a
confirmed custom phrase so "@hon" surfaces the person whose alias is "Honey".
"""
from django.test import TestCase
from django.urls import reverse

from apps.people.models import Person, PersonMembership
from apps.people.services.membership import grant_membership
from apps.people.services.phrases import add_custom_phrase

from ._helpers import make_user


class LookupApiTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.heather = Person.objects.create(
            user=self.user, first_name="Heather", last_name="Jenkins")
        grant_membership(self.heather, PersonMembership.Grant.CONTACT_IMPORT)

    def _results(self, q):
        r = self.client.get(reverse("people:lookup"), {"members": "1", "q": q})
        return r.json()["results"]

    def test_returns_canonical_surfaces(self):
        [row] = self._results("hea")
        self.assertEqual(row["id"], self.heather.pk)
        # Surfaces carry the canonical casing the editor labels from.
        self.assertIn("Heather", row["surfaces"])
        self.assertIn("Heather Jenkins", row["surfaces"])

    def test_matches_confirmed_custom_phrase(self):
        add_custom_phrase(self.heather, "Honey")
        results = self._results("hon")            # matches the alias, not the name
        self.assertEqual([r["id"] for r in results], [self.heather.pk])
        self.assertIn("Honey", results[0]["surfaces"])

    def test_partial_name_still_matches(self):
        self.assertEqual([r["id"] for r in self._results("jenk")], [self.heather.pk])
