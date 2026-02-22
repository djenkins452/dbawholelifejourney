"""Owner-only access mixin for Financial Command Center views."""

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect


class OwnerOnlyMixin(UserPassesTestMixin):
    """
    Restrict access to owner/superuser only.

    Checks:
      1. request.user.is_superuser
      2. OR user has 'owner_finance.view_llmusageevent' permission
         (a proxy for OWNER_FINANCE_ACCESS)
    """

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser
            or user.has_perm('owner_finance.view_llmusageevent')
        )

    def handle_no_permission(self):
        messages.error(
            self.request,
            "You don't have permission to access the Financial Command Center.",
        )
        return redirect('dashboard:home')
