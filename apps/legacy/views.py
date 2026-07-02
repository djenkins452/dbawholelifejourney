"""
Legacy views (Phase 1).

Home (the Hearth) is fully built. The remaining destinations render inside the
same immersive Legacy shell with a graceful "being prepared" state; each is
replaced by its real screen in a later slice of Phase 1.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.legacy.services.home import build_home_context


class LegacyContextMixin(LoginRequiredMixin):
    """Shared context for every Legacy page (drives sidebar active-state)."""

    nav_active = None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("nav_active", self.nav_active)
        return ctx


class HearthView(LegacyContextMixin, TemplateView):
    template_name = "legacy/home.html"
    nav_active = "home"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(build_home_context(self.request.user))
        return ctx


class LegacyPlaceholderView(LegacyContextMixin, TemplateView):
    """Graceful placeholder for destinations arriving in later Phase-1 slices."""

    template_name = "legacy/_placeholder.html"
