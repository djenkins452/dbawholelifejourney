# ==============================================================================
# File: apps/admin_console/temp_diag_von.py
# TEMPORARY, READ-ONLY diagnostic — "Check on Von's House" completion trust incident.
# Purpose: capture the REAL build_standing_context() truth for the logged-in user to
# settle whether execution_state.completed actually contained the task (upstream false
# completion) vs. an OpenAI fabrication from otherwise-correct truth.
#
# CONTRACT: read-only (no writes), self-scoped (only request.user's own data), staff-gated,
# no cache. REMOVE THIS FILE + its one URL in a single follow-up commit once evidence is
# captured (temporary-infra lifecycle).
# ==============================================================================
import json
import logging

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache

from apps.admin_console.views import AdminRequiredMixin

logger = logging.getLogger(__name__)

_VON = "von"


def _safe(fn, default=None):
    try:
        return fn()
    except Exception as e:  # pragma: no cover - diagnostic must never 500
        return {"__error__": f"{type(e).__name__}: {e}"}


def _row(t):
    """Raw Task fields relevant to the completion question (read-only projection)."""
    def iso(v):
        return v.isoformat() if v is not None and hasattr(v, "isoformat") else v
    return {
        "id": t.pk,
        "title": t.title,
        "status": getattr(t, "status", None),
        "completion_status": t.completion_status,
        "completed_at": iso(getattr(t, "completed_at", None)),
        "due_date": iso(getattr(t, "due_date", None)),
        "is_recurring": getattr(t, "is_recurring", None),
        "recurrence_pattern": getattr(t, "recurrence_pattern", None),
        "start_date": iso(getattr(t, "start_date", None)),
        "end_date": iso(getattr(t, "end_date", None)),
        "is_routine": getattr(t, "is_routine", None),
        "scheduled_time": iso(getattr(t, "scheduled_time", None)),
        "created_at": iso(getattr(t, "created_at", None)),
        "updated_at": iso(getattr(t, "updated_at", None)),
    }


@method_decorator(never_cache, name="dispatch")
class TempVonDiagnosticView(AdminRequiredMixin, View):
    """GET → JSON snapshot of the caller's OWN deterministic truth. No parameters, no
    writes, no other user's data. Staff-only (AdminRequiredMixin)."""

    def get(self, request, *args, **kwargs):
        user = request.user

        # --- Execution truth (built ONCE) -------------------------------------
        def _exec():
            from apps.core.execution.execution_state import build_execution_state
            from apps.core.execution.decision_authority import (
                execution_facts, current_action,
            )
            state = build_execution_state(user)
            ef = execution_facts(user, state=state) or {}
            ca = current_action(user, state=state) or {}
            return {
                "completed": ef.get("completed"),
                "overdue": ef.get("overdue"),
                "due_now": ef.get("due_now"),
                "coming_up": ef.get("coming_up"),
                "later": ef.get("later"),
                "current_action": {
                    "reason": ca.get("reason"),
                    "message": ca.get("message"),
                    "primary_action": (ca.get("primary_action") or {}).get("title")
                    if isinstance(ca.get("primary_action"), dict) else None,
                },
            }

        # --- Full standing-context envelope: wins + scan for "von" ------------
        def _envelope():
            from apps.ai.model_interface.service import ModelInterfaceService
            env = ModelInterfaceService(user).build_standing_context()
            du = env.get("deterministic_understanding") or {}
            wins = du.get("wins") if isinstance(du, dict) else None
            carried = []
            for k, v in env.items():
                try:
                    if _VON in json.dumps(v, default=str).lower():
                        carried.append(k)
                except Exception:
                    pass
            return {
                "deterministic_understanding_wins": wins,
                "envelope_contains_von": bool(carried),
                "von_carried_in_keys": carried,
            }

        # --- Raw Task rows for the title (incl. soft-deleted if available) ----
        def _rows():
            from apps.life.models import Task
            out = {}
            out["default_manager"] = [
                _row(t) for t in Task.objects.filter(
                    user=user, title__icontains=_VON).order_by("-updated_at")
            ]
            mgr = getattr(Task, "all_objects", None)
            if mgr is not None:
                out["all_objects_incl_deleted"] = [
                    _row(t) for t in mgr.filter(
                        user=user, title__icontains=_VON).order_by("-updated_at")
                ]
            return out

        from apps.core.utils import get_user_now
        payload = {
            "diagnostic": "temp_von_current_context (READ-ONLY, self-scoped)",
            "user_id": user.id,
            "as_of": _safe(lambda: get_user_now(user).isoformat()),
            "execution_state": _safe(_exec),
            "envelope": _safe(_envelope),
            "von_task_rows": _safe(_rows),
        }
        return JsonResponse(payload, json_dumps_params={"indent": 2, "default": str})
