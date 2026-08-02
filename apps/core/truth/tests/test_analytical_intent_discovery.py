# ==============================================================================
# File: apps/core/truth/tests/test_analytical_intent_discovery.py
# Description: Capability-discovery contract — the plain-language routing layer
#              (capabilities.domain_semantics[domain].analyzes) advertises the SAME
#              analytical subjects a domain declared in analysis_subjects, DERIVED from
#              the catalog so the two can never silently drift. This is how the model
#              discovers that reflective/thematic journal questions belong to
#              get_analysis(journal, ...), not search_history / an invented domain.
# ==============================================================================
from django.test import SimpleTestCase

from apps.ai.cos_services.current_context import _capabilities
from apps.ai.model_interface.constitution import all_tools
from apps.core.truth.domain import WHOLE_DOMAIN_SUBJECT, get_domain_truth


def _tool_desc(name):
    for t in all_tools():
        if t.get("type") == "function" and t["function"]["name"] == name:
            return t["function"]["description"]
    return ""


class AnalyticalIntentDiscoveryTests(SimpleTestCase):
    def setUp(self):
        self.caps = _capabilities()
        self.sem = self.caps["domain_semantics"]
        self.ta = self.caps["truth_analysis"]

    # 1 — journal's semantic metadata carries its declared analytical intents
    def test_journal_semantics_include_analyzes(self):
        self.assertIn("journal", self.sem)
        self.assertIn("analyzes", self.sem["journal"])
        self.assertTrue(self.sem["journal"]["analyzes"])

    # 2 — analytical coverage cannot silently drift from the registered analysis_subjects.
    # The ONLY subject advertised beyond the raw registration is the synthetic whole-domain
    # roll-up "overall" (added by DomainTruth.supports() for every multi-subject domain and
    # served by get_analysis(domain, 'overall')) — so the advertised set is EXACTLY the
    # registered subjects plus that one generic token, never anything else.
    def test_analyzes_cannot_drift_from_registered_subjects(self):
        registered = set(get_domain_truth(None, "journal").analysis_subjects.keys())
        expected = registered | {WHOLE_DOMAIN_SUBJECT}   # journal is multi-subject
        self.assertEqual(set(self.sem["journal"]["analyzes"]), expected)
        self.assertEqual(sorted(self.sem["journal"]["analyzes"]),
                         sorted(self.ta.get("journal", [])))

    # 3 — journal is described as OWNING these analytical intents
    def test_journal_owns_reflective_intents(self):
        analyzes = set(self.sem["journal"]["analyzes"])
        for intent in ("themes", "gratitude", "patterns", "reflection",
                       "positive_changes", "concerns", "advice"):
            self.assertIn(intent, analyzes, f"journal must advertise analyzing {intent}")

    # 4 — search_history stays content/keyword search (not analytical composition)
    def test_search_history_is_content_search(self):
        d = _tool_desc("search_history").lower()
        self.assertIn("content search", d)
        # it explicitly steers analytical synthesis to get_analysis
        self.assertIn("get_analysis", d)

    # 5 — the model-facing tool contracts receive the authoritative semantics pointer
    def test_tool_contracts_reference_analyzes_metadata(self):
        for name in ("get_analysis", "search_history"):
            self.assertIn("domain_semantics[domain].analyzes", _tool_desc(name),
                          f"{name} must point at the authoritative analyzes metadata")

    # 6 — no invented 'life' analysis domain is advertised anywhere
    def test_no_life_analysis_domain(self):
        self.assertNotIn("life", self.ta)
        self.assertNotIn("life", self.sem)
        self.assertNotIn("life", self.caps.get("answerable_domains", []))

    # 7 — the nutrition/meals boundary semantics are untouched
    def test_nutrition_meals_boundary_unchanged(self):
        self.assertIn("meals", self.sem["nutrition"].get("boundary", "").lower())
        self.assertIn("nutrition", self.sem["meals"].get("boundary", "").lower())

    # 8 — other analysis-capable domains keep their analyzes coverage
    def test_other_domains_analysis_unchanged(self):
        for d in ("nutrition", "health", "goals", "habits", "medical"):
            self.assertIn(d, self.sem, f"{d} lost semantics")
            self.assertEqual(sorted(self.sem[d].get("analyzes", [])),
                             sorted(self.ta.get(d, [])),
                             f"{d} analyzes drifted from truth_analysis")

    # 9 — whole-domain 'overall' is advertised for EVERY multi-subject domain (so the model
    # can ask for a whole-domain summary) and NEVER for a single-subject one (where it would
    # be redundant). This is the capability that answers "overall health this week".
    def test_overall_advertised_iff_multi_subject(self):
        for d, subjects in self.ta.items():
            others = [s for s in subjects if s != WHOLE_DOMAIN_SUBJECT]
            if len(others) >= 2:
                self.assertIn(WHOLE_DOMAIN_SUBJECT, subjects,
                              f"{d} is multi-subject but does not advertise 'overall'")
            else:
                self.assertNotIn(WHOLE_DOMAIN_SUBJECT, subjects,
                                 f"{d} is single-subject but advertises 'overall'")
        self.assertIn(WHOLE_DOMAIN_SUBJECT, self.ta.get("health", []))
