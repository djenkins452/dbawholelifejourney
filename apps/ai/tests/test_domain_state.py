# ==============================================================================
# File: apps/ai/tests/test_domain_state.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for the ChatGPT CoS DomainStateService (Phase 2)
# ==============================================================================
"""
DomainStateService tests.

Verifies the generic canonical domain-state read surface:
* delegates to get_module_state (no domain-specific readers, no re-aggregation);
* STATE-FIRST: read-only on the request path (allow_rebuild=False), pending on a
  cold snapshot; allow_build permits a rebuild;
* honest handling of unknown domains and no-SAE-state domains (no fabrication);
* JSON-safe + deterministic + observable.
"""

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services import (
    DOMAIN_REGISTRY,
    get_domain_state,
    supported_domains,
)

User = get_user_model()

_GMS = "apps.core.ai_state.state_engine.get_module_state"

# The 13 Phase 2 target domains must all be supported.
_TARGET_DOMAINS = [
    "health", "medical", "faith", "purpose", "life", "journal",
    "relationships", "finance", "meals", "calendar", "capture",
    "sports", "notes",
]


class DomainStateServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="domainstate@example.com", password="x"
        )

    # --- registry / supported domains ------------------------------------
    def test_all_target_domains_supported(self):
        supported = supported_domains()
        for d in _TARGET_DOMAINS:
            self.assertIn(d, supported, f"{d} must be a supported domain")

    def test_registry_is_exposure_alias_only(self):
        # life -> tasks, purpose -> goals (exposure aliases; SAE map untouched)
        self.assertEqual(DOMAIN_REGISTRY["life"], "tasks")
        self.assertEqual(DOMAIN_REGISTRY["purpose"], "goals")
        self.assertIsNone(DOMAIN_REGISTRY["notes"])

    # --- valid domain, ready ---------------------------------------------
    def test_valid_domain_ready_delegates_to_get_module_state(self):
        fake_state = {"weight_current": 286.6, "sleep_status": "ok"}
        with mock.patch(_GMS, return_value=fake_state) as gms:
            result = get_domain_state(self.user, "health")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["domain"], "health")
        self.assertEqual(result["module"], "health")
        self.assertEqual(result["state"], fake_state)
        self.assertEqual(result["_meta"]["field_count"], 2)
        # delegated read-only (allow_rebuild=False by default)
        gms.assert_called_once()
        self.assertEqual(gms.call_args.kwargs.get("allow_rebuild"), False)

    def test_exposure_alias_maps_to_canonical_module(self):
        with mock.patch(_GMS, return_value={"x": 1}) as gms:
            get_domain_state(self.user, "life")
        # life is read from the canonical 'tasks' SAE module
        self.assertEqual(gms.call_args.args[1], "tasks")

    # --- state-first: cache/pending behavior -----------------------------
    def test_cold_snapshot_is_pending_not_rebuilt(self):
        with mock.patch(_GMS, return_value={}) as gms:
            result = get_domain_state(self.user, "faith")  # allow_build False
        self.assertEqual(result["status"], "pending")
        self.assertIsNone(result["state"])
        self.assertEqual(gms.call_args.kwargs.get("allow_rebuild"), False)

    def test_allow_build_permits_rebuild(self):
        with mock.patch(_GMS, return_value={"prayer": 1}) as gms:
            result = get_domain_state(self.user, "faith", allow_build=True)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(gms.call_args.kwargs.get("allow_rebuild"), True)
        self.assertEqual(result["_meta"]["source"], "rebuild_allowed")

    def test_allow_build_empty_is_ready_empty(self):
        with mock.patch(_GMS, return_value={}):
            result = get_domain_state(self.user, "sports", allow_build=True)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["state"], {})
        self.assertEqual(result["_meta"]["field_count"], 0)

    # --- honest handling: no fabrication ---------------------------------
    def test_unsupported_domain(self):
        result = get_domain_state(self.user, "telepathy")
        self.assertEqual(result["status"], "unsupported_domain")
        self.assertIn("supported_domains", result)
        self.assertNotIn("state", result)

    def test_notes_has_no_sae_state_source(self):
        # notes is a known domain but has NO SAE state — must not fabricate one
        with mock.patch(_GMS) as gms:
            result = get_domain_state(self.user, "notes")
        self.assertEqual(result["status"], "no_state_source")
        gms.assert_not_called()  # never even hits SAE
        self.assertNotIn("state", result)

    def test_read_error_is_surfaced_not_swallowed(self):
        with mock.patch(_GMS, side_effect=RuntimeError("boom")):
            result = get_domain_state(self.user, "health")
        self.assertEqual(result["status"], "error")
        self.assertNotIn("state", result)

    def test_domain_is_case_insensitive(self):
        with mock.patch(_GMS, return_value={"x": 1}):
            result = get_domain_state(self.user, "  HEALTH ")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["domain"], "health")

    # --- output contract --------------------------------------------------
    def test_output_is_json_serializable_all_statuses(self):
        # ready
        with mock.patch(_GMS, return_value={"a": 1}):
            json.dumps(get_domain_state(self.user, "health"))
        # pending
        with mock.patch(_GMS, return_value={}):
            json.dumps(get_domain_state(self.user, "health"))
        # no_state_source
        json.dumps(get_domain_state(self.user, "notes"))
        # unsupported
        json.dumps(get_domain_state(self.user, "nope"))

    def test_jsonsafe_coerces_nonserializable_state(self):
        import datetime

        class Weird:
            def __repr__(self):
                return "weird"

        state = {"when": datetime.date(2026, 6, 24), "obj": Weird()}
        with mock.patch(_GMS, return_value=state):
            result = get_domain_state(self.user, "journal")
        json.dumps(result)  # must not raise
        self.assertEqual(result["state"]["when"], "2026-06-24")
