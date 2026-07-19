# ==============================================================================
# File: apps/faith/views_first_light.py
# Project: Whole Life Journey - Django 5.x
# Description: First Light — Formation. The present-tense "Today" Faith home and
#              the dispatcher that serves it to opted-in users while leaving the
#              classic Faith home untouched for everyone else.
# ==============================================================================
"""First Light views.

Request-path-safe: the only work these views do is call the deterministic,
read-only ``build_today`` presenter (no LLM, no heavy intelligence, no rebuilds).
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.help.mixins import HelpContextMixin

from .first_light.today import build_today
from .views import FaithHomeView, FaithRequiredMixin

logger = logging.getLogger(__name__)


class FaithTodayView(HelpContextMixin, LoginRequiredMixin, FaithRequiredMixin, TemplateView):
    """The First Light "Today" — presence, a companion, and one warm step."""

    template_name = "faith/today.html"
    help_context_id = "FAITH_HOME"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["today"] = build_today(self.request.user)
        return context


class FaithMirrorView(HelpContextMixin, LoginRequiredMixin, FaithRequiredMixin, TemplateView):
    """The Mirror — a spiritual biography reflected back from truth WLJ owns.

    Request-path-safe: reads only the cached reflection. On a cache miss it
    enqueues the background compute (non-blocking) and shows a gentle "preparing"
    state — it never computes the heavy aggregation inline.
    """

    template_name = "faith/mirror.html"
    help_context_id = "FAITH_HOME"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .first_light.mirror import get_cached_mirror

        mirror = get_cached_mirror(self.request.user)
        if mirror is None:
            from apps.core.celery_utils import safe_enqueue
            from apps.faith.tasks import compute_faith_mirror
            safe_enqueue(compute_faith_mirror, self.request.user.id)
            context["mirror"] = None
            context["pending"] = True
        else:
            context["mirror"] = mirror
            context["pending"] = False
        return context


def _first_light_enabled(request) -> bool:
    """True when the request should be served the First Light 'Today' home.

    Opt-in per user via the ``features.faith.first_light`` sub-feature flag, with
    an env-backed settings default (FAITH_FIRST_LIGHT_DEFAULT) for an instant,
    code-free global switch — mirroring the dashboard v2/v3 dispatch pattern.
    """
    if not request.user.is_authenticated:
        return False
    try:
        if request.user.preferences.is_feature_enabled("faith", "first_light"):
            return True
    except Exception:  # pragma: no cover - defensive; missing prefs
        logger.warning("First Light flag check failed for user=%s", request.user.pk, exc_info=True)
    return bool(getattr(settings, "FAITH_FIRST_LIGHT_DEFAULT", False))


def faith_home_dispatch(request, *args, **kwargs):
    """Canonical /faith/ entry point.

    Serves the First Light 'Today' home to opted-in users; otherwise the classic
    Faith home. The classic home stays directly reachable at /faith/classic/ for
    rollback and comparison.
    """
    if _first_light_enabled(request):
        return FaithTodayView.as_view()(request, *args, **kwargs)
    return FaithHomeView.as_view()(request, *args, **kwargs)
