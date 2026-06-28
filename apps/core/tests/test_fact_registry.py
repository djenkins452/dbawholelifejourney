# ==============================================================================
# File: apps/core/tests/test_fact_registry.py
# Description: Layer 1 capability — Deterministic Provider Registry. Routing by
#   predicate, default fallback, idempotent registration. Plus the built-in
#   goal/execution/health providers resolve their keys. No OpenAI.
# ==============================================================================
from django.test import SimpleTestCase

from apps.ai.chatgpt_cos import fact_registry as R


class FactRegistryMechanicsTests(SimpleTestCase):
    def setUp(self):
        self._saved = list(R._PROVIDERS)
        R._PROVIDERS = []

    def tearDown(self):
        R._PROVIDERS = self._saved

    def test_predicate_routing_and_default(self):
        R.register_fact_provider(lambda k: k == "a", lambda u, ks: {"a": {"value": 1}}, "A")
        R.register_fact_provider(lambda k: False, lambda u, ks: {ks[0]: {"value": 9}}, "DEF",
                                 default=True)
        self.assertEqual(R.resolve(None, "a"), ({"value": 1}, "A"))
        self.assertEqual(R.resolve(None, "zzz"), ({"value": 9}, "DEF"))  # default

    def test_registration_is_idempotent_per_source(self):
        R.register_fact_provider(lambda k: True, lambda u, ks: {ks[0]: {"v": 1}}, "X")
        R.register_fact_provider(lambda k: True, lambda u, ks: {ks[0]: {"v": 2}}, "X")
        self.assertEqual(R.registered_sources().count("X"), 1)

    def test_no_match_no_default_returns_empty(self):
        R.register_fact_provider(lambda k: k == "a", lambda u, ks: {"a": {}}, "A")
        self.assertEqual(R.resolve(None, "b"), ({}, None))


class BuiltinProvidersRegisteredTests(SimpleTestCase):
    def test_builtin_sources_present(self):
        import apps.ai.chatgpt_cos.foundational_facts  # noqa: F401 (triggers registration)
        sources = R.registered_sources()
        self.assertIn("get_foundational_goal_facts", sources)
        self.assertIn("get_foundational_execution_facts", sources)
        self.assertIn("get_foundational_health_facts", sources)
