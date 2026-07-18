"""Unit tests for the Truth Validation deterministic comparison engine.

The engine flattens a WLJ truth object into typed scalar values and compares each against
the structured values present in a Chief-of-Staff response — PRESENT / MISSING / MISMATCH /
N/A. It is 100% deterministic (no model). These tests pin that behaviour: numeric tolerance
+ unit normalization, date rendering, text containment, forbidden-value contamination, and
object grading. WLJ is always the authority.
"""
import datetime as dt

from django.test import SimpleTestCase

from apps.core.truth.validation.comparison import (
    Check, ExpectedValue, compare_object, flatten_entity, grade_checks,
)
from apps.core.truth.validation.surface import parse_surface


class FlattenTests(SimpleTestCase):
    def test_flatten_picks_scalars_and_inherits_unit(self):
        entity = {
            "kind": "weight", "identity": "Latest weigh-in",
            "standing": {"value": 185.2, "unit": "lb"},
            "definition": {"note": "morning after run"},
            "freshness": "current", "confidence": "high",   # skipped
        }
        evs = {e.label: e for e in flatten_entity(entity)}
        # metadata keys are skipped
        self.assertNotIn("freshness", evs)
        self.assertNotIn("confidence", evs)
        # numeric value carries the sibling unit
        self.assertIn("value", evs)
        self.assertEqual(evs["value"].kind, "numeric")
        self.assertEqual(evs["value"].unit, "lb")
        # identity text is captured
        self.assertEqual(evs["identity"].kind, "text")

    def test_flatten_skips_booleans_and_collections(self):
        entity = {"identity": "x", "standing": {"is_favorite": True,
                                                 "tags": ["a", "b"], "count": 3}}
        kinds = {e.label: e.kind for e in flatten_entity(entity)}
        self.assertNotIn("is_favorite", kinds)   # bool skipped
        self.assertNotIn("tags", kinds)           # list skipped
        self.assertEqual(kinds.get("count"), "numeric")

    def test_flatten_dedupes_same_value(self):
        # same fact (value+unit) in two dimensions -> one check
        entity = {"identity": "Latest weigh-in",
                  "standing": {"weight": 185, "unit": "lb"},
                  "performance": {"latest": 185, "unit": "lb"}}
        evs = [e for e in flatten_entity(entity) if e.kind == "numeric"]
        vals = [e.value for e in evs]
        self.assertEqual(vals.count(185.0), 1)

    def test_date_string_detected(self):
        entity = {"identity": "session", "status": "2026-07-17"}
        evs = {e.label: e for e in flatten_entity(entity)}
        self.assertEqual(evs["status"].kind, "date")
        self.assertEqual(evs["status"].value, dt.date(2026, 7, 17))


class NumericMatchTests(SimpleTestCase):
    def _check(self, value, unit, response):
        ev = ExpectedValue("standing.weight", "weight", value, "numeric", unit)
        return compare_object([ev], response)[0]

    def test_present_exact(self):
        self.assertEqual(self._check(185, "lb", "You weigh 185 lb.").status, "present")

    def test_present_within_rounding_tolerance(self):
        # 185.2 expected, answer says "185 lbs" -> within 1% tolerance
        self.assertEqual(self._check(185.2, "lb", "About 185 lbs this morning.").status,
                         "present")

    def test_missing_when_absent(self):
        self.assertEqual(self._check(185, "lb", "I don't have that yet.").status, "missing")

    def test_mismatch_same_unit_different_value(self):
        # answer asserts a DIFFERENT same-unit value -> contradiction
        c = self._check(185, "lb", "You weigh 172 lb.")
        self.assertEqual(c.status, "mismatch")

    def test_thousands_separator(self):
        c = self._check(8432, "steps", "You took 8,432 steps.")
        self.assertEqual(c.status, "present")

    def test_glucose_unit_normalization_alias(self):
        # calories alias: kcal expected, answer says "calories"
        ev = ExpectedValue("s.cal", "calories", 640, "numeric", "kcal")
        c = compare_object([ev], "That meal was 640 calories.")[0]
        self.assertEqual(c.status, "present")


class DateMatchTests(SimpleTestCase):
    def _check(self, value, response, today=None):
        ev = ExpectedValue("status", "date", value, "date")
        return compare_object([ev], response, today=today)[0]

    def test_iso(self):
        self.assertEqual(self._check(dt.date(2026, 7, 17),
                                     "Recorded 2026-07-17.").status, "present")

    def test_month_day(self):
        self.assertEqual(self._check(dt.date(2026, 7, 17),
                                     "That was on July 17.").status, "present")

    def test_relative_yesterday(self):
        today = dt.date(2026, 7, 18)
        self.assertEqual(self._check(dt.date(2026, 7, 17),
                                     "You logged that yesterday.", today).status, "present")

    def test_missing(self):
        self.assertEqual(self._check(dt.date(2026, 7, 17),
                                     "No date available.").status, "missing")


class TextAndForbiddenTests(SimpleTestCase):
    def test_text_present(self):
        ev = ExpectedValue("definition.source", "source", "Apple Health", "text")
        self.assertEqual(compare_object([ev], "Synced from Apple Health.")[0].status,
                         "present")

    def test_text_multiword_tokens(self):
        ev = ExpectedValue("id", "note", "morning after run", "text")
        # tokens present out of order
        self.assertEqual(compare_object([ev], "Note: after your morning run.")[0].status,
                         "present")

    def test_forbidden_contamination_flagged(self):
        checks = compare_object([], "Your blood pressure was 120/80.",
                                forbidden=["blood pressure reading"])
        forb = [c for c in checks if c.is_forbidden][0]
        self.assertTrue(forb.is_forbidden)
        self.assertEqual(forb.status, "mismatch")   # contamination present

    def test_forbidden_absent_is_clean(self):
        checks = compare_object([], "Here is your journal entry.",
                                forbidden=["blood pressure reading"])
        self.assertEqual([c for c in checks if c.is_forbidden][0].status, "present")


class GradeTests(SimpleTestCase):
    def test_all_present_passes(self):
        checks = [Check("a", "p", "text", "", "x", "x", "present"),
                  Check("b", "p", "text", "", "y", "y", "present")]
        g = grade_checks(checks)
        self.assertTrue(g.passed)
        self.assertEqual((g.present, g.total), (2, 2))

    def test_missing_fails(self):
        checks = [Check("a", "p", "text", "", "x", "", "missing")]
        self.assertFalse(grade_checks(checks).passed)

    def test_mismatch_fails(self):
        checks = [Check("a", "p", "numeric", "lb", "185", "172", "mismatch")]
        self.assertFalse(grade_checks(checks).passed)

    def test_forbidden_hit_fails_even_if_others_present(self):
        checks = [Check("a", "p", "text", "", "x", "x", "present"),
                  Check("bp", "must_not_surface", "forbidden", "", "", "hit",
                        "mismatch", is_forbidden=True)]
        g = grade_checks(checks)
        self.assertFalse(g.passed)
        self.assertEqual(g.forbidden_hits, 1)

    def test_empty_is_na_not_pass(self):
        g = grade_checks([])
        self.assertTrue(g.is_na)
        self.assertFalse(g.passed)


class ObjectResolutionTests(SimpleTestCase):
    """The validator must select the SAME object the app considers current/active/latest —
    never a silent describe()[0]. (Regression: 'current Bible study' resolved the most
    recently STARTED plan instead of the plan_status='active' plan.)"""

    def _patch_entity(self, entities):
        from unittest import mock
        env = {"status": "ready", "entities": entities}
        return mock.patch("apps.ai.cos_services.domain_entity.get_domain_entity",
                          return_value=env)

    def test_active_rule_picks_active_not_first(self):
        from apps.core.truth.validation.surface import resolve_expected_object
        # provider order (newest-started first) puts the COMPLETED plan first
        entities = [
            {"kind": "reading_plan", "identity": "Journey Through Matthew", "status": "completed"},
            {"kind": "reading_plan", "identity": "Walking With God Through Scripture", "status": "active"},
        ]
        prompt = {"domain": "faith", "surface": "faith.entity(reading_plan)",
                  "selection": {"rule": "active", "status": "active"}}
        with self._patch_entity(entities):
            obj = resolve_expected_object(None, prompt)
        self.assertTrue(obj.present)
        self.assertEqual(obj.resolved_identity, "Walking With God Through Scripture")
        self.assertEqual(obj.object_status, "active")
        self.assertIn("active", obj.selection_rule.lower())

    def test_latest_rule_picks_first(self):
        from apps.core.truth.validation.surface import resolve_expected_object
        entities = [{"kind": "prayer", "identity": "Newest", "status": "unanswered"},
                    {"kind": "prayer", "identity": "Older", "status": "unanswered"}]
        prompt = {"domain": "faith", "surface": "faith.entity(prayer)",
                  "selection": {"rule": "latest"}}
        with self._patch_entity(entities):
            obj = resolve_expected_object(None, prompt)
        self.assertEqual(obj.resolved_identity, "Newest")

    def test_active_with_no_active_record_is_absent(self):
        from apps.core.truth.validation.surface import resolve_expected_object
        entities = [{"kind": "reading_plan", "identity": "Done", "status": "completed"}]
        prompt = {"domain": "faith", "surface": "faith.entity(reading_plan)",
                  "selection": {"rule": "active", "status": "active"}}
        with self._patch_entity(entities):
            obj = resolve_expected_object(None, prompt)
        self.assertFalse(obj.present)
        self.assertIn("active", obj.reason.lower())

    def test_resolution_card_is_populated(self):
        from apps.core.truth.validation.surface import resolve_expected_object
        entities = [{"kind": "reading_plan", "identity": "Walking", "status": "active"}]
        prompt = {"domain": "faith", "surface": "faith.entity(reading_plan)",
                  "selection": {"rule": "active", "status": "active"}}
        with self._patch_entity(entities):
            card = resolve_expected_object(None, prompt).resolution()
        self.assertEqual(card["resolved_object"], "Walking")
        self.assertEqual(card["provider"], "faith.entity(reading_plan)")
        self.assertTrue(card["resolved_from"].startswith("Faith"))


class SurfaceParseTests(SimpleTestCase):
    def test_entity_type(self):
        p = parse_surface("health.entity(weight)")
        self.assertEqual((p["domain"], p["entity_type"], p["name"]),
                         ("health", "weight", None))

    def test_entity_one_quoted(self):
        p = parse_surface("medicine.entity_one('Metformin')")
        self.assertEqual((p["domain"], p["name"]), ("medicine", "Metformin"))

    def test_entity_one_bareword(self):
        p = parse_surface("journal.entity_one(yesterday)")
        self.assertEqual(p["name"], "yesterday")

    def test_compound_prefers_entity(self):
        p = parse_surface("calendar.current(next_event) / entity(event)")
        self.assertEqual(p["entity_type"], "event")
        self.assertTrue(p["wants_current"])

    def test_current_only(self):
        p = parse_surface("relationships.current(most_connected)")
        self.assertEqual(p["entity_type"], None)
        self.assertTrue(p["wants_current"])
