# ==============================================================================
# File: apps/core/tests/test_executable_identity_integrity_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Every projection naming an executable item must carry its identity
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-18
# ==============================================================================
"""Executable identity integrity (2026-08-18 production incident).

Danny asked to complete "Shower". The model called
`complete_execution_item(title="Shower", source_id=11, ...)` — and id 11 is
"Empty Dishwasher". An earlier attempt sent id 9 ("Wake up") for the same request. The
write-layer target-mismatch guard refused both, so nothing was mutated.

ROOT CAUSE: the envelope carried the SAME executable items in more than one projection,
and only `execution_state` carried canonical identity. `timing.remaining[]`,
`timing.next_anchor` and `earliest_future_commitment` named items by TITLE ONLY, so
anything reading those had to join back to identity by title across separate JSON
structures. That join failed, twice, on different items.

THE INVARIANT THIS FILE PROTECTS:

    Every projection that NAMES an executable item carries that item's canonical
    identity, and title -> source_id is consistent across the WHOLE envelope.

This is class-level: it is asserted over every item in a representative execution set,
not for one named item.
"""

import datetime
import json

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class ExecutableIdentityIntegrityTests(TestCase):
    """Production-equivalent fixture: two routines, several items, a non-Shower current
    action, and ids that are deliberately not contiguous with list order."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule, Task
        self.user = User.objects.create_user(email="ii@contract.test", password="x")
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.use_model_interface = True
        prefs.use_model_interface_writes = True
        prefs.save()
        self.user = User.objects.get(pk=self.user.pk)
        self.today = datetime.date.today()

        # The ROUTINE's block drives recovery eligibility, so it must match the times
        # below or the whole block ages out and the fixture silently loses its subject.
        # Both derived from `now`, keeping this suite wall-clock independent.
        _blocks = ["morning", "mid_morning", "lunch", "afternoon", "evening", "nightly"]
        _hour = datetime.datetime.now().hour
        _current = ("morning" if _hour < 9 else "mid_morning" if _hour < 11
                    else "lunch" if _hour < 14 else "afternoon" if _hour < 17
                    else "evening" if _hour < 21 else "nightly")
        _later = _blocks[min(_blocks.index(_current) + 1, len(_blocks) - 1)]
        morning = Routine.objects.create(
            user=self.user, name="Morning Routine", time_of_day=_current)
        nightly = Routine.objects.create(
            user=self.user, name="Nightly Routine", time_of_day=_later)

        def mk(routine, name, t):
            return RoutineSchedule.objects.create(
                routine=routine, name=name, scheduled_time=t, is_active=True,
                days_of_week="0,1,2,3,4,5,6")

        # Times are RELATIVE TO NOW, clamped inside the day. Fixed clock times made this
        # suite wall-clock dependent: morning items stop being recoverable late in the
        # day (correct Recovery-Contract behaviour), so they legitimately leave the
        # actionable buckets and the fixture silently lost its subject.
        now = datetime.datetime.now()
        def offset(minutes):
            t = (now + datetime.timedelta(minutes=minutes))
            hour = min(max(t.hour, 1), 22)
            return datetime.time(hour, t.minute)

        # Order here deliberately differs from time order, so a positional/index merge
        # would produce a visible mismatch.
        self.items = {
            # All UPCOMING. Overdue items are subject to the Recovery Contract's
            # recoverability window, which legitimately drops them from the actionable
            # buckets late in a block — correct product behaviour, but it makes a
            # fixture wall-clock dependent. Identity/confirmation/execution/verification
            # are what this suite exercises; overdue-ness is not.
            "Wake up": mk(morning, "Wake up", offset(10)),
            "Shower": mk(morning, "Shower", offset(15)),
            "THORNE Creatine": mk(morning, "THORNE Creatine", offset(20)),
            "Empty Dishwasher": mk(nightly, "Empty Dishwasher", offset(90)),
            "Lay out clothes": mk(nightly, "Lay out clothes", offset(120)),
        }
        self.canonical = {n: s.pk for n, s in self.items.items()}
        Task.objects.create(
            user=self.user, title="Call the pharmacy", due_date=self.today,
            completion_status="pending", status="active")

    # -- helpers -----------------------------------------------------------
    def _envelope(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(self.user)
        return svc.build_standing_context(writes_enabled=True)

    def _walk_named_items(self, node, out, path="ctx"):
        """Collect every dict in the envelope that NAMES an item (has a `title`)."""
        if isinstance(node, dict):
            if "title" in node and isinstance(node.get("title"), str) and node["title"]:
                out.append((path, node))
            for k, v in node.items():
                self._walk_named_items(v, out, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                self._walk_named_items(v, out, f"{path}[{i}]")
        return out

    # -- the class-level invariants ---------------------------------------
    def test_every_projection_naming_an_item_carries_its_identity(self):
        """A title without an id forces a join the model gets wrong."""
        named = self._walk_named_items(self._envelope(), [])
        offenders = []
        for path, node in named:
            title = node["title"]
            if title not in self.canonical:
                continue                      # not one of our executable items
            if node.get("source_id") is None:
                offenders.append(f"{path}: {title!r} named with no source_id")
        self.assertEqual(offenders, [], (
            "these envelope projections name an executable item WITHOUT canonical "
            "identity, forcing a title->id join across structures:\n  "
            + "\n  ".join(offenders)))

    def test_title_to_identity_is_consistent_across_the_whole_envelope(self):
        """THE production failure: one title paired with another item's id."""
        named = self._walk_named_items(self._envelope(), [])
        pairs = {}
        conflicts = []
        for path, node in named:
            title, sid = node["title"], node.get("source_id")
            if title not in self.canonical or sid is None:
                continue
            if title in pairs and pairs[title][0] != sid:
                conflicts.append(
                    f"{title!r}: id {pairs[title][0]} at {pairs[title][1]} vs {sid} at {path}")
            pairs.setdefault(title, (sid, path))
        self.assertEqual(conflicts, [], "\n  ".join(["inconsistent identity:"] + conflicts))

    def test_every_projected_identity_resolves_to_the_named_object(self):
        """source_id must resolve to a canonical object whose name IS the title."""
        from apps.life.models import RoutineSchedule
        named = self._walk_named_items(self._envelope(), [])
        wrong = []
        for path, node in named:
            title, sid = node["title"], node.get("source_id")
            if sid is None or node.get("source_type") != "routine_item":
                continue
            row = RoutineSchedule.objects.filter(
                pk=sid, routine__user=self.user).first()
            if row is None:
                wrong.append(f"{path}: {title!r} -> id {sid} resolves to nothing")
            elif row.name != title:
                wrong.append(f"{path}: {title!r} -> id {sid} is actually {row.name!r}")
        self.assertEqual(wrong, [], (
            "PRODUCTION CLASS: a title is paired with another object's identity:\n  "
            + "\n  ".join(wrong)))

    def test_no_identity_is_shared_by_two_different_titles(self):
        named = self._walk_named_items(self._envelope(), [])
        by_id = {}
        clashes = []
        for path, node in named:
            title, sid = node["title"], node.get("source_id")
            st = node.get("source_type")
            if sid is None or title not in self.canonical:
                continue
            key = (st, sid)
            if key in by_id and by_id[key] != title:
                clashes.append(f"{key} claimed by {by_id[key]!r} and {title!r}")
            by_id.setdefault(key, title)
        self.assertEqual(clashes, [], "\n  ".join(["duplicate identity:"] + clashes))

    def test_timing_projection_specifically_carries_identity(self):
        """The projection that actually caused the incident."""
        from apps.core.execution.execution_state import build_execution_state
        from apps.core.execution.timing import compute_execution_timing
        state = build_execution_state(self.user)
        timing = compute_execution_timing({"items": state.get("items") or []},
                                          datetime.datetime.now())
        remaining = timing.get("remaining") or []
        self.assertTrue(remaining, "no remaining items to check")
        for entry in remaining:
            if entry.get("title") in self.canonical:
                with self.subTest(item=entry.get("title")):
                    self.assertIsNotNone(entry.get("source_id"),
                                         "timing.remaining named an item with no identity")
                    self.assertEqual(entry["source_id"],
                                     self.canonical[entry["title"]])

    def test_identity_survives_json_serialization_into_the_prompt(self):
        """What the model literally reads must keep title and id adjacent."""
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(self.user)
        prompt = svc._system_prompt(svc.build_standing_context(writes_enabled=True))
        shower_id = self.canonical["Shower"]
        dish_id = self.canonical["Empty Dishwasher"]
        for mention in [m for m in prompt.split('{"title": "Shower"') if False]:
            pass
        # Every serialized object naming Shower must carry Shower's id, never another's.
        for chunk in prompt.split('"title": "Shower"')[1:]:
            window = chunk[:260]
            if '"source_id"' in window:
                self.assertIn(f'"source_id": {shower_id}', window,
                              "a serialized Shower object carries the wrong identity")
                self.assertNotIn(f'"source_id": {dish_id}', window)


class EndToEndActionLifecycleTests(ExecutableIdentityIntegrityTests):
    """ONE end-to-end contract for the whole customer flow, not six disconnected units.

    Reproduces the exact production shape deterministically: several visible routine
    items across two routines, a current action that is NOT the requested item, and a
    confirmation-required preference.
    """

    def setUp(self):
        super().setUp()
        prefs = self.user.preferences
        prefs.assistant_confirm_actions = True
        prefs.save()
        self.user = User.objects.get(pk=self.user.pk)
        from apps.ai.models import AssistantConversation
        self.conv = AssistantConversation.get_or_create_active(self.user)

    def _complete_state(self, name):
        from apps.core.execution.completion_service import is_routine_item_complete
        from apps.life.models import RoutineSchedule
        sched = RoutineSchedule.objects.get(pk=self.canonical[name])
        return bool(is_routine_item_complete(
            User.objects.get(pk=self.user.pk), sched, self.today))

    def _projected(self, name):
        from apps.core.execution.decision_authority import execution_facts
        facts = execution_facts(User.objects.get(pk=self.user.pk))
        for bucket in ("overdue", "due_now", "coming_up", "later", "completed"):
            for f in (facts.get(bucket) or []):
                if f.get("title") == name and f.get("source_type") == "routine_item":
                    return f
        return None

    def test_full_flow_request_confirm_execute_verify(self):
        from apps.ai.cos_services.action_execution import confirmation_required_for
        from apps.ai.cos_services.action_interface import (
            request_confirmation_for, resolve_typed_confirmation,
        )
        from apps.ai.model_interface import confirmation as _confirm
        from apps.core.execution.decision_authority import current_action

        target = "Shower"
        target_id = self.canonical[target]

        # -- the current action is deliberately NOT the requested item -------
        ca = (current_action(User.objects.get(pk=self.user.pk)).get("primary_action") or {})
        self.assertNotEqual(ca.get("source_id"), target_id,
                            "fixture invalid: the requested item IS the current action")

        # -- projection integrity for the requested item ---------------------
        proj = self._projected(target)
        self.assertIsNotNone(proj)
        self.assertEqual(proj["source_id"], target_id)
        self.assertFalse(proj["completed_today"])

        # -- Turn A: request -> confirmation required, nothing mutates -------
        user = User.objects.get(pk=self.user.pk)
        self.assertTrue(confirmation_required_for(user, "complete_execution_item"))
        gate = request_confirmation_for(
            user, "complete_execution_item",
            {"source_type": "routine_item", "source_id": target_id, "title": target},
            conversation_id=self.conv.id)
        _confirm.bind_conversation(user, self.conv.id)
        self.assertEqual(gate["status"], "confirmation_required")

        cid = (gate.get("confirmation") or {}).get("confirmation_id")
        rec = _confirm.get(user, cid)
        self.assertEqual(rec["params"]["source_id"], target_id,
                         "the confirmation bound the wrong identity")
        self.assertEqual(rec["params"]["title"], target)

        for name in self.canonical:
            self.assertFalse(self._complete_state(name),
                             f"{name} mutated before confirmation")

        # -- Turn B: "Confirm" -> deterministic execution --------------------
        out = resolve_typed_confirmation(
            User.objects.get(pk=self.user.pk), self.conv.id, "Confirm",
            turn_id="t", surface="chat_stream")
        self.assertIsNotNone(out, "the typed confirmation was not resolved deterministically")
        self.assertEqual(out["status"], "ok", out)

        # -- canonical truth + postcondition + no collateral change ----------
        self.assertTrue(self._complete_state(target))
        for name in self.canonical:
            if name != target:
                self.assertFalse(self._complete_state(name),
                                 f"{name} changed while completing {target}")

        # -- rebuilt Dashboard truth agrees ----------------------------------
        proj_after = self._projected(target)
        self.assertIsNotNone(proj_after, "the completed item vanished from the envelope")
        self.assertTrue(proj_after["completed_today"])
        self.assertEqual(proj_after["source_id"], target_id)

        # -- a later turn: current truth governs, prose is irrelevant --------
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(
            conversation=self.conv, role="assistant", message_type="text",
            content="Empty Dishwasher is marked as complete.")
        self.assertFalse(self._complete_state("Empty Dishwasher"))
        self.assertFalse(self._projected("Empty Dishwasher")["completed_today"],
                         "assistant prose became current truth on a later turn")

    def test_a_wrong_identity_is_still_refused_at_the_write_layer(self):
        """Defence in depth must remain, even now that projection is correct."""
        from apps.core.execution.execution_completion import complete_by_identity
        out = complete_by_identity(
            User.objects.get(pk=self.user.pk), "routine_item",
            self.canonical["Empty Dishwasher"], self.today, requested_target="Shower")
        self.assertEqual(out["status"], "target_mismatch")
        self.assertFalse(self._complete_state("Empty Dishwasher"))
        self.assertFalse(self._complete_state("Shower"))
