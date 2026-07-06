"""Clarifications are first-class, fully CRUD-able entities — never write-only.

A question can be answered (writes Canonical Truth) OR removed from the queue (deletes
NOTHING in Canonical Truth). Removal is reversible (undo). These tests pin that
contract: delete one / delete many / delete all / undo, always leaving Person,
Relationship, and every other canonical fact untouched.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import ClarificationDismissal, Person, Relationship
from apps.legacy.services import clarification
from apps.legacy.services.import_engine import commit_genealogy, create_batch

User = get_user_model()


# A GEDCOM family with several shared children but NO marriage event → one marriage
# clarification (Legacy preserves the gap, never infers a marriage).
LIKELY_GED = """0 HEAD
0 @I1@ INDI
1 NAME Marvin Lynn /Jenkins/
1 SEX M
0 @I2@ INDI
1 NAME Barbara Jean /Dorff/
1 SEX F
0 @I3@ INDI
1 NAME Danny Ray /Jenkins/
0 @I4@ INDI
1 NAME Lynne Anne /Jenkins/
0 @I5@ INDI
1 NAME Mark /Jenkins/
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 CHIL @I4@
1 CHIL @I5@
0 TRLR
"""


def _make_user(email="crud@example.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class ClarificationCrudServiceTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.batch = create_batch(self.user, "Tree", "gedcom", LIKELY_GED, classifier=lambda x: {})
        commit_genealogy(self.batch)

    def _canon(self):
        return (Person.objects.filter(user=self.user).count(),
                Relationship.objects.filter(user=self.user).count())

    def test_a_question_is_pending_with_a_stable_cid(self):
        q = clarification.pending(self.batch)
        self.assertEqual(len(q), 1)
        self.assertTrue(q[0]["cid"])                       # stable CRUD handle
        self.assertEqual(q[0]["kind"], "marriage_status")

    def test_delete_one_removes_question_and_touches_no_canonical_truth(self):
        before = self._canon()
        cid = clarification.pending(self.batch)[0]["cid"]
        removed = clarification.dismiss(self.user, [cid])
        self.assertEqual(removed, [cid])
        self.assertEqual(clarification.pending(self.batch), [])   # gone from the queue
        self.assertEqual(self._canon(), before)                   # NOTHING deleted in truth
        self.assertEqual(ClarificationDismissal.objects.filter(user=self.user).count(), 1)

    def test_undo_restores_the_question(self):
        cid = clarification.pending(self.batch)[0]["cid"]
        clarification.dismiss(self.user, [cid])
        self.assertEqual(clarification.pending(self.batch), [])
        restored = clarification.restore(self.user, [cid])
        self.assertEqual(restored, [cid])
        self.assertEqual(len(clarification.pending(self.batch)), 1)   # re-derived, back
        self.assertEqual(ClarificationDismissal.objects.filter(user=self.user).count(), 0)

    def test_delete_all_then_undo(self):
        before = self._canon()
        cids = clarification.pending_cids(self.batch)
        self.assertTrue(cids)
        clarification.dismiss(self.user, cids)
        self.assertEqual(clarification.pending(self.batch), [])
        self.assertEqual(self._canon(), before)
        clarification.restore(self.user, cids)
        self.assertEqual(len(clarification.pending(self.batch)), len(cids))

    def test_re_dismiss_is_idempotent(self):
        cid = clarification.pending(self.batch)[0]["cid"]
        self.assertEqual(clarification.dismiss(self.user, [cid]), [cid])
        self.assertEqual(clarification.dismiss(self.user, [cid]), [])   # already gone → no-op
        self.assertEqual(ClarificationDismissal.objects.filter(user=self.user).count(), 1)

    def test_answer_still_writes_canonical_truth(self):
        # Regression: dismissal is a separate path; answering still teaches Legacy.
        item = clarification.pending(self.batch)[0]
        self.assertTrue(clarification.resolve(self.batch, item["kind"], item["ref"], "married"))
        self.assertTrue(Relationship.objects.filter(
            user=self.user, relationship_type__icontains="married").exists())
        self.assertEqual(clarification.pending(self.batch), [])


class ClarificationCrudViewTests(TestCase):
    def setUp(self):
        self.user = _make_user("crudview@example.com")
        self.client.force_login(self.user)
        self.batch = create_batch(self.user, "Tree", "gedcom", LIKELY_GED, classifier=lambda x: {})
        commit_genealogy(self.batch)

    def _pending(self):
        return clarification.pending(self.batch)

    def test_dismiss_view_removes_selected(self):
        cid = self._pending()[0]["cid"]
        r = self.client.post(
            reverse("legacy:clarify_dismiss", args=[self.batch.pk]), {"cids": [cid]})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self._pending(), [])
        # Undo cids are stashed for the one-time banner.
        self.assertEqual(self.client.session.get("clarify_undo"), [cid])

    def test_delete_all_via_scope(self):
        self.assertTrue(self._pending())
        r = self.client.post(
            reverse("legacy:clarify_dismiss", args=[self.batch.pk]), {"scope": "all"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self._pending(), [])

    def test_restore_view_brings_it_back(self):
        cid = self._pending()[0]["cid"]
        self.client.post(reverse("legacy:clarify_dismiss", args=[self.batch.pk]), {"cids": [cid]})
        self.assertEqual(self._pending(), [])
        r = self.client.post(
            reverse("legacy:clarify_restore", args=[self.batch.pk]), {"cids": [cid]})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(len(self._pending()), 1)

    def test_detail_page_renders_crud_controls(self):
        r = self.client.get(reverse("legacy:import_detail", args=[self.batch.pk]))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        for marker in ["clarify-toolbar", "clarify-check", "clarify-menu-btn",
                       "clarify-danger", 'value="all"', "clarify/dismiss"]:
            self.assertIn(marker, html)

    def test_dismiss_only_affects_owner(self):
        other = _make_user("intruder@example.com")
        self.client.force_login(other)
        cid = clarification.pending(self.batch)[0]["cid"]
        # Intruder can't load a batch they don't own.
        r = self.client.post(
            reverse("legacy:clarify_dismiss", args=[self.batch.pk]), {"cids": [cid]})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(ClarificationDismissal.objects.filter(user=other).count(), 0)
