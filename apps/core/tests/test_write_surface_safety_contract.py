# ==============================================================================
# File: apps/core/tests/test_write_surface_safety_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Certified CoS write surface — Action Safety Baseline
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-19
# ==============================================================================
"""Write-Surface Safety Contract.

DURABLE LESSON (2026-08-18/19 action-integrity incident):

    A model-facing capability is not certified merely because it exists, routes, and
    passes functional tests. Whenever its scope or runtime path expands, its assumptions
    about target identity, authorization, confirmation, reversibility, postcondition
    truth, mutable-state precedence, and auditability must be RE-CERTIFIED.

`complete_execution_item` was safe as a narrow guided-review verb ("the user already said
yes"). Generalizing it into THE completion verb silently invalidated that assumption and
produced, in sequence: a wrong-target mutation, a confirmation bypass, a false success, a
no-tool-call narration, and a cross-wired identity.

This file is the CI gate that stops the next capability entering the same way. Every
model-facing state-changing tool must appear in `WRITE_SURFACE` with an explicit policy
declaration — adding a write without declaring one FAILS.
"""

from pathlib import Path

from django.test import SimpleTestCase, TestCase

REPO = Path(__file__).resolve().parents[3]

# Policy vocabulary
CANONICAL = "canonical_domain_authority"
EXEMPT = "explicit_exemption"

# ── THE CERTIFIED WRITE SURFACE ───────────────────────────────────────────────
# Every model-facing tool that can change state. `confirmation` records how the
# confirmation authority applies; `exemption` documents why an invariant does not.
WRITE_SURFACE = {
    # --- DAY-1 named intents: all route request_action -> execute_action -> handler,
    #     so they inherit confirmation_required_for, ownership and audit uniformly.
    "mutate_task":            {"authority": CANONICAL, "confirmation": "policy"},
    "create_task":            {"authority": CANONICAL, "confirmation": "policy"},
    "complete_task":          {"authority": CANONICAL, "confirmation": "policy"},
    "log_weight":             {"authority": CANONICAL, "confirmation": "policy"},
    "log_body_measurements":  {"authority": CANONICAL, "confirmation": "policy"},
    "import_journal_entries": {"authority": CANONICAL, "confirmation": "policy"},
    "create_event":           {"authority": CANONICAL, "confirmation": "policy"},
    "add_reminder":           {"authority": CANONICAL, "confirmation": "policy"},
    "log_workout":            {"authority": CANONICAL, "confirmation": "policy"},
    "log_habit":              {"authority": CANONICAL, "confirmation": "policy"},
    "create_goal":            {"authority": CANONICAL, "confirmation": "policy"},
    "update_goal_progress":   {"authority": CANONICAL, "confirmation": "policy"},
    "log_prayer":             {"authority": CANONICAL, "confirmation": "policy"},
    "save_verse":             {"authority": CANONICAL, "confirmation": "policy"},
    "create_journal_entry":   {"authority": CANONICAL, "confirmation": "policy"},
    "add_gratitude":          {"authority": CANONICAL, "confirmation": "policy"},
    # Routes the SAME request_action -> execute_action -> handle_log_food pipeline as every
    # other named intent, so it inherits confirmation_required_for (the user's "confirm
    # before acting" preference), ownership scoping and audit uniformly. It was exposed to
    # the model without ever being declared here — the gate existed and this write walked
    # past it (found 2026-09-01).
    "log_food":               {"authority": CANONICAL, "confirmation": "policy"},

    # --- direct model-interface dispatches (do NOT pass through request_action) ---
    "complete_execution_item": {
        "authority": CANONICAL,        # Task.mark_complete / toggle_routine_completion / complete_dose
        "confirmation": "policy",      # consults confirmation_required_for, mints a bound confirmation
        "target_binding": "mandatory",  # requested_target required on the identity path
        "reversible": True,             # explicit undo=true, separate semantics
        "postcondition": "verified",
    },
    "delete_record": {
        # M4 exact-identity record correction. NOT a request_action intent — it is a direct
        # model-interface dispatch, which is precisely why it needed declaring: entering
        # through a newer path does not exempt a write from the safety contracts.
        "authority": CANONICAL,        # the domain's own soft_delete(), never a raw delete
        # STRICTER than "policy": it does not consult the user's preference at all, it
        # ALWAYS mints a bound confirmation showing the record's current deterministic
        # state. For a removal that is the right asymmetry — a write that can never
        # under-confirm cannot be talked past by a preference.
        "confirmation": "always",
        "target_binding": "mandatory",  # no exact identity -> FAIL CLOSED, nothing removed
        "reversible": True,             # soft_delete sets status='deleted' + deleted_at;
                                        # the row survives and remains restorable
        "postcondition": "verified",    # returns already_removed vs ok from canonical state
    },
    "resolve_pending_action": {
        "authority": EXEMPT, "confirmation": EXEMPT,
        "exemption": ("This tool IS the confirmation. Requiring confirmation of a "
                      "confirmation is circular; it executes only a previously bound, "
                      "single-use action and audits the outcome."),
    },
    "schedule_follow_up": {
        "authority": CANONICAL, "confirmation": EXEMPT,
        "exemption": ("Writes a ConversationFollowUp — a commitment the user just asked "
                      "for, not domain truth. Confirming it would re-ask the request "
                      "itself. Reversible by the user, audited, no domain mutation."),
    },
    "remember_about_user": {
        "authority": CANONICAL,        # apps.core.personal_knowledge.service (add/correct)
        "confirmation": EXEMPT,
        "target_binding": "n/a",       # new knowledge; a supersede targets a fact BY ID
        "reversible": True,            # every fact is editable/deletable in About Me
        "postcondition": "verified",   # the result reports exactly what was kept/updated
        "exemption": (
            "Personal memory, not domain truth. Confirming each remembered sentence would "
            "turn every conversation into a clerical queue and make the Chief of Staff "
            "worse than one that simply forgot — the failure this capability exists to "
            "end. Safety comes from elsewhere, and none of it is relaxed: it creates ONLY "
            "Personal Knowledge and never domain truth; every write goes through the "
            "canonical PK service with its domain-boundary validation, sensitivity policy "
            "and ownership scoping; a supersede uses the EXISTING M2 lineage so the old "
            "fact becomes history rather than being destroyed; the result reports honestly "
            "what was and was not kept; and About Me is the standing control surface where "
            "anything can be corrected or removed immediately, taking effect at once."),
    },
    "next_review_item": {
        "authority": CANONICAL, "confirmation": EXEMPT,
        "exemption": ("Advances the guided review and persists the pending question in "
                      "Conversation State — working state, not user domain truth. It "
                      "completes nothing; completion goes through complete_execution_item."),
    },
}

# Registered tools that change NOTHING. Listed so the audit is exhaustive.
NON_MUTATING = {"navigate_to_workspace"}


class WriteSurfaceInventoryTests(SimpleTestCase):
    """No model-facing write may exist without a declared safety policy."""

    def _registered(self):
        from apps.ai.model_interface.constitution import all_tools
        return {(t.get("function") or {}).get("name")
                for t in all_tools(writes_enabled=True)
                if (t.get("function") or {}).get("name")}

    def test_every_declared_write_is_actually_registered(self):
        registered = self._registered()
        missing = sorted(n for n in WRITE_SURFACE if n not in registered)
        self.assertEqual(missing, [], f"declared but not registered: {missing}")

    def test_no_undeclared_write_capability_is_registered(self):
        """THE GATE: a new write must consciously declare its safety policy."""
        from apps.ai.model_interface.constitution import ALLOWED_WRITE_INTENTS
        registered = self._registered()
        known = set(WRITE_SURFACE) | NON_MUTATING
        # Read-only truth tools are out of scope for this audit.
        unknown = sorted(n for n in registered
                         if n not in known and not n.startswith("get_")
                         and not n.startswith("search_"))
        self.assertEqual(unknown, [], (
            f"these model-facing tools are not declared in WRITE_SURFACE: {unknown}. "
            "If a tool can change state it must declare its canonical authority, "
            "confirmation policy, target binding, reversibility and postcondition "
            "semantics. If it cannot, add it to NON_MUTATING."))
        for intent in ALLOWED_WRITE_INTENTS:
            self.assertIn(intent, WRITE_SURFACE,
                          f"{intent} is an allowed write intent but is undeclared")

    def test_every_exemption_states_a_reason(self):
        for name, spec in WRITE_SURFACE.items():
            if EXEMPT in (spec.get("authority"), spec.get("confirmation")):
                with self.subTest(tool=name):
                    self.assertTrue((spec.get("exemption") or "").strip(),
                                    f"{name} claims an exemption with no governing reason")

    def test_no_probably_safe_classifications(self):
        for name, spec in WRITE_SURFACE.items():
            for key, val in spec.items():
                if isinstance(val, str):
                    self.assertNotIn("probably", val.lower(),
                                     f"{name}.{key} is not a certification")


class ConfirmationCoverageTests(TestCase):
    """Invariant 3 — every policy-governed write consults the ONE authority."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(
            email="ws@contract.test", password="x")

    def test_preference_on_requires_confirmation_for_every_policy_write(self):
        from apps.ai.cos_services.action_execution import confirmation_required_for
        prefs = self.user.preferences
        prefs.assistant_confirm_actions = True
        prefs.save()
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.get(pk=self.user.pk)
        for name, spec in WRITE_SURFACE.items():
            if spec.get("confirmation") != "policy":
                continue
            with self.subTest(tool=name):
                self.assertTrue(confirmation_required_for(user, name), (
                    f"{name} would execute without confirmation while the user's "
                    "'Ask me first' preference is ON"))

    def test_always_confirm_writes_really_do_confirm_unconditionally(self):
        """`always` is a STRONGER promise than `policy`, so prove it is kept.

        A write declared `always` must mint a bound confirmation with no preference check
        in front of it — otherwise the declaration overstates the protection.
        """
        src = (REPO / "apps/ai/model_interface/service.py").read_text(encoding="utf-8")
        for name, spec in WRITE_SURFACE.items():
            if spec.get("confirmation") != "always":
                continue
            marker = f'if name == "{name}":'
            self.assertIn(marker, src, f"{name} declares 'always' but is not dispatched here")
            block = src[src.index(marker):][:2500]
            with self.subTest(tool=name):
                self.assertIn("request_confirmation_for", block,
                              f"{name} declares 'always' but never mints a confirmation")
                self.assertNotIn("confirmation_required_for", block,
                                 f"{name} declares 'always' but gates on the preference — "
                                 "it is really 'policy', so declare that instead")

    def test_direct_dispatch_writes_consult_the_authority(self):
        """A direct Model Interface dispatch must not skip the confirmation spine."""
        src = (REPO / "apps/ai/model_interface/service.py").read_text(encoding="utf-8")
        for name, spec in WRITE_SURFACE.items():
            if spec.get("confirmation") != "policy" or name.startswith(("create_", "log_")):
                continue
            marker = f'if name == "{name}":'
            if marker not in src:
                continue          # routed through request_action, covered by policy
            block = src[src.index(marker):][:2500]
            with self.subTest(tool=name):
                self.assertIn("confirmation_required_for", block,
                              f"{name} is dispatched directly and never consults the "
                              "confirmation authority")


class AuditCoverageTests(SimpleTestCase):
    """Invariant 9 — every write leaves reconstructable evidence."""

    def test_every_direct_dispatch_records_a_tool_call(self):
        src = (REPO / "apps/ai/model_interface/service.py").read_text(encoding="utf-8")
        for name in ("complete_execution_item", "schedule_follow_up", "next_review_item",
                     "resolve_pending_action"):
            marker = f'if name == "{name}":'
            if marker not in src:
                continue
            block = src[src.index(marker):][:2500]
            with self.subTest(tool=name):
                self.assertTrue(
                    "record_tool_call" in block or "action_interface" in block,
                    f"{name} mutates without audit coverage")

    def test_confirmed_execution_path_is_audited(self):
        """The turn that ACTUALLY mutates must be logged, not just the confirmation.

        Regression: the confirmed-completion branch returned before the function's
        trailing record_tool_call, so production showed `confirmation_required` and a
        later `reversed` with the successful completion missing entirely.
        """
        src = (REPO / "apps/ai/cos_services/action_interface.py").read_text(encoding="utf-8")
        start = src.index('if action == "complete_execution_item":')
        block = src[start:start + 3200]
        self.assertIn("record_tool_call", block,
                      "the CONFIRMED execution path leaves no audit row")
        for field in ("source_id", "requested_target", "confirmation_id"):
            self.assertIn(field, block,
                          f"the confirmed-execution audit omits {field}")


class TargetBindingCoverageTests(TestCase):
    """Invariants 1 + 6 — binding is mandatory on BOTH completion and reversal."""

    def setUp(self):
        import datetime
        from django.contrib.auth import get_user_model
        from apps.life.models import Routine, RoutineSchedule
        self.user = get_user_model().objects.create_user(
            email="wsb@contract.test", password="x")
        self.today = datetime.date.today()
        r = Routine.objects.create(user=self.user, name="R", time_of_day="morning")
        self.a = RoutineSchedule.objects.create(
            routine=r, name="Item A", scheduled_time=datetime.time(7, 0),
            is_active=True, days_of_week="0,1,2,3,4,5,6")

    def test_completion_requires_a_stated_target(self):
        from apps.core.execution.execution_completion import complete_by_identity
        out = complete_by_identity(self.user, "routine_item", self.a.pk, self.today)
        self.assertEqual(out["status"], "target_unverified")

    def test_reversal_requires_a_stated_target(self):
        """GAP FOUND in this audit: undo accepted an identity with no stated target."""
        from apps.core.execution.execution_completion import (
            complete_by_identity, reverse_by_identity,
        )
        complete_by_identity(self.user, "routine_item", self.a.pk, self.today,
                             requested_target="Item A")
        out = reverse_by_identity(self.user, "routine_item", self.a.pk, self.today)
        self.assertEqual(out["status"], "target_unverified",
                         "reversal accepted an unverified target — a wrong id would "
                         "have un-completed the wrong object")
        self.assertFalse(out["detail"]["mutated"])
