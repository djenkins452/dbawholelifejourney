# ==============================================================================
# File: apps/ai/tests/test_object_reveal_cleanup.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Proves the Object-Level Reveal cert-artifact cleanup (migration 0041) removes
#   ONLY the smoke artifacts (the "Reveal Test" journal + the 15-min mobility workout) by proven
#   identity, and never a legitimately-named same-day object. Soft-delete (recoverable).
# ==============================================================================
import importlib
from datetime import date

from django.apps import apps as django_apps
from django.conf import settings
from django.test import TestCase

from apps.users.models import TermsAcceptance

try:
    from apps.users.models import User
except ImportError:
    from django.contrib.auth import get_user_model
    User = get_user_model()

OWNER_EMAIL = "dannyjenkins71@gmail.com"
_MIG = importlib.import_module("apps.ai.migrations.0041_cleanup_object_reveal_artifacts")


def _owner():
    u = User.objects.create_user(email=OWNER_EMAIL, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    return u


class ObjectRevealCleanupTests(TestCase):
    def setUp(self):
        self.user = _owner()

    def test_removes_artifacts_only(self):
        from apps.journal.models import JournalEntry
        from apps.health.models import WorkoutSession

        art_j = JournalEntry.objects.create(user=self.user, title="Reveal Test")
        legit_j = JournalEntry.objects.create(user=self.user, title="Morning pages")
        art_w = WorkoutSession.objects.create(
            user=self.user, date=date(2026, 8, 17), name="Mobility", duration_minutes=15)
        legit_w = WorkoutSession.objects.create(
            user=self.user, date=date(2026, 8, 17), name="Mobility", duration_minutes=45)

        _MIG.cleanup(django_apps, None)

        for obj in (art_j, legit_j, art_w, legit_w):
            obj.refresh_from_db()
        self.assertIsNotNone(art_j.deleted_at, "'Reveal Test' journal should be soft-deleted")
        self.assertIsNone(legit_j.deleted_at, "a real same-day journal must be untouched")
        self.assertIsNotNone(art_w.deleted_at, "15-min mobility workout should be soft-deleted")
        self.assertIsNone(legit_w.deleted_at,
                          "a 45-min mobility workout (different duration) must be untouched")

    def test_idempotent(self):
        _MIG.cleanup(django_apps, None)
        _MIG.cleanup(django_apps, None)   # must not raise on a second run
