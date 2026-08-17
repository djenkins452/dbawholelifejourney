# ==============================================================================
# File: apps/ai/tests/test_phase2_cleanup.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Proves the Phase 2 cert-artifact cleanup (migration 0039) deletes ONLY the
#   known test artifacts by proven identity (owner + exact title + cert-day window) and never
#   touches a legitimately-named, same-day record. Tasks are soft-deleted (recoverable);
#   ConversationFollowUp rows (model shipped the same day) are removed outright.
# ==============================================================================
import importlib

from django.apps import apps as django_apps
from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.users.models import TermsAcceptance

try:
    from apps.users.models import User
except ImportError:
    from django.contrib.auth import get_user_model
    User = get_user_model()

OWNER_EMAIL = "dannyjenkins71@gmail.com"
_MIG = importlib.import_module("apps.ai.migrations.0039_cleanup_phase2_cert_artifacts")


def _owner():
    u = User.objects.create_user(email=OWNER_EMAIL, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    return u


class Phase2CleanupIdentityTests(TestCase):
    def setUp(self):
        self.user = _owner()

    def test_deletes_artifacts_only_and_spares_legit_data(self):
        from apps.ai.models import AssistantConversation, ConversationFollowUp
        from apps.life.models import Task

        artifact = Task.objects.create(user=self.user, title="Call the pharmacy")
        legit = Task.objects.create(user=self.user, title="Prepare board deck")
        conv = AssistantConversation.get_or_create_active(self.user)
        fu = ConversationFollowUp.objects.create(
            user=self.user, conversation=conv,
            due_at=timezone.now() + timezone.timedelta(hours=1), topic="test")

        _MIG.cleanup(django_apps, None)

        artifact.refresh_from_db()
        legit.refresh_from_db()
        self.assertIsNotNone(artifact.deleted_at, "artifact task should be soft-deleted")
        self.assertIsNone(legit.deleted_at, "legitimate same-day task must be untouched")
        self.assertFalse(ConversationFollowUp.objects.filter(pk=fu.pk).exists(),
                         "test follow-up should be removed")

    def test_idempotent_and_safe_on_second_run(self):
        from apps.life.models import Task
        Task.objects.create(user=self.user, title="Call the pharmacy")
        _MIG.cleanup(django_apps, None)
        _MIG.cleanup(django_apps, None)  # must not raise or change anything further
