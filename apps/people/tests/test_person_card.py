"""The shared Person hover-card data endpoint (`people:card`).

One endpoint, many consumers: any recognized-person chip anywhere in WLJ fetches this to
confirm identity on hover and to know where to open the person. Verifies the canonical
identity, the human-readable recognition surfaces, and the feature-contributed facts
(relationship label + rich page URL) that arrive through the people `person_summary` hook
— never by Core importing a feature app.
"""
import json

from django.test import TestCase
from django.urls import reverse

from apps.people.models import Person, PersonMembership
from apps.people.services import hooks
from apps.people.services.membership import grant_membership
from apps.people.services.phrases import add_custom_phrase, derived_display_names

from ._helpers import make_user


class PersonCardTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.heather = Person.objects.create(
            user=self.user, first_name="Heather", last_name="Jenkins", display_name="Heather Jenkins")
        grant_membership(self.heather, PersonMembership.Grant.CONTACT_IMPORT)
        add_custom_phrase(self.heather, "Honey")
        # Deterministic: ensure the relationships summary provider is registered.
        from apps.relationships.person_summary import relationship_person_summary
        hooks.register_person_summary_provider(relationship_person_summary)

    def _card(self, pk):
        return json.loads(self.client.get(reverse("people:card", args=[pk])).content)

    def test_derived_display_names_are_human_readable(self):
        # No lowercase/compact artifacts like "heatherjenkins".
        names = derived_display_names(self.heather)
        self.assertEqual(names, ["Heather", "Heather Jenkins"])
        self.assertNotIn("heatherjenkins", names)

    def test_card_identity_and_recognition(self):
        card = self._card(self.heather.pk)
        self.assertEqual(card["id"], self.heather.pk)
        self.assertEqual(card["name"], "Heather Jenkins")
        self.assertEqual(card["auto_names"], ["Heather", "Heather Jenkins"])
        self.assertIn("Honey", card["nicknames"])
        self.assertIn("Heather", card["recognition"])
        self.assertIn("Honey", card["recognition"])

    def test_card_without_relationship_falls_back_to_canonical_page(self):
        card = self._card(self.heather.pk)
        self.assertEqual(card["relationship"], "")
        self.assertEqual(card["url"], reverse("people:person_detail", args=[self.heather.pk]))

    def test_card_includes_relationship_and_rich_url_via_hook(self):
        from apps.relationships.models import Person as RelPerson
        from apps.people.services.reconciliation import ingest_source_person, MATCH_SOURCE_LINK_ONLY
        rel = RelPerson.objects.create(
            owner=self.user, first_name="Heather", last_name="Jenkins",
            display_name="Heather Jenkins", relationship_type="spouse")
        # Bind this relationships contact to the SAME canonical person.
        from apps.people.models import PersonSourceLink
        PersonSourceLink.objects.create(
            person=self.heather, source_domain=PersonSourceLink.Source.RELATIONSHIPS, source_pk=rel.pk)

        card = self._card(self.heather.pk)
        self.assertEqual(card["relationship"], rel.get_relationship_type_display())
        self.assertEqual(card["url"], reverse("relationships:person_detail", args=[rel.pk]))

    def test_ownership_enforced(self):
        other = make_user("other@example.com")
        theirs = Person.objects.create(user=other, first_name="Nope")
        self.assertEqual(
            self.client.get(reverse("people:card", args=[theirs.pk])).status_code, 404)
