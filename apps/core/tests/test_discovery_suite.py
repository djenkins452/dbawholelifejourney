"""Integrity guard for the Truth Discovery Validation Suite (Owner-2 object suite).

Keeps the suite permanent and self-maintaining: every registered truth domain (except
finance, intentionally out of scope) must have at least one object-discovery prompt, and
every prompt must be well-formed. Fails when a new domain is added but has no
"tell me everything about <object>" prompt — so object coverage cannot silently regress.
This does not run the prompts (that is the operator's Acceptance Center / Owner-2 pass).
"""
from django.test import TestCase

from apps.core.truth.discovery_suite import DISCOVERY_PROMPTS, prompts_by_domain
from apps.core.truth.domain import registered_domains

_REQUIRED_KEYS = ("id", "domain", "object", "prompt", "anchor", "surface", "must_surface")
_OUT_OF_SCOPE = {"finance"}


class DiscoverySuiteIntegrityTests(TestCase):
    def test_every_prompt_is_well_formed(self):
        bad = [p.get("id", "?") for p in DISCOVERY_PROMPTS
               if not all(k in p for k in _REQUIRED_KEYS)
               or not p.get("must_surface")
               or not p["prompt"].strip().endswith(("?", "."))]
        self.assertEqual(bad, [], f"malformed discovery prompts: {bad}")

    def test_prompt_ids_are_unique(self):
        ids = [p["id"] for p in DISCOVERY_PROMPTS]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        self.assertEqual(dupes, [], f"duplicate prompt ids: {dupes}")

    def test_every_registered_domain_has_a_discovery_prompt(self):
        covered = set(prompts_by_domain().keys())
        required = set(registered_domains()) - _OUT_OF_SCOPE
        missing = sorted(required - covered)
        self.assertEqual(
            missing, [],
            f"registered truth domains with NO object-discovery prompt: {missing} "
            f"— add a 'tell me everything about <object>' prompt to discovery_suite.py")
