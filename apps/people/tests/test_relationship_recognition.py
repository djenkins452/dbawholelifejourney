"""Relationship-derived recognition — deterministic first-person role phrases.

"my wife" / "my daughter" / "my father" resolve to the canonical Person straight from the
relationship graph, with NO stored RecognitionPhrase. Every consumer benefits through the
one canonical resolver: these tests prove resolution, the ambiguity guard, the read-only
projections used for display, passive Journal recognition, and the hover card.
"""
import json
from datetime import date

from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.journal.models import JournalEntry
from apps.people import api
from apps.people.models import PersonMention, RecognitionPhrase
from apps.people.services import hooks, resolution
from apps.people.services.mentions import recognize_prose_mentions

from ._helpers import make_user

_rf = RequestFactory()


def _register_hooks():
    """Deterministic registration (AppConfig.ready may have been reset by another test)."""
    from apps.relationships.relationship_recognition import (
        all_role_phrases, person_role_phrases, resolve_relationship_role,
    )
    hooks.register_role_resolver(resolve_relationship_role)
    hooks.register_person_roles_provider(person_role_phrases)
    hooks.register_role_phrases_provider(all_role_phrases)


class RelationshipRecognitionTests(TestCase):
    def setUp(self):
        _register_hooks()
        self.user = make_user()

    def _contact(self, first, rtype, last=""):
        from apps.relationships.models import Person as RP
        return RP.objects.create(
            owner=self.user, first_name=first, last_name=last,
            display_name=(f"{first} {last}").strip(), relationship_type=rtype, status="active")

    def _resolve(self, text):
        return resolution.resolve(self.user, text)

    def test_my_wife_resolves_when_presented_as_wife(self):
        self._contact("Heather", "wife", last="Jenkins")
        r = self._resolve("my wife")
        self.assertEqual(r.status, resolution.RESOLVED)
        self.assertEqual(r.source_type, resolution.RELATIONSHIP_ROLE)
        self.assertEqual(r.person.display_name, "Heather Jenkins")
        # No custom phrase was created — it's a pure projection.
        self.assertFalse(RecognitionPhrase.objects.filter(person=r.person).exists())

    def test_presentation_label_drives_the_phrase_no_contradiction(self):
        # A person presented as "Wife" derives ONLY "my wife" — never "my husband"/"my spouse".
        heather = self._contact("Heather", "wife")
        person = self._resolve("my wife").person
        self.assertEqual(hooks.person_roles(self.user, person), ["my wife"])
        self.assertEqual(self._resolve("my husband").status, resolution.UNRESOLVED)
        self.assertEqual(self._resolve("my spouse").status, resolution.UNRESOLVED)

    def test_each_spouse_presentation_maps_to_its_phrase(self):
        # Distinct users so each presentation is isolated (a user has one spouse).
        for rtype, phrase in [("spouse", "my spouse"), ("wife", "my wife"),
                              ("husband", "my husband"), ("partner", "my partner")]:
            with self.subTest(rtype=rtype):
                user = make_user(f"{rtype}@example.com")
                from apps.relationships.models import Person as RP
                RP.objects.create(owner=user, first_name="Alex", display_name="Alex",
                                  relationship_type=rtype, status="active")
                r = resolution.resolve(user, phrase)
                self.assertEqual(r.status, resolution.RESOLVED)
                self.assertEqual(hooks.person_roles(user, r.person), [phrase])

    def test_daughter_and_father(self):
        self._contact("Haley", "daughter")
        self._contact("Robert", "father")
        for phrase, name in [("my daughter", "Haley"), ("my father", "Robert"),
                             ("my dad", "Robert")]:
            r = self._resolve(phrase)
            self.assertEqual(r.status, resolution.RESOLVED, phrase)
            self.assertEqual(r.person.display_name, name, phrase)

    def test_ambiguous_role_does_not_resolve(self):
        self._contact("Haley", "daughter")
        self._contact("Hannah", "daughter")     # two daughters → ambiguous
        self.assertEqual(self._resolve("my daughter").status, resolution.UNRESOLVED)

    def test_out_of_scope_third_person_phrases_do_not_resolve(self):
        self._contact("Heather", "spouse")
        for phrase in ["his wife", "her husband", "mike's wife", "their daughter"]:
            self.assertEqual(self._resolve(phrase).status, resolution.UNRESOLVED, phrase)

    def test_person_roles_projection_is_readonly(self):
        self._contact("Haley", "daughter")
        person = self._resolve("my daughter").person
        self.assertEqual(hooks.person_roles(self.user, person), ["my daughter"])
        self.assertIn("my daughter", hooks.all_role_phrases(self.user))

    def test_passive_journal_recognizes_my_wife(self):
        self._contact("Heather", "wife", last="Jenkins")
        spouse = self._resolve("my wife").person
        e = JournalEntry.objects.create(
            user=self.user, title="x", entry_date=date(2026, 7, 18),
            body="<p>Had dinner with my wife tonight.</p>")
        e.refresh_from_db()
        self.assertIn(f'data-person-id="{spouse.pk}"', e.body)
        self.assertIn(">my wife</span>", e.body)               # author's wording preserved
        ct = ContentType.objects.get_for_model(JournalEntry)
        mentions = PersonMention.objects.filter(content_type=ct, object_id=e.pk)
        self.assertEqual(mentions.count(), 1)
        self.assertEqual(mentions.first().person_id, spouse.pk)
        self.assertEqual(mentions.first().source_type, PersonMention.Source.RELATIONSHIP_ROLE)

    def test_hover_card_lists_role_phrase(self):
        self._contact("Heather", "wife")
        person = self._resolve("my wife").person
        req = _rf.get("/x")
        req.user = self.user
        card = json.loads(api.card(req, person.pk).content)
        self.assertIn("my wife", card["recognition"])
        self.assertNotIn("my husband", card["recognition"])   # no contradictory phrase
