# ==============================================================================
# File: apps/core/tests/test_evolving_personal_truth_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Personal Truth can evolve — supersession lineage + acceptance semantics
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-20
# ==============================================================================
"""Memory gives the Chief of Staff continuity, not permission to freeze the user in the past.

People change. A fact that was true is not evidence that the user is wrong today. The store
therefore has to carry *current* truth and *historical* truth without letting the second
masquerade as the first.

This file certifies the deterministic half of that:

  * a correction supersedes rather than destroys — history stays queryable;
  * superseded truth NEVER reaches the model as current;
  * accepting legacy knowledge removes the REVIEW gate and nothing else.

The conversational half (noticing tension, clarifying before superseding) belongs to M6 and
is deliberately NOT built here. No provider calls.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.personal_knowledge import service as pk
from apps.core.personal_knowledge.models import (
    FactStatus, PersonalKnowledgeFact, Provenance, ReviewState, Sensitivity,
)

User = get_user_model()


class LineageTests(TestCase):
    """Does the M2 lineage already give us evolving personal truth? (It does.)"""

    def setUp(self):
        self.user = User.objects.create_user(email="evolve@contract.test", password="x")

    def test_a_correction_supersedes_the_old_fact_without_destroying_it(self):
        old = pk.add_fact(self.user, "I don't enjoy running.", topic="interests")
        new = pk.correct_fact(old, "I've started enjoying running.")
        old.refresh_from_db()
        self.assertEqual(old.fact_status, FactStatus.SUPERSEDED)
        self.assertEqual(old.superseded_by_id, new.id)
        self.assertEqual(new.fact_status, FactStatus.ACTIVE)

    def test_history_remains_queryable_after_supersession(self):
        old = pk.add_fact(self.user, "I don't enjoy running.", topic="interests")
        pk.correct_fact(old, "I've started enjoying running.")
        self.assertTrue(
            PersonalKnowledgeFact.objects.filter(
                pk=old.pk, fact_status=FactStatus.SUPERSEDED).exists(),
            "the previous truth was destroyed rather than kept as history")

    def test_superseded_truth_never_reaches_current_retrieval(self):
        old = pk.add_fact(self.user, "MARKER-OLD I don't enjoy running.", topic="interests")
        pk.correct_fact(old, "MARKER-NEW I've started enjoying running.")
        statements = [f.statement for f in pk.active_facts(self.user)]
        self.assertTrue(any("MARKER-NEW" in s for s in statements))
        self.assertFalse(any("MARKER-OLD" in s for s in statements),
                         "old truth still competes with current truth")

    def test_superseded_truth_never_reaches_standing_context(self):
        old = pk.add_fact(self.user, "MARKER-OLD I don't enjoy running.", topic="interests")
        pk.correct_fact(old, "MARKER-NEW I've started enjoying running.")
        standing = "\n".join(f.statement for f in pk.standing_facts(self.user))
        self.assertIn("MARKER-NEW", standing)
        self.assertNotIn("MARKER-OLD", standing)

    def test_current_truth_survives_a_second_change(self):
        """People change more than once — lineage must chain, not flatten."""
        first = pk.add_fact(self.user, "I don't enjoy running.", topic="interests")
        second = pk.correct_fact(first, "I've started enjoying running.")
        third = pk.correct_fact(second, "I run most mornings now.")
        first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual(first.superseded_by_id, second.id)
        self.assertEqual(second.superseded_by_id, third.id)
        self.assertEqual(
            pk.active_facts(self.user).filter(topic="interests").count(), 1,
            "each change must leave exactly one current truth")

    def test_a_correction_is_user_authored_regardless_of_the_old_provenance(self):
        """A legacy guess the user corrects becomes the user's own statement."""
        old = pk.add_fact(self.user, "Danny dislikes early mornings.", topic="preferences",
                          provenance=Provenance.LEGACY_EXTRACTION,
                          review_state=ReviewState.UNREVIEWED)
        new = pk.correct_fact(old, "I'm usually up before six.")
        self.assertEqual(new.review_state, ReviewState.USER_AUTHORED)


class AcceptanceSemanticsTests(TestCase):
    """Accepting legacy knowledge removes the REVIEW gate — and nothing else."""

    def setUp(self):
        self.user = User.objects.create_user(email="accept@contract.test", password="x")

    def _legacy(self, text, **kw):
        return pk.add_fact(self.user, text, provenance=Provenance.LEGACY_EXTRACTION,
                           review_state=ReviewState.UNREVIEWED, **kw)

    def test_unreviewed_legacy_is_excluded_from_standing_context(self):
        self._legacy("MARKER-UNREVIEWED something old.")
        standing = "\n".join(f.statement for f in pk.standing_facts(self.user))
        self.assertNotIn("MARKER-UNREVIEWED", standing)

    def test_accepting_makes_it_eligible(self):
        fact = self._legacy("MARKER-ACCEPTED something old.")
        pk.mark_reviewed(fact)
        standing = "\n".join(f.statement for f in pk.standing_facts(self.user))
        self.assertIn("MARKER-ACCEPTED", standing)

    def test_acceptance_does_NOT_override_sensitivity_exclusion(self):
        fact = self._legacy("MARKER-SENS a private matter.", sensitivity=Sensitivity.SENSITIVE)
        pk.mark_reviewed(fact)
        standing = "\n".join(f.statement for f in pk.standing_facts(self.user))
        self.assertNotIn("MARKER-SENS", standing,
                         "acceptance leaked a sensitive fact into standing context")

    def test_acceptance_does_NOT_resurrect_a_superseded_fact(self):
        fact = self._legacy("MARKER-OLD stale belief.")
        pk.correct_fact(fact, "MARKER-NEW current belief.")
        fact.refresh_from_db()
        pk.mark_reviewed(fact)                       # accept the SUPERSEDED row
        statements = [f.statement for f in pk.active_facts(self.user)]
        self.assertFalse(any("MARKER-OLD" in s for s in statements),
                         "acceptance resurrected superseded truth")

    def test_acceptance_does_not_rewrite_or_split_the_statement(self):
        compound = ("I am motivated by progress, structure, truth telling, challenge, "
                    "reflection, and clear metrics.")
        fact = self._legacy(compound)
        pk.mark_reviewed(fact)
        fact.refresh_from_db()
        self.assertEqual(fact.statement, compound)
        self.assertEqual(pk.active_facts(self.user).count(), 1,
                         "a compound record was split into invented atomic facts")

    def test_acceptance_does_not_infer_a_topic(self):
        fact = self._legacy("Heather is my wife.")     # would be 'family' if inferred
        pk.mark_reviewed(fact)
        fact.refresh_from_db()
        self.assertEqual(fact.topic, "other", "review invented a topic")

    def test_acceptance_is_immediately_visible_to_the_model(self):
        from apps.ai.cos_services import personal_truth
        fact = self._legacy("MARKER-CACHE something old.")
        personal_truth.build_personal_truth(self.user)   # prime the projection cache
        pk.mark_reviewed(fact)
        standing = "\n".join(f.statement for f in pk.standing_facts(self.user))
        self.assertIn("MARKER-CACHE", standing)


class OwnerMigrationScopeTests(TestCase):
    """The acceptance migration is account-scoped — it must not touch anyone else."""

    def test_the_migration_names_exactly_one_account_and_filters_on_it(self):
        import pathlib
        src = pathlib.Path(
            "apps/core/migrations/0137_accept_owner_legacy_personal_knowledge.py"
        ).read_text(encoding="utf-8")
        self.assertIn('OWNER_EMAIL = "dannyjenkins71@gmail.com"', src)
        self.assertIn("user_id=owner.id", src)
        self.assertIn('review_state="unreviewed"', src)
        self.assertIn('provenance="legacy_extraction"', src)

    def test_the_migration_does_not_touch_statements_topics_or_sources(self):
        import pathlib
        src = pathlib.Path(
            "apps/core/migrations/0137_accept_owner_legacy_personal_knowledge.py"
        ).read_text(encoding="utf-8")
        for banned in ("statement =", ".delete()", "topic=", "superseded_by ="):
            self.assertNotIn(banned, src,
                             f"the acceptance migration does more than lift the gate: {banned}")

    def test_the_personal_knowledge_path_has_no_owner_special_case(self):
        """A one-time migration is fine; a permanent special-case in the PK/review path
        is not — that would make one account's rules different from everyone's forever.

        Deliberately scoped to the surfaces this decision touches. The owner address
        appears in several pre-existing management commands and account-setup paths,
        which is unrelated to how Personal Knowledge is governed.
        """
        import pathlib
        watched = [
            pathlib.Path("apps/core/personal_knowledge"),
            pathlib.Path("apps/users/about_me_views.py"),
            pathlib.Path("apps/ai/cos_services/personal_truth.py"),
        ]
        offenders = []
        for target in watched:
            files = target.rglob("*.py") if target.is_dir() else [target]
            for p in files:
                if "/migrations/" in str(p):
                    continue
                if "dannyjenkins71@gmail.com" in p.read_text(encoding="utf-8"):
                    offenders.append(str(p))
        self.assertEqual(offenders, [],
                         f"owner special-case inside the PK governance path: {offenders}")


class CrossUserIsolationTests(TestCase):
    def test_accepting_one_users_knowledge_leaves_another_untouched(self):
        a = User.objects.create_user(email="a@contract.test", password="x")
        b = User.objects.create_user(email="b@contract.test", password="x")
        fa = pk.add_fact(a, "A's legacy fact.", provenance=Provenance.LEGACY_EXTRACTION,
                         review_state=ReviewState.UNREVIEWED)
        fb = pk.add_fact(b, "B's legacy fact.", provenance=Provenance.LEGACY_EXTRACTION,
                         review_state=ReviewState.UNREVIEWED)
        pk.mark_reviewed(fa)
        fb.refresh_from_db()
        self.assertEqual(fb.review_state, ReviewState.UNREVIEWED,
                         "another user's review gate was lifted")
