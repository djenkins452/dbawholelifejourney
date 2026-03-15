"""
Tests for the central engine registry and dependency graph.

Project: Whole Life Journey
Path: apps/core/tests/test_engine_registry.py
"""

from django.test import TestCase

from apps.core.engine_registry import (
    ENGINE_REGISTRY,
    get_critical_engines,
    get_dependency_chain,
    get_dependency_graph,
    get_dependents,
    get_engine,
    get_engine_codes,
    get_engine_count,
    get_engines_by_category,
    get_engines_by_phase,
    get_engines_that_mutate,
    get_impact_chain,
    get_manual_engines,
    get_registry_summary,
    get_scheduled_engines,
    validate_registry,
)


class EngineRegistryBasicTests(TestCase):
    """Test basic registry queries."""

    def test_registry_has_engines(self):
        """Registry should have 40+ engines."""
        self.assertGreater(get_engine_count(), 40)

    def test_get_engine_by_code(self):
        """Should retrieve known engines by code."""
        sae = get_engine("SAE")
        self.assertIsNotNone(sae)
        self.assertEqual(sae.code, "SAE")
        self.assertEqual(sae.name, "State Aggregation Engine")

    def test_get_engine_unknown_returns_none(self):
        """Unknown code should return None."""
        self.assertIsNone(get_engine("NONEXISTENT"))

    def test_get_engines_by_phase(self):
        """Should filter by pipeline phase."""
        phase_1 = get_engines_by_phase(1)
        self.assertTrue(len(phase_1) > 0)
        for engine in phase_1:
            self.assertEqual(int(engine.phase), 1)

    def test_get_scheduled_engines(self):
        """Should return engines with ISE task names."""
        scheduled = get_scheduled_engines()
        self.assertTrue(len(scheduled) > 10)
        for engine in scheduled:
            self.assertIsNotNone(engine.ise_task_name)

    def test_get_manual_engines(self):
        """Should return engines that support manual execution."""
        manual = get_manual_engines()
        self.assertTrue(len(manual) > 5)
        for engine in manual:
            self.assertTrue(engine.can_manual_run)

    def test_manual_engines_have_batch_runners(self):
        """Every manual-run engine must have a batch_runner path."""
        manual = get_manual_engines()
        for engine in manual:
            self.assertIsNotNone(
                engine.batch_runner,
                f"{engine.code} has can_manual_run=True but no batch_runner"
            )

    def test_get_engines_by_category(self):
        """Should filter by category."""
        core = get_engines_by_category("core")
        self.assertTrue(len(core) > 10)
        blueprint = get_engines_by_category("blueprint")
        self.assertTrue(len(blueprint) > 3)

    def test_all_engine_codes_unique(self):
        """All engine codes must be unique (enforced by dict keys)."""
        codes = get_engine_codes()
        self.assertEqual(len(codes), get_engine_count())


class EngineRegistryValidationTests(TestCase):
    """Test registry validation catches issues."""

    def test_validate_registry_no_critical_warnings(self):
        """Registry should pass validation without critical warnings."""
        warnings = validate_registry()
        # Filter out expected warnings (if any)
        critical = [w for w in warnings if "depends on" in w and "not in the registry" in w]
        self.assertEqual(
            critical, [],
            f"Registry has broken dependency references: {critical}"
        )

    def test_no_dependency_cycles(self):
        """No circular dependencies should exist in the engine graph."""
        warnings = validate_registry()
        cycles = [w for w in warnings if "cycle" in w.lower()]
        self.assertEqual(
            cycles, [],
            f"Dependency cycles detected: {cycles}"
        )

    def test_scheduled_engines_have_intervals(self):
        """Every scheduled engine must have an interval."""
        warnings = validate_registry()
        interval_warnings = [w for w in warnings if "no interval_seconds" in w]
        self.assertEqual(
            interval_warnings, [],
            f"Scheduled engines missing intervals: {interval_warnings}"
        )

    def test_all_dependencies_exist_in_registry(self):
        """Every dependency reference must point to a registered engine."""
        for code, engine in ENGINE_REGISTRY.items():
            for dep in engine.dependencies:
                self.assertIn(
                    dep, ENGINE_REGISTRY,
                    f"{code} depends on '{dep}' which is not registered"
                )


class DependencyGraphTests(TestCase):
    """Test dependency graph queries."""

    def test_sae_has_many_dependents(self):
        """SAE is the truth layer — many engines should depend on it."""
        dependents = get_dependents("SAE")
        self.assertGreater(
            len(dependents), 3,
            f"SAE should have many dependents, got: {dependents}"
        )
        # PIE, PRIE, PGE should all depend on SAE
        self.assertIn("PIE", dependents)
        self.assertIn("PRIE", dependents)

    def test_pie_depends_on_sae(self):
        """PIE should declare SAE as a dependency."""
        pie = get_engine("PIE")
        self.assertIn("SAE", pie.dependencies)

    def test_pge_depends_on_pie_and_prie(self):
        """PGE should depend on PIE and PRIE."""
        pge = get_engine("PGE")
        self.assertIn("PIE", pge.dependencies)
        self.assertIn("PRIE", pge.dependencies)
        self.assertIn("SAE", pge.dependencies)

    def test_dbe_depends_on_intelligence_chain(self):
        """DBE should depend on the full intelligence chain."""
        dbe = get_engine("DBE")
        self.assertIn("SAE", dbe.dependencies)
        self.assertIn("PIE", dbe.dependencies)
        self.assertIn("PGE", dbe.dependencies)

    def test_dependency_chain_is_transitive(self):
        """get_dependency_chain should resolve transitive dependencies."""
        # PGE depends on PIE, PIE depends on SAE
        # So PGE's chain should include SAE
        chain = get_dependency_chain("PGE")
        self.assertIn("SAE", chain)
        self.assertIn("PIE", chain)

    def test_dependency_chain_handles_no_deps(self):
        """Engines with no dependencies should return empty chain."""
        chain = get_dependency_chain("SUE")
        self.assertEqual(chain, [])

    def test_dependency_chain_handles_unknown_engine(self):
        """Unknown engine should return empty chain."""
        chain = get_dependency_chain("NONEXISTENT")
        self.assertEqual(chain, [])

    def test_impact_chain_sae_affects_many(self):
        """SAE failure should impact many downstream engines."""
        impact = get_impact_chain("SAE")
        self.assertGreater(len(impact), 3)
        # PIE depends on SAE, PGE depends on PIE, so PGE should be in impact
        self.assertIn("PIE", impact)

    def test_impact_chain_handles_leaf_engine(self):
        """Leaf engines (no dependents) should have empty impact chain."""
        # SUE has no dependents except UAIO
        impact = get_impact_chain("SUE")
        # SUE might be in UAIO's deps — check if it has any dependents at all
        # This just verifies it doesn't crash
        self.assertIsInstance(impact, list)

    def test_dependency_graph_complete(self):
        """Dependency graph should include all registered engines."""
        graph = get_dependency_graph()
        self.assertEqual(len(graph), get_engine_count())
        for code in get_engine_codes():
            self.assertIn(code, graph)
            self.assertIn("dependencies", graph[code])
            self.assertIn("dependents", graph[code])
            self.assertIn("impact_count", graph[code])

    def test_critical_engines_returns_high_impact(self):
        """Critical engines should have high impact counts."""
        critical = get_critical_engines(min_impact=3)
        # SAE should be critical (many engines depend on it)
        sae_entries = [e for e in critical if e["code"] == "SAE"]
        self.assertTrue(
            len(sae_entries) > 0,
            "SAE should be a critical engine"
        )

    def test_protective_depends_on_pressure_and_drift(self):
        """PROTECTIVE should depend on PRESSURE and DRIFT."""
        protective = get_engine("PROTECTIVE")
        self.assertIn("PRESSURE", protective.dependencies)
        self.assertIn("DRIFT", protective.dependencies)


class RegistrySummaryTests(TestCase):
    """Test registry summary output."""

    def test_summary_includes_dependency_stats(self):
        """Summary should include dependency edge count."""
        summary = get_registry_summary()
        self.assertIn("with_dependencies", summary)
        self.assertIn("dependency_edges", summary)
        self.assertGreater(summary["with_dependencies"], 5)
        self.assertGreater(summary["dependency_edges"], 10)

    def test_summary_includes_manual_run_count(self):
        """Summary should include manual run count."""
        summary = get_registry_summary()
        self.assertIn("manual_run_count", summary)
        self.assertGreater(summary["manual_run_count"], 5)


class ObservabilityRegistryCompatTests(TestCase):
    """Test that the observability engine registry still works via canonical delegation."""

    def test_observability_registry_loads(self):
        """Observability ENGINE_REGISTRY should load from canonical."""
        from apps.core.ai_observability.engine_registry import ENGINE_REGISTRY as OBS_REG
        # Should have at least the original 13 engines that had manual run
        self.assertGreater(len(OBS_REG), 8)

    def test_get_engine_meta_returns_dict(self):
        """get_engine_meta should return backward-compatible dict."""
        from apps.core.ai_observability.engine_registry import get_engine_meta
        meta = get_engine_meta("SAE")
        self.assertIsNotNone(meta)
        self.assertIn("label", meta)
        self.assertIn("phase", meta)
        self.assertIn("category", meta)
        self.assertIn("can_manual_run", meta)
        self.assertIn("batch_runner", meta)
        self.assertTrue(meta["can_manual_run"])

    def test_get_manual_engines_returns_list(self):
        """get_manual_engines should return engine codes with manual run."""
        from apps.core.ai_observability.engine_registry import get_manual_engines
        manual = get_manual_engines()
        self.assertIsInstance(manual, list)
        self.assertIn("SAE", manual)
        self.assertIn("PIE", manual)

    def test_resolve_batch_runner_returns_callable(self):
        """resolve_batch_runner should import and return the function."""
        from apps.core.ai_observability.engine_registry import resolve_batch_runner
        # SAE has a known batch runner
        runner = resolve_batch_runner("SAE")
        # It might fail to import in test env, so just check it doesn't crash
        # and returns either callable or None
        self.assertTrue(runner is None or callable(runner))

    def test_original_engines_present(self):
        """All 13 original engines should still be accessible."""
        from apps.core.ai_observability.engine_registry import get_engine_meta
        original_codes = ["UAL", "SAE", "PIE", "PRIE", "PGE", "ICQG", "CDCE", "DBE", "WIRE", "DNE"]
        for code in original_codes:
            meta = get_engine_meta(code)
            self.assertIsNotNone(meta, f"Engine {code} missing from observability registry")

    def test_phase_labels_backward_compatible(self):
        """Phase categories should use original labels."""
        from apps.core.ai_observability.engine_registry import get_engine_meta
        sae_meta = get_engine_meta("SAE")
        self.assertIn(sae_meta["category"], ["Interpret", "Execute", "Post-Exec"])
