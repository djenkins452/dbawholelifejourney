# ==============================================================================
# File: apps/ai/tests/test_cos_account_flag.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Per-account ChatGPT CoS enablement (UserPreferences.use_chatgpt_cos)
# ==============================================================================
"""
The ChatGPT CoS is enabled PER ACCOUNT (legacy Beth is the global default):
* global override `WLJ_COS_EVIDENCE_TOOLS_ENABLED` -> on for everyone (dev/test);
* otherwise `UserPreferences.use_chatgpt_cos` -> the production opt-in.
Toggling the preference off is the zero-deploy rollback.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.cos_services.tool_registry import evidence_tools_enabled

User = get_user_model()


class PerAccountFlagTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="alpha@example.com", password="x")

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
    def test_default_is_legacy_beth(self):
        # fresh user -> preference defaults False -> legacy Beth
        self.assertFalse(self.user.preferences.use_chatgpt_cos)
        self.assertFalse(evidence_tools_enabled(self.user))

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
    def test_account_opt_in_enables(self):
        self.user.preferences.use_chatgpt_cos = True
        self.user.preferences.save()
        self.user.refresh_from_db()
        self.assertTrue(evidence_tools_enabled(self.user))

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
    def test_account_toggle_off_is_rollback(self):
        self.user.preferences.use_chatgpt_cos = True
        self.user.preferences.save()
        self.assertTrue(evidence_tools_enabled(self.user))
        # zero-deploy rollback: toggle off
        self.user.preferences.use_chatgpt_cos = False
        self.user.preferences.save()
        self.user.refresh_from_db()
        self.assertFalse(evidence_tools_enabled(self.user))

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
    def test_no_user_is_disabled(self):
        self.assertFalse(evidence_tools_enabled(None))

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=True)
    def test_global_override_enables_for_everyone(self):
        self.assertFalse(self.user.preferences.use_chatgpt_cos)
        self.assertTrue(evidence_tools_enabled(self.user))
