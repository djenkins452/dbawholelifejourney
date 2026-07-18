"""Canonical PersonMention reconciliation — the ONE writer of mention truth.

Gates: tokens → PersonMention; deletion reconciles; idempotent re-save; ownership
boundary (foreign id dropped); membership granted on mention; extraction parsing.
"""
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from apps.journal.models import JournalEntry
from apps.people.models import Person, PersonMembership, PersonMention
from apps.people.services.mentions import (
    extract_mentions_from_html, reconcile_object_mentions,
)

from ._helpers import make_user


def _span(pid, label):
    return f'<span data-mention data-person-id="{pid}">@{label}</span>'


class ExtractionTests(TestCase):
    def test_extracts_id_and_surface_text_deduped(self):
        html = f"<p>Coffee with {_span(5, 'Heather')} and {_span(9, 'Von')}, then {_span(5, 'Heather')}.</p>"
        self.assertEqual(extract_mentions_from_html(html), [(5, "Heather"), (9, "Von")])

    def test_empty_and_plain(self):
        self.assertEqual(extract_mentions_from_html(""), [])
        self.assertEqual(extract_mentions_from_html("<p>no mentions here</p>"), [])


class ReconcileTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.other = make_user("other@example.com")
        self.heather = Person.objects.create(user=self.user, first_name="Heather", last_name="Jenkins")
        self.entry = JournalEntry.objects.create(user=self.user, title="t", body="<p>x</p>",
                                                  entry_date="2026-07-18")

    def _ct(self):
        return ContentType.objects.get_for_model(JournalEntry)

    def test_token_creates_canonical_mention(self):
        html = f"<p>Lunch with {_span(self.heather.pk, 'Heather')}.</p>"
        result = reconcile_object_mentions(self.entry, html, self.user)
        self.assertEqual(result["created"], 1)
        self.assertTrue(PersonMention.objects.filter(
            person=self.heather, content_type=self._ct(), object_id=self.entry.pk).exists())

    def test_removing_token_removes_mention(self):
        reconcile_object_mentions(self.entry, _span(self.heather.pk, "Heather"), self.user)
        self.assertEqual(PersonMention.objects.count(), 1)
        result = reconcile_object_mentions(self.entry, "<p>she left the entry</p>", self.user)
        self.assertEqual(result["removed"], 1)
        self.assertEqual(PersonMention.objects.count(), 0)

    def test_resave_unchanged_is_idempotent(self):
        html = _span(self.heather.pk, "Heather")
        reconcile_object_mentions(self.entry, html, self.user)
        r2 = reconcile_object_mentions(self.entry, html, self.user)
        self.assertEqual(r2, {"linked": 1, "created": 0, "removed": 0})
        self.assertEqual(PersonMention.objects.count(), 1)

    def test_ownership_boundary_foreign_person_dropped(self):
        foreign = Person.objects.create(user=self.other, first_name="Someone", last_name="Else")
        result = reconcile_object_mentions(self.entry, _span(foreign.pk, "Someone"), self.user)
        self.assertEqual(result["linked"], 0)
        self.assertEqual(PersonMention.objects.count(), 0)

    def test_mention_grants_membership(self):
        self.assertFalse(PersonMembership.objects.filter(person=self.heather).exists())
        reconcile_object_mentions(self.entry, _span(self.heather.pk, "Heather"), self.user)
        self.assertTrue(PersonMembership.objects.filter(
            person=self.heather, granted_via=PersonMembership.Grant.MENTION).exists())


class JournalSignalIntegrationTests(TestCase):
    """The end-to-end save path: saving a JournalEntry reconciles mentions via the
    canonical Phase-0d signal (no legacy path)."""

    def setUp(self):
        self.user = make_user()
        self.heather = Person.objects.create(user=self.user, first_name="Heather", last_name="Jenkins")

    def test_saving_entry_with_token_creates_mention_and_edit_removes_it(self):
        entry = JournalEntry.objects.create(
            user=self.user, title="Day", entry_date="2026-07-18",
            body=f"<p>Testing recognizing {_span(self.heather.pk, 'Heather')} today.</p>")
        ct = ContentType.objects.get_for_model(JournalEntry)
        self.assertTrue(PersonMention.objects.filter(
            person=self.heather, content_type=ct, object_id=entry.pk).exists())
        # Edit: remove the mention → the canonical link is reconciled away.
        entry.body = "<p>She is no longer mentioned.</p>"
        entry.save()
        self.assertFalse(PersonMention.objects.filter(object_id=entry.pk).exists())
