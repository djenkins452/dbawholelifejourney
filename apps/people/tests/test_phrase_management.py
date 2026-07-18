"""Canonical recognition-phrase management endpoints.

A phrase added here is the ONE authority every surface reads: after adding "Honey",
the resolver, the lookup API and passive recognition all recognize it — with NO
module-specific logic. These tests cover the CRUD endpoints, ownership, duplicate
handling, and the end-to-end "add a phrase → every consumer recognizes it" contract.

The views are exercised via RequestFactory (calling the view callables directly) so the
suite never depends on the whole project's URLconf loading — the phrase-management
contract is self-contained to the people app.
"""
from datetime import date

from django.contrib.contenttypes.models import ContentType
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory, TestCase

from apps.journal.models import JournalEntry
from apps.people import api, views
from apps.people.models import Person, PersonMembership, PersonMention, RecognitionPhrase
from apps.people.services import resolution
from apps.people.services.membership import grant_membership
from apps.people.services.mentions import recognize_prose_mentions

from ._helpers import make_user

_rf = RequestFactory()


def _post(user, data):
    req = _rf.post("/people/x/phrases/", data)
    req.user = user
    SessionMiddleware(lambda r: None).process_request(req)
    req.session.save()
    setattr(req, "_messages", FallbackStorage(req))
    return req


class PhraseManagementTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.heather = Person.objects.create(
            user=self.user, first_name="Heather", last_name="Jenkins")
        grant_membership(self.heather, PersonMembership.Grant.CONTACT_IMPORT)

    def _add(self, text, person=None):
        p = person or self.heather
        return views.phrase_add(_post(self.user, {"phrase": text, "next": "/journal/"}), p.pk)

    def test_add_creates_custom_phrase(self):
        r = self._add("Honey")
        self.assertEqual(r.status_code, 302)
        rp = RecognitionPhrase.objects.get(person=self.heather, normalized="honey")
        self.assertEqual(rp.phrase, "Honey")
        self.assertEqual(rp.source, RecognitionPhrase.Source.CUSTOM)

    def test_add_duplicate_derived_name_is_noop(self):
        self._add("Heather")            # already a derived name
        self.assertFalse(RecognitionPhrase.objects.filter(person=self.heather).exists())

    def test_add_duplicate_custom_is_noop(self):
        self._add("Honey")
        self._add("honey")              # same normalized
        self.assertEqual(
            RecognitionPhrase.objects.filter(person=self.heather, normalized="honey").count(), 1)

    def test_delete_removes_phrase(self):
        self._add("Babe")
        rp = RecognitionPhrase.objects.get(person=self.heather, normalized="babe")
        r = views.phrase_delete(_post(self.user, {"next": "/journal/"}), self.heather.pk, rp.pk)
        self.assertEqual(r.status_code, 302)
        self.assertFalse(RecognitionPhrase.objects.filter(pk=rp.pk).exists())

    def test_edit_renames_phrase(self):
        self._add("Swetie")             # typo
        rp = RecognitionPhrase.objects.get(person=self.heather, normalized="swetie")
        views.phrase_edit(
            _post(self.user, {"phrase": "Sweetie", "next": "/journal/"}), self.heather.pk, rp.pk)
        self.assertFalse(RecognitionPhrase.objects.filter(normalized="swetie").exists())
        self.assertTrue(RecognitionPhrase.objects.filter(
            person=self.heather, normalized="sweetie", phrase="Sweetie").exists())

    def test_ownership_enforced(self):
        other = make_user("other@example.com")
        theirs = Person.objects.create(user=other, first_name="Nope")
        with self.assertRaises(Http404):
            self._add("Hax", person=theirs)
        self.assertFalse(RecognitionPhrase.objects.filter(person=theirs).exists())

    def test_added_phrase_is_recognized_everywhere(self):
        """The contract: add once, every consumer recognizes it — no Journal logic."""
        self._add("Honey")
        # 1) The canonical resolver resolves it to Heather.
        res = resolution.resolve(self.user, "Honey")
        self.assertEqual(res.status, resolution.RESOLVED)
        self.assertEqual(res.person.pk, self.heather.pk)
        # 2) The picker API surfaces her by the alias.
        req = _rf.get("/people/api/lookup/", {"members": "1", "q": "hon"})
        req.user = self.user
        import json
        results = json.loads(api.lookup(req).content)["results"]
        self.assertIn(self.heather.pk, [r["id"] for r in results])
        # 3) Passive prose recognition wraps it as the canonical chip.
        html, _src = recognize_prose_mentions(self.user, "<p>Dinner with Honey.</p>")
        self.assertIn(f'data-person-id="{self.heather.pk}"', html)
        self.assertIn(">Honey</span>", html)

    def test_passive_journal_entry_links_alias_to_canonical_person(self):
        self._add("Sweetie")
        e = JournalEntry.objects.create(
            user=self.user, title="x", entry_date=date(2026, 7, 18),
            body="<p>Coffee with sweetie today.</p>")
        e.refresh_from_db()
        self.assertIn(">Sweetie</span>", e.body)          # recognized + case-normalized
        ct = ContentType.objects.get_for_model(JournalEntry)
        mentions = PersonMention.objects.filter(content_type=ct, object_id=e.pk)
        self.assertEqual(mentions.count(), 1)             # no duplicate mentions
        self.assertEqual(mentions.first().person_id, self.heather.pk)


class ProductionPersonPageBridgeTests(TestCase):
    """The production Person page (legacy relationships detail) must always offer
    recognition management — it ENSURES the canonical mirror rather than only querying a
    link that a post-backfill contact wouldn't have."""

    def setUp(self):
        self.user = make_user()

    def _rel_person(self, **kw):
        from apps.relationships.models import Person as RP
        return RP.objects.create(owner=self.user, **kw)

    def _canonical_for(self, rel_person):
        from apps.relationships.views import PersonDetailView
        view = PersonDetailView()
        view.request = _rf.get("/relationships/x/")
        view.request.user = self.user
        return view._ensure_canonical_person(rel_person)

    def test_view_ensures_canonical_mirror_and_membership(self):
        rel = self._rel_person(first_name="Nadia", last_name="Okoro", display_name="Nadia Okoro")
        canonical = self._canonical_for(rel)
        self.assertIsNotNone(canonical)
        from apps.people.models import PersonSourceLink, PersonMembership
        self.assertTrue(PersonSourceLink.objects.filter(
            source_domain="relationships", source_pk=rel.pk, person=canonical).exists())
        self.assertTrue(PersonMembership.objects.filter(person=canonical).exists())  # phrases take effect

    def test_bridge_is_idempotent(self):
        rel = self._rel_person(first_name="Sam", display_name="Sam")
        a = self._canonical_for(rel)
        b = self._canonical_for(rel)
        self.assertEqual(a.pk, b.pk)
        from apps.people.models import PersonSourceLink
        self.assertEqual(PersonSourceLink.objects.filter(
            source_domain="relationships", source_pk=rel.pk).count(), 1)  # no duplicate link

    def test_bridge_dedups_to_existing_canonical_by_name(self):
        # An existing canonical person of the same name is REUSED (no duplicate identity),
        # so their phrases show on the legacy page immediately.
        existing = Person.objects.create(
            user=self.user, first_name="Heather", last_name="Jenkins", display_name="Heather Jenkins")
        grant_membership(existing, PersonMembership.Grant.CONTACT_IMPORT)
        views.phrase_add(_post(self.user, {"phrase": "Honey", "next": "/"}), existing.pk)

        rel = self._rel_person(first_name="Heather", last_name="Jenkins", display_name="Heather Jenkins")
        canonical = self._canonical_for(rel)
        self.assertEqual(canonical.pk, existing.pk)                      # linked, not duplicated
        self.assertIn("honey", [p.normalized for p in canonical.recognition_phrases.all()])
