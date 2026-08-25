# ==============================================================================
# File: apps/finance/tests/test_finance_read_only_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Finance READ-ONLY architectural invariant, enforced in code.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Finance is structurally read-only, and owns no reasoning authority.

RATIFIED INVARIANT (`docs/WLJ_FINANCE_INTELLIGENCE_ARCHITECTURE_ASSESSMENT.md` §10.3):

    WLJ may write its own CLASSIFICATION of the world.
    WLJ may never write TO the world.

Finance may observe, explain, ask for confirmation, persist its own classifications and
the user's corrections through normal application paths, raise insights, schedule
follow-ups, and record whether an externally-completed action happened. It may NEVER move
money, pay a bill, change a payment method, cancel a subscription, dispute a charge,
initiate a reimbursement, or modify an external account.

Two structural conditions make that true today, and these tests keep them true:

  1. No Finance intent is exposed in ``ALLOWED_WRITE_INTENTS`` — the curated set the
     certified Chief of Staff may execute. If none exists, the CoS *cannot* write Finance.
  2. No module under ``apps/finance/`` owns a reasoning authority: no provider client, no
     domain-local system prompt. Finance produces deterministic truth; the canonical model
     interface reasons over it (Constitution I.2 / IV.4).

Condition 2 is the class-elimination half of F-1: retiring `FinanceAIService` removed one
instance; this test makes a RECURRENCE structurally detectable.
"""
from __future__ import annotations

import ast
from pathlib import Path

from django.test import SimpleTestCase

FINANCE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = FINANCE_DIR.parents[1]

# Tokens that mean "this module can talk to a model provider".
_PROVIDER_TOKENS = (
    "build_guarded_client",
    "OpenAI(",
    "_call_api",
    "_call_api_with_tools",
)
# Importing the shared AIService from a domain app is how a domain-local reasoning
# authority gets built. Finance consumes truth; it does not reason.
_PROVIDER_IMPORTS = (
    "apps.ai.services",
    "apps.ai.llm_admission",
    "openai",
)
# A domain-local system prompt is the signature of a second reasoning authority.
_PROMPT_TOKENS = (
    "system_prompt",
    "SYSTEM_PROMPT",
)


def _finance_sources():
    for path in FINANCE_DIR.rglob("*.py"):
        parts = path.parts
        if "migrations" in parts or "__pycache__" in parts:
            continue
        if path.name.startswith("test_") or "tests" in parts:
            continue
        yield path


class FinanceReadOnlyContractTests(SimpleTestCase):
    """The read-only + no-reasoning-authority invariant."""

    def test_scanner_actually_scans_finance(self):
        """Guard against a vacuously-passing scan (moved tree / bad glob)."""
        sources = list(_finance_sources())
        self.assertGreater(
            len(sources), 8,
            "Finance source scan found too few modules — the glob is broken and the "
            "invariant tests below would pass vacuously.",
        )

    def test_no_finance_intent_is_write_enabled(self):
        """No Finance intent may appear in the curated write set.

        This is the structural guarantee behind 'the MVP must not move money'. Adding a
        Finance write intent is a deliberate architectural decision, not a milestone
        footnote — it must fail here first.
        """
        from apps.ai.model_interface.constitution import ALLOWED_WRITE_INTENTS

        finance_markers = (
            "transaction", "budget", "payment", "transfer", "bill", "invoice",
            "payee", "account_balance", "reimburse", "subscription", "expense",
        )
        offenders = [
            name for name in ALLOWED_WRITE_INTENTS
            if any(marker in name.lower() for marker in finance_markers)
        ]
        self.assertEqual(
            offenders, [],
            "Finance is read-only (assessment §10.3). A Finance write intent appeared in "
            f"ALLOWED_WRITE_INTENTS: {offenders}. WLJ may write its own classification of "
            "the world; it may never write to the world.",
        )

    def test_no_provider_client_in_finance(self):
        """No module under apps/finance/ may reach a model provider."""
        offenders = []
        for path in _finance_sources():
            source = path.read_text(encoding="utf-8")
            hits = [tok for tok in _PROVIDER_TOKENS if tok in source]
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                module = None
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                elif isinstance(node, ast.Import):
                    module = ",".join(alias.name for alias in node.names)
                if module and any(imp in module for imp in _PROVIDER_IMPORTS):
                    hits.append(f"import {module}")
            if hits:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {sorted(set(hits))}")
        self.assertEqual(
            offenders, [],
            "Finance must own no reasoning authority — the canonical model interface "
            "reasons over Finance truth (Constitution I.2 / IV.4). Provider access found "
            f"in: {offenders}",
        )

    def test_no_domain_local_system_prompt_in_finance(self):
        """No module under apps/finance/ may define its own system prompt."""
        offenders = [
            str(path.relative_to(REPO_ROOT))
            for path in _finance_sources()
            if any(tok in path.read_text(encoding="utf-8") for tok in _PROMPT_TOKENS)
        ]
        self.assertEqual(
            offenders, [],
            "A domain-local system prompt is a second reasoning authority. Finance "
            f"exposes truth; it does not prompt a model. Found in: {offenders}",
        )

    def test_finance_is_not_in_inline_llm_allowlist(self):
        """Finance request paths never make an inline provider call."""
        from apps.core.tests.test_request_path_safety_contract import (
            INLINE_LLM_ALLOWLIST,
        )

        finance_entries = [m for m in INLINE_LLM_ALLOWLIST if m.startswith("apps/finance/")]
        self.assertEqual(
            finance_entries, [],
            "No Finance module may be allowlisted for inline request-path LLM calls "
            f"(found: {finance_entries}). Finance answers from deterministic truth.",
        )
