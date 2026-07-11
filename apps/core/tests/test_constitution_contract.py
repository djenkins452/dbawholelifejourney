# ==============================================================================
# File: apps/core/tests/test_constitution_contract.py
# Project: Whole Life Journey - Django Personal Wellness/Journaling App
# Description: CI CONTRACT — the WLJ Chief of Staff Constitution is executable,
#              not merely aspirational. Fails the build if the Constitution
#              document, its Articles, its enforcement references, its governing
#              docs, or its naming rule rot away.
# ==============================================================================
"""
Constitutional contract.

`docs/WLJ_CONSTITUTION.md` locks the permanent architecture of the WLJ Chief of Staff
(ratified at the 2026-07-11 Architecture Milestone). This test makes the Constitution
structural: it fails CI if

  1. the Constitution document disappears or loses its version stamp;
  2. any Article ID (I.1 … V.3) is dropped from it;
  3. an enforcement-table contract test the Constitution names no longer exists
     (so §4 "Enforcement" can never silently point at nothing);
  4. a governing doc the Constitution derives authority to no longer exists;
  5. a user-selected AI display name (e.g. "Beth") is hardcoded as system identity
     in user-facing fixtures (release notes / help) — violating §1 Naming and I.8;
  6. the runtime behavioral constitution names a vendor as system identity.

Changing any of these is itself a constitutional change and must go through the
Constitutional Review process in `docs/WLJ_CONSTITUTION.md` §3.
"""

import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

_ROOT = Path(settings.BASE_DIR)
_DOCS = _ROOT / "docs"

# Canonical Constitution lives in the startup package; docs/WLJ_CONSTITUTION.md is a pointer.
_STARTUP = _ROOT / "@WLJ_SYSTEM_PROMPTS" / "00_WLJ_CHIEF_OF_STAFF_STARTUP"
_CONSTITUTION_CANONICAL = _STARTUP / "02_WLJ_CONSTITUTION.md"
_CONSTITUTION_POINTER = _DOCS / "WLJ_CONSTITUTION.md"
_CONSTITUTION = _CONSTITUTION_CANONICAL if _CONSTITUTION_CANONICAL.exists() else _CONSTITUTION_POINTER

# Every Article that must remain present in the Constitution.
_ARTICLE_IDS = [
    "I.1", "I.2", "I.3", "I.4", "I.5", "I.6", "I.7", "I.8",
    "II.1", "II.2", "II.3", "II.4",
    "III.1", "III.2", "III.3",
    "IV.1", "IV.2", "IV.3", "IV.4",
    "V.1", "V.2", "V.3",
]

# Enforcement-table contract tests the Constitution (§4) points at. If the
# Constitution names an enforcer, the enforcer must exist.
_ENFORCEMENT_TESTS = [
    "apps/core/tests/test_request_path_safety_contract.py",
    "apps/core/tests/test_execution_decision_authority_contract.py",
    "apps/core/tests/test_visual_truth_contract.py",
    "apps/ai/tests/test_intent_registration.py",
]

# Governing docs the Constitution (§6) derives from. These must exist.
_GOVERNING_DOCS = [
    "WLJ_PRODUCT_VISION.md",
    "WLJ_LLM_TRUTH_ACTION_CONTRACT.md",
    "WLJ_ARCHITECTURE_LAWS.md",
    "WLJ_CONDUCTOR_DEVELOPMENT_MODEL.md",
    "WLJ_CURRENT_CONTEXT_CONTRACT.md",
    "WLJ_VISUAL_TRUTH_CONTRACT.md",
    "WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE.md",
    "LAYER1_DOMAIN_FRAMEWORK.md",
]

# User-selected AI display names that must NEVER appear as system identity in
# user-facing fixtures. (Internal code/changelog/dev-doc references are allowed.)
_RESERVED_DISPLAY_NAMES = ["Beth"]

# User-facing fixtures where a hardcoded assistant name would leak to every user.
_USER_FACING_FIXTURES = [
    "apps/core/fixtures/release_notes.json",
    "apps/help/fixtures/help_topics.json",
    "apps/help/fixtures/teaching_destinations.json",
]


class ConstitutionDocumentContractTests(SimpleTestCase):
    """The Constitution document itself must stay intact and versioned."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.text = _CONSTITUTION.read_text(encoding="utf-8") if _CONSTITUTION.exists() else ""

    def test_constitution_document_exists(self):
        self.assertTrue(
            _CONSTITUTION.exists(),
            "docs/WLJ_CONSTITUTION.md is missing — the architecture Constitution must exist.",
        )

    def test_constitution_is_versioned(self):
        self.assertIn(
            "Constitution Version:", self.text,
            "The Constitution must carry a 'Constitution Version:' stamp.",
        )

    def test_all_articles_present(self):
        missing = [aid for aid in _ARTICLE_IDS if f"**{aid} " not in self.text]
        self.assertEqual(
            missing, [],
            f"Constitution is missing Article(s) {missing}. Removing an Article is a "
            "constitutional change — see WLJ_CONSTITUTION.md §3 Constitutional Review.",
        )

    def test_constitutional_review_process_present(self):
        self.assertIn("Constitutional Review", self.text)
        self.assertIn("CONSTITUTIONAL CHANGE PROPOSED", self.text)
        self.assertIn("explicit written approval", self.text)


class ConstitutionEnforcementReferencesTests(SimpleTestCase):
    """Every enforcer and governing doc the Constitution names must exist."""

    def test_enforcement_contract_tests_exist(self):
        missing = [p for p in _ENFORCEMENT_TESTS if not (_ROOT / p).exists()]
        self.assertEqual(
            missing, [],
            f"Constitution §4 references enforcement tests that do not exist: {missing}.",
        )

    def test_governing_docs_exist(self):
        missing = [d for d in _GOVERNING_DOCS if not (_DOCS / d).exists()]
        self.assertEqual(
            missing, [],
            f"Constitution §6 references governing docs that do not exist: {missing}.",
        )


class ConstitutionNamingContractTests(SimpleTestCase):
    """§1 Naming + I.8: no user AI display name / vendor as system identity."""

    def test_no_reserved_display_name_in_user_facing_fixtures(self):
        offenders = []
        for rel in _USER_FACING_FIXTURES:
            path = _ROOT / rel
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            for name in _RESERVED_DISPLAY_NAMES:
                if name in content:
                    offenders.append(f"{rel} contains reserved AI display name '{name}'")
        self.assertEqual(
            offenders, [],
            "A user-selected AI display name is hardcoded in user-facing content "
            f"(§1 Naming / Article I.8): {offenders}. Use 'your Chief of Staff'.",
        )

    def test_runtime_constitution_names_no_vendor(self):
        path = _ROOT / "apps/ai/model_interface/constitution.py"
        if not path.exists():
            self.skipTest("model_interface/constitution.py not present")
        text = path.read_text(encoding="utf-8")
        # The fixed behavioral constitution must remain provider-agnostic.
        for vendor in ["OpenAI", "GPT-4", "gpt-4", "Anthropic", "Claude"]:
            self.assertNotIn(
                vendor, text,
                f"Runtime constitution names vendor '{vendor}' as system identity "
                "(Article I.8 — provider-agnostic behind one seam).",
            )


class ConstitutionResultsNotIntentionsContractTests(SimpleTestCase):
    """Article IV.1 + I.4: the model may reason but never fabricate a WLJ fact.

    The runtime behavioral constitution is the machine-checkable carrier of the
    'results, not intentions' / no-fabrication principle. If that clause is ever
    removed, the model is free to invent facts — a constitutional regression.
    """

    def test_runtime_constitution_forbids_fabrication(self):
        path = _ROOT / "apps/ai/model_interface/constitution.py"
        if not path.exists():
            self.skipTest("model_interface/constitution.py not present")
        text = path.read_text(encoding="utf-8").lower()
        self.assertIn("never", text)
        self.assertTrue(
            ("invent" in text) or ("fabricat" in text),
            "Runtime constitution must forbid inventing/fabricating a WLJ fact "
            "(Article IV.1 results-not-intentions / I.4).",
        )
