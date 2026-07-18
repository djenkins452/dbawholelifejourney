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


class PassiveProseRecognitionTests(TestCase):
    """Natural prose references resolve to the SAME canonical token as an explicit
    @mention — deterministic only, never guessing."""

    def setUp(self):
        from datetime import date
        from apps.people.services.membership import grant_membership
        self.today = date(2026, 7, 18)
        self.user = make_user()
        self.heather = Person.objects.create(user=self.user, first_name="Heather", last_name="Jenkins")
        grant_membership(self.heather, PersonMembership.Grant.CONTACT_IMPORT)

    def _ct(self):
        return ContentType.objects.get_for_model(JournalEntry)

    def test_prose_name_becomes_a_canonical_mention(self):
        e = JournalEntry.objects.create(
            user=self.user, title="Dinner", entry_date=self.today,
            body="<p>Today I had dinner with Heather.</p>")
        e.refresh_from_db()
        # The stored body now carries the canonical token (renders as a chip on reopen).
        self.assertIn(f'data-person-id="{self.heather.pk}"', e.body)
        # The `@` is an editing gesture only — the finished journal shows the author's
        # wording as a chip, with NO injected "@".
        self.assertIn(">Heather</span>", e.body)
        self.assertNotIn("@", e.body)
        # Plain shadow reads naturally — the original sentence, no "@".
        self.assertEqual(e.body_plain, "Today I had dinner with Heather.")
        # And the canonical PersonMention link exists — same authority as explicit,
        # but recorded with faithful provenance (recognized by name, not "@mention").
        m = PersonMention.objects.get(
            person=self.heather, content_type=self._ct(), object_id=e.pk)
        self.assertEqual(m.source_type, PersonMention.Source.EXACT_NAME)

    def test_ambiguous_name_stays_plain_text(self):
        from apps.people.services.membership import grant_membership
        h2 = Person.objects.create(user=self.user, first_name="Heather", last_name="Smith")
        grant_membership(h2, PersonMembership.Grant.CONTACT_IMPORT)
        e = JournalEntry.objects.create(
            user=self.user, title="x", entry_date=self.today,
            body="<p>I saw Heather today.</p>")   # two Heathers → ambiguous
        e.refresh_from_db()
        self.assertNotIn("data-mention", e.body)          # left as plain prose
        self.assertEqual(PersonMention.objects.filter(object_id=e.pk).count(), 0)

    def test_resave_is_idempotent_no_double_wrap(self):
        e = JournalEntry.objects.create(
            user=self.user, title="x", entry_date=self.today,
            body="<p>Dinner with Heather.</p>")
        e.refresh_from_db()
        first_body = e.body
        e.title = "edited"
        e.save()
        e.refresh_from_db()
        self.assertEqual(e.body, first_body)              # no second token wrapped
        self.assertEqual(e.body.count("data-person-id"), 1)

    def test_non_member_prose_name_not_recognized(self):
        # A genealogy person (no membership) referenced in prose is NOT auto-recognized.
        Person.objects.create(user=self.user, display_name="Ada Lovelace", is_deceased=True)
        e = JournalEntry.objects.create(
            user=self.user, title="x", entry_date=self.today,
            body="<p>Reading about Ada Lovelace.</p>")
        e.refresh_from_db()
        self.assertNotIn("data-mention", e.body)

    def test_custom_phrase_prose_recognition(self):
        from apps.people.services.phrases import add_custom_phrase
        add_custom_phrase(self.heather, "Honey")
        e = JournalEntry.objects.create(
            user=self.user, title="x", entry_date=self.today,
            body="<p>Coffee with Honey this morning.</p>")
        e.refresh_from_db()
        self.assertIn(f'data-person-id="{self.heather.pk}"', e.body)
        # The chip preserves the author's chosen wording ("Honey") — no "@".
        self.assertIn(">Honey</span>", e.body)
        self.assertNotIn("@Honey", e.body)

    def test_saved_mention_has_no_space_before_punctuation(self):
        # An explicit chip stored with the editor's trailing space + punctuation is
        # normalized on save so the finished journal reads naturally.
        token = f'<span data-mention data-person-id="{self.heather.pk}">Heather</span>'
        e = JournalEntry.objects.create(
            user=self.user, title="x", entry_date=self.today,
            body=f"<p>Lunch with {token} , then home.</p>")
        e.refresh_from_db()
        self.assertIn("</span>,", e.body)
        self.assertNotIn("</span> ,", e.body)
        self.assertEqual(e.body_plain, "Lunch with Heather, then home.")

    def test_existing_explicit_token_not_rewrapped(self):
        token = f'<span data-mention data-person-id="{self.heather.pk}">@Heather Jenkins</span>'
        e = JournalEntry.objects.create(
            user=self.user, title="x", entry_date=self.today,
            body=f"<p>Dinner with {token} and later Heather again.</p>")
        e.refresh_from_db()
        # The explicit token is untouched; the second bare "Heather" is recognized too,
        # but still ONE PersonMention (deduped per person+object).
        self.assertEqual(e.body.count("data-mention"), 2)
        self.assertEqual(PersonMention.objects.filter(object_id=e.pk).count(), 1)
        # The person was explicitly @mentioned → keeps explicit provenance (the passive
        # occurrence never downgrades it).
        m = PersonMention.objects.get(object_id=e.pk)
        self.assertEqual(m.source_type, PersonMention.Source.EXPLICIT_AT_MENTION)
