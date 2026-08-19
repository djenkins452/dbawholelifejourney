# ==============================================================================
# File: apps/core/tests/test_about_me_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: M3 — About Me workspace + legacy review, at the real HTTP paths
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-19
# ==============================================================================
"""About Me consumer-boundary contract (M3).

Tested at the ACTUAL customer paths, not through helpers — the M2 lesson was that a
subsystem is not certified because its components pass in isolation. What the user sees
and what the Chief of Staff consumes must be the same canonical truth, and a change made
here must reach the model immediately.
"""

import re
from pathlib import Path

from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.core.personal_knowledge import legacy_import
from apps.core.personal_knowledge import service as pk
from apps.core.personal_knowledge.models import (
    PersonalKnowledgeFact, Provenance, ReviewState, Sensitivity, Topic,
)

User = get_user_model()
REPO = Path(__file__).resolve().parents[3]


class AboutMeHarness(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(
            email="am@contract.test", password="x", first_name="AM")
        self.user.has_completed_onboarding = True
        self.user.save()
        TermsAcceptance.objects.get_or_create(
            user=self.user,
            defaults={"terms_version": dj_settings.WLJ_SETTINGS["TERMS_VERSION"]})
        prefs = self.user.preferences
        prefs.has_completed_onboarding = True
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.use_model_interface = True
        prefs.save()
        self.user = User.objects.get(pk=self.user.pk)
        self.client = Client()
        self.client.force_login(self.user)

    def _get(self, name, **kw):
        return self.client.get(reverse(name, kwargs=kw) if kw else reverse(name))

    def _prompt(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(User.objects.get(pk=self.user.pk))
        return svc._system_prompt(svc.build_standing_context())

    def _seed_legacy(self):
        prefs = self.user.preferences
        prefs.ai_personal_context = ("Heather is my wife.\n"
                                     "Haley is my daughter.\n"
                                     "I work in enterprise software.")
        prefs.ai_profile = "I am a father and husband.\n\nI ride motorcycles."
        prefs.save()
        from apps.core.ai_memory.models import PersonalFact
        PersonalFact.objects.create(
            user=self.user, fact_type="family_relationship", subject_name="Linda",
            relationship="wife's mother", fact_text="Linda is my wife's mother.")


class AboutMeTruthTests(AboutMeHarness):
    """The workspace must reflect the SAME canonical authority the CoS consumes."""

    def test_workspace_renders(self):
        r = self._get("users:about_me")
        self.assertEqual(r.status_code, 200)
        self.assertIn("About Me", r.content.decode())

    def test_counts_reflect_canonical_personal_knowledge(self):
        pk.add_fact(self.user, "Heather is my wife.", topic=Topic.FAMILY)
        pk.add_fact(self.user, "Haley is my daughter.", topic=Topic.FAMILY)
        pk.add_fact(self.user, "I ride motorcycles.", topic=Topic.INTERESTS)
        html = self._get("users:about_me").content.decode()
        self.assertIn("2 things I know", html)
        self.assertIn("1 thing I know", html)
        self.assertIn("3 things in total", html)

    def test_topic_drilldown_shows_the_same_authority(self):
        pk.add_fact(self.user, "MARKER-TOPIC Heather is my wife.", topic=Topic.FAMILY)
        html = self._get("users:about_me_topic", topic="family").content.decode()
        self.assertIn("MARKER-TOPIC", html)

    def test_adding_reaches_the_model_immediately(self):
        self.client.post(reverse("users:about_me_add"),
                         {"statement": "MARKER-ADD I ride motorcycles.",
                          "topic": Topic.INTERESTS})
        self.assertIn("MARKER-ADD", self._prompt())

    def test_deleting_disappears_from_about_me_and_the_model(self):
        fact = pk.add_fact(self.user, "MARKER-DEL forget this.", topic=Topic.FAMILY)
        self.assertIn("MARKER-DEL", self._prompt())
        self.client.post(reverse("users:about_me_fact_action",
                                 kwargs={"pk_id": fact.id, "action": "delete"}))
        self.assertNotIn("MARKER-DEL", self._prompt(),
                         "deleted knowledge still reaches the model")
        self.assertNotIn("MARKER-DEL",
                         self._get("users:about_me_topic", topic="family").content.decode())

    def test_correcting_supersedes_and_replaces_everywhere(self):
        fact = pk.add_fact(self.user, "MARKER-OLD married since 1996.", topic=Topic.FAMILY)
        self.client.post(
            reverse("users:about_me_fact_action",
                    kwargs={"pk_id": fact.id, "action": "correct"}),
            {"statement": "MARKER-NEW married since 1997."})
        prompt = self._prompt()
        self.assertNotIn("MARKER-OLD", prompt)
        self.assertIn("MARKER-NEW", prompt)
        fact.refresh_from_db()
        self.assertEqual(fact.fact_status, "superseded",
                         "correction overwrote history instead of superseding it")
        self.assertIsNotNone(fact.superseded_by, "lineage was not preserved")


class EligibilityTests(AboutMeHarness):
    """Review state and sensitivity must hold at the customer boundary."""

    def test_unreviewed_legacy_is_visible_for_review_but_not_in_context(self):
        self._seed_legacy()
        self.client.post(reverse("users:about_me_import"))
        review_html = self._get("users:about_me_review").content.decode()
        self.assertIn("Heather is my wife", review_html,
                      "imported knowledge is not offered for review")
        self.assertNotIn("Heather is my wife", self._prompt(),
                         "UNREVIEWED legacy knowledge entered routine context")

    def test_keeping_a_fact_makes_it_standing_eligible(self):
        self._seed_legacy()
        self.client.post(reverse("users:about_me_import"))
        fact = pk.active_facts(self.user).filter(
            review_state=ReviewState.UNREVIEWED).first()
        statement = fact.statement
        self.assertNotIn(statement[:30], self._prompt())
        self.client.post(reverse("users:about_me_fact_action",
                                 kwargs={"pk_id": fact.id, "action": "keep"}))
        self.assertIn(statement[:30], self._prompt())

    def test_marking_sensitive_removes_it_from_context_immediately(self):
        fact = pk.add_fact(self.user, "MARKER-SENS private detail.", topic=Topic.FAMILY)
        self.assertIn("MARKER-SENS", self._prompt())
        self.client.post(reverse("users:about_me_fact_action",
                                 kwargs={"pk_id": fact.id, "action": "sensitive"}))
        self.assertNotIn("MARKER-SENS", self._prompt())


class LegacyMigrationTests(AboutMeHarness):
    """Adoption must be safe, idempotent and non-destructive."""

    def test_import_adopts_from_every_source(self):
        self._seed_legacy()
        summary = legacy_import.import_legacy_knowledge(self.user)
        for source in (legacy_import.SOURCE_AI_CONTEXT,
                       legacy_import.SOURCE_AI_PROFILE,
                       legacy_import.SOURCE_PERSONAL_FACT):
            with self.subTest(source=source):
                self.assertGreater(summary[source]["adopted"], 0)

    def test_import_is_idempotent(self):
        self._seed_legacy()
        legacy_import.import_legacy_knowledge(self.user)
        first = pk.active_facts(self.user).count()
        again = legacy_import.import_legacy_knowledge(self.user)
        self.assertEqual(sum(v["adopted"] for v in again.values()), 0,
                         "a second import created duplicates")
        self.assertEqual(pk.active_facts(self.user).count(), first)

    def test_everything_adopted_is_unreviewed_legacy_provenance(self):
        self._seed_legacy()
        legacy_import.import_legacy_knowledge(self.user)
        for fact in pk.active_facts(self.user):
            with self.subTest(statement=fact.statement[:30]):
                self.assertEqual(fact.provenance, Provenance.LEGACY_EXTRACTION)
                self.assertEqual(fact.review_state, ReviewState.UNREVIEWED,
                                 "legacy extraction was silently promoted to trusted")

    def test_legacy_sources_are_never_modified_or_deleted(self):
        self._seed_legacy()
        from apps.core.ai_memory.models import PersonalFact
        before_ctx = self.user.preferences.ai_personal_context
        before_profile = self.user.preferences.ai_profile
        before_facts = PersonalFact.objects.filter(user=self.user).count()
        legacy_import.import_legacy_knowledge(self.user)
        prefs = User.objects.get(pk=self.user.pk).preferences
        self.assertEqual(prefs.ai_personal_context, before_ctx)
        self.assertEqual(prefs.ai_profile, before_profile)
        self.assertEqual(PersonalFact.objects.filter(user=self.user).count(), before_facts,
                         "M7 owns retirement — M3 must not delete legacy source data")

    def test_import_records_source_provenance_for_idempotency(self):
        self._seed_legacy()
        legacy_import.import_legacy_knowledge(self.user)
        for fact in pk.active_facts(self.user):
            with self.subTest(statement=fact.statement[:30]):
                self.assertIn("legacy_source", fact.attributes)
                self.assertIn("legacy_ref", fact.attributes)

    def test_profile_split_is_deterministic_not_model_backed(self):
        src = (REPO / "apps/core/personal_knowledge/legacy_import.py").read_text(
            encoding="utf-8")
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        for forbidden in ("openai", "_call_api", "AIService", "completion"):
            self.assertNotIn(forbidden, code,
                             "legacy migration must be deterministic parsing, not learning")


class DomainBoundaryTests(AboutMeHarness):
    """Removing what WLJ learned must never remove what a domain owns."""

    def test_clear_removes_only_personal_knowledge(self):
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user, title="Keep me", completion_status="pending", status="active")
        pk.add_fact(self.user, "MARKER-CLEAR something learned.", topic=Topic.FAMILY)
        self.client.post(reverse("users:about_me_clear"),
                         {"confirm": "remove everything"})
        self.assertEqual(pk.active_facts(self.user).count(), 0)
        self.assertTrue(Task.objects.filter(pk=task.pk).exists(),
                        "clearing learned knowledge deleted a domain record")

    def test_clear_requires_explicit_confirmation(self):
        pk.add_fact(self.user, "MARKER-NOCLEAR keep me.", topic=Topic.FAMILY)
        self.client.post(reverse("users:about_me_clear"), {"confirm": "yes"})
        self.assertEqual(pk.active_facts(self.user).count(), 1,
                         "a destructive action ran without explicit confirmation")

    def test_deleting_knowledge_about_a_person_keeps_the_person(self):
        from apps.people.models import Person
        person = Person.objects.create(user=self.user, display_name="Heather")
        fact = pk.add_fact(self.user, "Heather is my wife.", topic=Topic.FAMILY,
                           subject_person=person)
        self.client.post(reverse("users:about_me_fact_action",
                                 kwargs={"pk_id": fact.id, "action": "delete"}))
        self.assertTrue(Person.objects.filter(pk=person.pk).exists(),
                        "deleting knowledge deleted the canonical Person")


class OwnershipTests(AboutMeHarness):
    """One user can never see or change another's knowledge."""

    def test_another_users_fact_is_not_reachable(self):
        other = User.objects.create_user(email="am2@contract.test", password="x")
        foreign = pk.add_fact(other, "MARKER-FOREIGN their knowledge.", topic=Topic.FAMILY)
        r = self.client.post(reverse("users:about_me_fact_action",
                                     kwargs={"pk_id": foreign.id, "action": "delete"}))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(
            PersonalKnowledgeFact.objects.filter(pk=foreign.id).exists(),
            "a user deleted another user's knowledge")


class PresentationLawTests(AboutMeHarness):
    """The map reports stored knowledge. It never judges the person."""

    FORBIDDEN = ("progress-bar", "completeness", "% complete", "incomplete",
                 "needs attention", "you should add", "missing information")

    def _body(self):
        """ONLY the About Me content, never the surrounding app shell.

        Scanning the whole document produced false failures — the shell legitimately
        contains words like "Rich" (rich text) and "incomplete" elsewhere. The
        presentation law governs THIS page's content, so that is what is asserted.
        """
        html = self._get("users:about_me").content.decode()
        start = html.index('class="content-container about-me"')
        end = html.index("<style", start)
        return html[start:end]

    def test_no_deficiency_language_or_scores(self):
        pk.add_fact(self.user, "Heather is my wife.", topic=Topic.FAMILY)
        body = self._body().lower()
        for phrase in self.FORBIDDEN:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, body)

    def test_empty_topic_reads_as_neutral_storage_not_a_gap(self):
        body = self._body()
        self.assertIn("nothing yet", body)
        for judgy in ("Not yet", "Rich", "0%", "of 12"):
            with self.subTest(label=judgy):
                self.assertNotIn(judgy, body)

    def test_counts_are_text_not_colour_alone(self):
        pk.add_fact(self.user, "Heather is my wife.", topic=Topic.FAMILY)
        self.assertRegex(self._body(), r"\d+ thing[s]? I know")

    def test_privacy_explanation_is_present_and_truthful(self):
        body = self._body()
        self.assertIn("Whole Life Journey remembers", body)
        self.assertIn("AI provider processes", body)
        # Provider/endpoint detail belongs on the deeper "How AI & Your Data Work" page.
        for jargon in ("chat/completions", "Zero Data Retention", "API key"):
            with self.subTest(jargon=jargon):
                self.assertNotIn(jargon, body)


class NoLearningPulledForwardTests(SimpleTestCase):
    """M3 is a management surface. M4/M6 behaviour must not appear."""

    def test_about_me_implements_no_interview_or_extraction(self):
        """Assert on STRUCTURE, not prose.

        A word-scan is the wrong instrument here: the module legitimately names the
        M2 `Provenance.INTERVIEW` / `CANDIDATE_ACCEPTED` enum members to LABEL facts
        that later milestones will create. Naming a provenance is not implementing a
        capability, so this checks imports and callables instead.
        """
        import ast
        src = (REPO / "apps/users/about_me_views.py").read_text(encoding="utf-8")
        tree = ast.parse(src)

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        for forbidden in ("apps.ai.personal_context", "apps.core.ai_memory.life_fact_extractor",
                          "apps.ai.post_response_intelligence", "apps.ai.services",
                          "apps.core.blueprint.learning_mode"):
            with self.subTest(module=forbidden):
                self.assertNotIn(forbidden, imported,
                                 f"About Me must not import {forbidden} — that is learning")

        names = {n.name.lower() for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        for banned in ("interview", "candidate", "extract", "invitation", "coverage"):
            offenders = sorted(n for n in names if banned in n)
            with self.subTest(term=banned):
                self.assertEqual(offenders, [], f"{offenders} implement M4/M6 scope")

        # No background/scheduled writer may exist on this surface.
        for marker in ("shared_task", "celery", "safe_enqueue", ".delay("):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, src, "About Me must have no background writer")

    def test_templates_use_customer_language_not_table_terminology(self):
        for name in ("about_me", "about_me_topic", "about_me_review"):
            html = (REPO / f"templates/users/{name}.html").read_text(encoding="utf-8")
            body = html[html.index("{% block content %}"):]
            for jargon in ("PersonalKnowledgeFact", "source_id", "provenance=",
                           "review_state", "queryset"):
                with self.subTest(template=name, jargon=jargon):
                    self.assertNotIn(jargon, body)

    def test_templates_use_block_comment_syntax(self):
        """`{# #}` is single-line only in Django; a multi-line one RENDERS."""
        for name in ("about_me", "about_me_topic", "about_me_review"):
            html = (REPO / f"templates/users/{name}.html").read_text(encoding="utf-8")
            for m in re.finditer(r"\{#", html):
                seg = html[m.start():m.start() + 400]
                close = seg.find("#}")
                with self.subTest(template=name):
                    self.assertNotEqual(close, -1, "unterminated {# #}")
                    self.assertNotIn("\n", seg[:close],
                                     "multi-line {# #} renders as visible text")
