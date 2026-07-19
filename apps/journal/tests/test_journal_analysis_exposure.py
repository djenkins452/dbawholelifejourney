# ==============================================================================
# File: apps/journal/tests/test_journal_analysis_exposure.py
# Description: Journal Analysis = truth EXPOSURE only. Journal now participates in the
#              shared Analysis Surface by declaring analysis_subjects that REUSE its
#              existing history('mood') + describe('entry') inputs. WLJ supplies the
#              deterministic evidence bundle; the model summarizes/interprets/advises.
#              WLJ declares NO verdict (healthy/concerning/positive/commitment).
# ==============================================================================
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.domain_analysis import (analysis_capable_domains,
                                                  get_domain_analysis)
from apps.core.truth.domain import get_domain_truth
from apps.journal.models import JournalEntry, Tag

User = get_user_model()


def _entry(user, d, *, mood="", body="x"):
    return JournalEntry.objects.create(user=user, title=f"e-{d}", body_plain=body,
                                       entry_date=d, mood=mood)


class JournalAnalysisExposureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="janalysis@example.com", password="x")
        # A small spread of RECENT dated entries with recorded moods (recent so the
        # entity `describe` window includes them, mirroring an active journaler).
        today = date.today()
        for i, mood in enumerate(["great", "good", "okay", "low", "good"]):
            _entry(cls.user, today - timedelta(days=i), mood=mood,
                   body=f"day {i} reflection")

    # 1 — journal participates
    def test_journal_in_analysis_capable(self):
        self.assertIn("journal", analysis_capable_domains())

    # 2 — every declared subject reuses ONLY existing history+entity inputs
    def test_subjects_reference_existing_inputs_only(self):
        truth = get_domain_truth(self.user, "journal")
        hist, ents = set(truth.history_metrics), set(truth.entity_types)
        self.assertTrue(truth.analysis_subjects, "no analysis_subjects declared")
        for subj, m in truth.analysis_subjects.items():
            self.assertIn(m["history_metric"], hist, f"{subj}: history missing")
            self.assertIn(m.get("entity_type"), ents, f"{subj}: entity missing")

    # 3 — summary bundle is ready when entries exist
    def test_summary_ready_with_entries(self):
        a = get_domain_analysis(self.user, "journal", "summary")
        self.assertEqual(a["status"], "ready")
        self.assertTrue(a["holds_data"])

    # 4 — mood analysis includes deterministic mood history
    def test_mood_includes_history(self):
        a = get_domain_analysis(self.user, "journal", "mood")
        self.assertEqual(a["status"], "ready")
        self.assertIn("history", a)
        # at least one window carries mood data points
        present = [w for w, v in a["history"].items() if v.get("present")]
        self.assertTrue(present, "mood history has no populated window")

    # 5 — the bundle includes actual journal entry records
    def test_bundle_includes_entry_records(self):
        a = get_domain_analysis(self.user, "journal", "reflection")
        recs = a.get("records") or {}
        self.assertTrue(recs.get("present"))
        self.assertGreaterEqual(recs.get("count"), 1)
        first = recs["records"][0]
        self.assertIn("date", first["definition"])
        self.assertIn("mood", first["definition"])

    # 6 — empty journal truth → honest empty, NOT unsupported
    def test_empty_journal_is_empty_not_unsupported(self):
        blank = User.objects.create_user(email="jblank@example.com", password="x")
        a = get_domain_analysis(blank, "journal", "summary")
        self.assertEqual(a["status"], "empty")       # not "unsupported"
        self.assertFalse(a["holds_data"])

    # 7 — structured themes appear ONLY from actual saved tags/emotions
    def test_structured_themes_only_from_saved_tags(self):
        # Before any tag: the entry record's tags are empty (no fabricated theme).
        a0 = get_domain_analysis(self.user, "journal", "themes")
        rec0 = (a0["records"]["records"][0])["definition"]
        self.assertEqual(rec0.get("tags", []), [])
        # After saving a real tag: it surfaces on that entry record (structured truth).
        e = JournalEntry.objects.filter(user=self.user).order_by("-entry_date").first()
        tag = Tag.objects.create(user=self.user, name="gratitude")
        e.tags.add(tag)
        a1 = get_domain_analysis(self.user, "journal", "themes")
        newest = a1["records"]["records"][0]["definition"]
        self.assertIn("gratitude", newest.get("tags", []))

    # 8 — WLJ declares no deterministic verdict (no healthy/concerning/positive/commitment)
    def test_no_deterministic_verdict_in_bundle(self):
        import json
        for subj in ("concerns", "positive_changes", "advice"):
            a = get_domain_analysis(self.user, "journal", subj)
            blob = json.dumps(a, default=str).lower()
            for verdict in ("concerning", "healthy", "successful", "commitment",
                            "positive change"):
                self.assertNotIn(f'"{verdict}"', blob,
                                 f"{subj}: WLJ must not emit a '{verdict}' verdict")
            # only data-existence verdicts are allowed
            self.assertIn(a.get("evidence"), ("rich", "thin", "absent"))


class OtherDomainsUnchangedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="jother2@example.com", password="x")

    # 9 — existing analysis-capable domains are unchanged (journal is additive)
    def test_existing_analysis_domains_still_present(self):
        caps = set(analysis_capable_domains())
        for d in ("nutrition", "health", "goals", "habits", "medical"):
            self.assertIn(d, caps, f"{d} lost analysis capability")
