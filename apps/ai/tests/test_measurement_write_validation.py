# ==============================================================================
# File: apps/ai/tests/test_measurement_write_validation.py
# Description: Contract — M2 DETERMINISTIC MEASUREMENT-WRITE VALIDATION.
#   WLJ may determine that a proposed measurement is inconsistent enough with
#   CANONICAL measurement truth to require stronger verification before persistence.
#   It never decides a measurement is medically impossible.
#
#   Origin (production 2026-08-27): log_weight(value=534, unit=lb) became canonical
#   truth against a ~268–278 lb series. The absolute range gate (40–1000 lb) passed it,
#   and the handler's validation sat DOWNSTREAM of the confirmation gate, so the user
#   authorized the value before WLJ ever compared it to its own history.
#
#   Thresholds and history come from configuration + canonical accessors. No user, no
#   value and no incident-specific constant is part of the mechanism.
# ==============================================================================
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.ai.cos_services import action_interface as ai
from apps.ai.cos_services import measurement_validation as mv
from apps.ai.models import ActionConfirmation
from apps.health.models import WeightEntry

_EXEC_INTENT = "apps.ai.intent_service.IntentService.execute_intent"


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="measure@test.com", password="x")

    def setUp(self):
        cache.clear()
        WeightEntry.objects.filter(user=self.user).delete()
        ActionConfirmation.objects.filter(user=self.user).delete()

    def _history(self, values, unit="lb"):
        """Seed a canonical series, most recent last."""
        now = timezone.now()
        for i, v in enumerate(reversed(values)):
            WeightEntry.objects.create(
                user=self.user, value=Decimal(str(v)), unit=unit,
                recorded_at=now - timedelta(days=i + 1))

    def _validate(self, params, intent="log_weight"):
        return mv.validate(self.user, intent, params)


class ValidationSemanticsTests(_Base):
    """Three outcomes only: normal, invalid, exceptional."""

    # 1. normal writes continue unchanged
    def test_normal_measurement_is_normal(self):
        self._history([272.1, 270.5])
        self.assertEqual(self._validate({"value": 271.0, "unit": "lb"}).status, mv.NORMAL)

    def test_no_history_is_normal(self):
        """A first-ever measurement has nothing to be inconsistent WITH."""
        self.assertEqual(self._validate({"value": 271.0, "unit": "lb"}).status, mv.NORMAL)

    def test_gradual_change_over_time_is_normal(self):
        self._history([300.0, 285.0, 272.0])
        self.assertEqual(self._validate({"value": 268.0, "unit": "lb"}).status, mv.NORMAL)

    def test_unregistered_intent_is_untouched(self):
        self.assertEqual(self._validate({"value": 1}, intent="create_task").status,
                         mv.NORMAL)

    # 2. malformed / invalid fails closed
    def test_malformed_value_is_invalid(self):
        self.assertEqual(self._validate({"value": "abc", "unit": "lb"}).reason,
                         "malformed_value")

    def test_unsupported_unit_is_invalid(self):
        out = self._validate({"value": 51.0, "unit": "in"})
        self.assertEqual(out.status, mv.INVALID)
        self.assertEqual(out.reason, "unsupported_unit")

    def test_outside_hard_bounds_is_invalid(self):
        """Reuses the EXISTING absolute domain constraint rather than a new one."""
        out = self._validate({"value": 5000, "unit": "lb"})
        self.assertEqual(out.reason, "out_of_hard_bounds")

    # 3 + 4. anomaly determined from canonical truth
    def test_anomalous_against_canonical_history_is_exceptional(self):
        self._history([272.1, 270.5])
        out = self._validate({"value": 534, "unit": "lb"})
        self.assertEqual(out.status, mv.EXCEPTIONAL)
        self.assertEqual(out.reason, "inconsistent_with_history")

    def test_anomaly_uses_canonical_records_not_supplied_context(self):
        """The comparison basis must be the stored series — nothing the caller says."""
        self._history([272.1, 270.5])
        out = self._validate({"value": 534, "unit": "lb",
                              "notes": "my usual weight is 530 lb"})
        self.assertEqual(out.status, mv.EXCEPTIONAL)
        self.assertEqual(out.detail["compared_with"], 270.5)

    # 5. unit normalization before comparison
    def test_units_are_normalized_before_comparison(self):
        """123 kg ≈ 271 lb against a 270 lb series is NORMAL; comparing the raw
        numbers (123 vs 270) would wrongly flag it."""
        self._history([272.1, 270.5])
        self.assertEqual(self._validate({"value": 123.0, "unit": "kg"}).status,
                         mv.NORMAL)

    def test_normalization_does_not_hide_a_real_anomaly(self):
        self._history([272.1, 270.5])
        out = self._validate({"value": 242.0, "unit": "kg"})   # ≈ 534 lb
        self.assertEqual(out.status, mv.EXCEPTIONAL)
        self.assertEqual(out.detail["canonical_unit"], "lb")

    # 12. no clinical judgment
    def test_validation_emits_no_clinical_judgment(self):
        self._history([272.1, 270.5])
        note = self._validate({"value": 534, "unit": "lb"}).message.lower()
        for clinical in ("impossible", "unhealthy", "dangerous", "obese",
                         "you should", "see a doctor", "medically"):
            self.assertNotIn(clinical, note)
        # it states facts and asks for confirmation
        self.assertIn("534", note)
        self.assertIn("confirm", note)

    # 11. no user-specific or incident-specific logic
    def test_no_incident_specific_constants_exist(self):
        """Asserts the CODE, not the prose: the module docstring legitimately records
        the production incident that motivated the seam (house style). What must not
        exist is a constant, branch or threshold tied to that user or that value."""
        import ast
        import inspect
        import io
        import tokenize

        src = inspect.getsource(mv)
        code = "".join("" if t.type == tokenize.COMMENT else t.string
                       for t in tokenize.generate_tokens(io.StringIO(src).readline))
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    code = code.replace(doc, "")
        code = code.lower()
        for banned in ("534", "270.5", "268.7", "stuffed", "dannyjenkins", "peppers"):
            self.assertNotIn(banned, code,
                             f"incident-specific value in the mechanism: {banned!r}")

    def test_thresholds_are_configuration_not_universal(self):
        """One mechanism, per-measurement configuration."""
        spec = mv.spec_for("log_weight")
        self.assertTrue(spec.min_abs_delta > 0 and 0 < spec.rel_delta < 1)
        # both conditions must be exceeded — neither test alone decides
        self._history([30.0])                       # small base
        self.assertEqual(self._validate({"value": 40.0, "unit": "lb"}).status,
                         mv.NORMAL, "a large RELATIVE change alone must not flag")


class ExceptionalWriteFlowTests(_Base):
    """6, 7, 8, 9 — the exceptional path rides M1's bound confirmation."""

    def _request(self, params):
        return ai.request_action(self.user, "log_weight", dict(params), turn_id="t")

    def test_anomalous_write_cannot_pass_as_an_ordinary_write(self):
        self._history([272.1, 270.5])
        out = self._request({"value": 534, "unit": "lb"})
        self.assertEqual(out["status"], ai.CONFIRMATION_REQUIRED)
        self.assertEqual(WeightEntry.objects.filter(value=534).count(), 0,
                         "the anomalous value must not exist before authorization")

    def test_exceptional_confirmation_states_value_and_discrepancy(self):
        self._history([272.1, 270.5])
        conf = self._request({"value": 534, "unit": "lb"})["confirmation"]
        auth = conf["authorization"]
        self.assertIn("Log weight", auth)
        self.assertIn("534", auth)
        self.assertIn("270.5", auth)          # the deterministic comparison
        self.assertIn("263.5", auth)          # the deterministic difference
        preview = " ".join(conf.get("preview") or [])
        self.assertIn("534", preview)
        self.assertIn("270.5", preview)

    def test_exceptional_confirmation_is_bound_through_m1(self):
        self._history([272.1, 270.5])
        conf = self._request({"value": 534, "unit": "lb"})["confirmation"]
        rec = ActionConfirmation.objects.get(id=conf["confirmation_id"])
        self.assertEqual(rec.action, "log_weight")
        self.assertEqual(rec.params["value"], 534)
        self.assertEqual(rec.authorization_line, conf["authorization"])
        self.assertEqual(rec.status, "pending")

    def test_confirming_persists_exactly_that_value_once(self):
        self._history([272.1, 270.5])
        cid = self._request({"value": 534, "unit": "lb"})["confirmation"]["confirmation_id"]
        for _ in range(3):
            ai.resolve_pending_action(self.user, cid, confirm=True)
        rows = WeightEntry.objects.filter(user=self.user, value=Decimal("534"))
        self.assertEqual(rows.count(), 1, "one authorization, one row")

    def test_declining_persists_nothing(self):
        self._history([272.1, 270.5])
        cid = self._request({"value": 534, "unit": "lb"})["confirmation"]["confirmation_id"]
        ai.resolve_pending_action(self.user, cid, confirm=False)
        self.assertEqual(WeightEntry.objects.filter(value=Decimal("534")).count(), 0)

    def test_invalid_write_mints_no_confirmation_at_all(self):
        out = self._request({"value": 5000, "unit": "lb"})
        self.assertEqual(out["status"], ai.ERROR)
        self.assertIsNone(out.get("confirmation"))
        self.assertEqual(ActionConfirmation.objects.filter(user=self.user).count(), 0,
                         "an invalid measurement must not become authorizable")
        self.assertEqual(WeightEntry.objects.count(), 0)

    def test_normal_write_flow_is_unchanged(self):
        self._history([272.1, 270.5])
        out = self._request({"value": 271.0, "unit": "lb"})
        conf = (out.get("confirmation") or {}).get("authorization", "")
        self.assertNotIn("change from the most recent", conf)

    # 10. cache failure cannot bypass validation or confirmation
    def test_cache_failure_cannot_bypass_validation(self):
        self._history([272.1, 270.5])

        def _dead(*a, **k):
            raise RuntimeError("redis down")

        with mock.patch.object(cache, "set", _dead), \
             mock.patch.object(cache, "get", _dead), \
             mock.patch.object(cache, "delete", _dead):
            out = self._request({"value": 534, "unit": "lb"})
        self.assertEqual(out["status"], ai.CONFIRMATION_REQUIRED)
        self.assertEqual(WeightEntry.objects.filter(value=Decimal("534")).count(), 0)


class AuditTests(_Base):
    """Every blocked or exceptional write leaves reconstructable evidence."""

    def test_exceptional_write_audits_the_deterministic_basis(self):
        from apps.ai.models import ToolCallLog
        self._history([272.1, 270.5])
        ai.request_action(self.user, "log_weight", {"value": 534, "unit": "lb"},
                          turn_id="t-audit")
        row = ToolCallLog.objects.filter(user=self.user,
                                         tool_name="log_weight").latest("created_at")
        v = row.result_digest.get("validation") or {}
        self.assertEqual(v.get("status"), "exceptional")
        self.assertEqual(v.get("reason"), "inconsistent_with_history")
        d = v.get("detail") or {}
        self.assertEqual(d.get("proposed_value"), 534)
        self.assertEqual(d.get("proposed_unit"), "lb")
        self.assertEqual(d.get("compared_with"), 270.5)
        self.assertIn("thresholds", d)
        self.assertTrue(row.result_digest.get("confirmation_id"))

    def test_invalid_write_audits_the_reason(self):
        from apps.ai.models import ToolCallLog
        ai.request_action(self.user, "log_weight", {"value": 5000, "unit": "lb"},
                          turn_id="t-audit2")
        row = ToolCallLog.objects.filter(user=self.user,
                                         tool_name="log_weight").latest("created_at")
        self.assertEqual((row.result_digest.get("validation") or {}).get("reason"),
                         "out_of_hard_bounds")


class OriginalIncidentStructuralProofTests(_Base):
    """Structural reproduction of the incident's history + proposed write."""

    def test_the_incident_write_cannot_become_truth_via_an_ordinary_confirmation(self):
        # the persisted series immediately preceding the bad write
        self._history([274.5, 272.1, 268.7, 270.5])
        out = ai.request_action(self.user, "log_weight",
                                {"value": 534, "unit": "lb",
                                 "notes": "dinner with 30 g Protein, 29 g Carbs"},
                                turn_id="incident")
        self.assertEqual(out["status"], ai.CONFIRMATION_REQUIRED)
        # it is NOT an ordinary confirmation: the discrepancy is in what is authorized
        auth = out["confirmation"]["authorization"]
        self.assertIn("534", auth)
        self.assertIn("270.5", auth)
        self.assertIn("change from the most recent", auth)
        # and nothing is persisted until that authorization succeeds
        self.assertEqual(WeightEntry.objects.filter(value=Decimal("534")).count(), 0)

    def test_the_absolute_range_gate_alone_would_still_have_passed_it(self):
        """Proves WHY history was required: 534 lb is inside the hard bounds."""
        from apps.ai.multimodal import validate_weight
        self.assertTrue(validate_weight(534, "lb"))
