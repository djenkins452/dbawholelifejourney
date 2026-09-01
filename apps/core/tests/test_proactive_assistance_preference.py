# ==============================================================================
# File: apps/core/tests/test_proactive_assistance_preference.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The setting controls interruption, never access.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""`proactive_assistance_enabled` means one thing: may it start something on its own.

It used to be `personal_assistant_enabled`, a module switch, and turning it off removed
the Chief of Staff outright — every entry point disappeared and the chat API refused.
Someone who only wanted it to stop interrupting them had to give the whole thing up.

Two questions, now two fields:

  * `personal_assistant_consent`      — may it read my life? A permission. Gates access.
  * `proactive_assistance_enabled`    — may it come to me unasked? A preference. Gates
                                        check-ins, briefings, greetings, the panel.

These tests hold the line between them in both directions: proactive OFF must never cost
someone access, and proactive ON must never substitute for consent.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.users.models import TermsAcceptance

User = get_user_model()


def _person(email, *, consent=True, proactive=False):
    user = User.objects.create_user(email=email, password="pw" * 8)
    TermsAcceptance.objects.get_or_create(
        user=user,
        defaults={"terms_version": settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")})
    prefs = user.preferences
    prefs.has_completed_onboarding = True
    prefs.ai_enabled = True
    prefs.ai_data_consent = consent
    prefs.personal_assistant_consent = consent
    prefs.proactive_assistance_enabled = proactive
    prefs.save()
    return user


class AccessDoesNotDependOnProactiveTests(TestCase):
    """Turning off interruption must not take the Chief of Staff away."""

    def setUp(self):
        self.quiet = _person("quiet@example.com", proactive=False)
        self.open_to_it = _person("proactive@example.com", proactive=True)

    def _page(self, user):
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:home"), follow=True)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_chat_endpoint_answers_with_proactive_off(self):
        """The endpoint that used to refuse. This is the regression."""
        from apps.ai.views import AssistantChatView

        view = AssistantChatView()
        view.request = type("R", (), {"user": self.quiet})()
        allowed, error = view.check_cos_access()
        self.assertTrue(allowed, error)

    def test_a_proactive_surface_still_declines_with_proactive_off(self):
        from apps.ai.views import AssistantOpeningView

        view = AssistantOpeningView()
        view.request = type("R", (), {"user": self.quiet})()
        allowed, error = view.check_proactive_assistance_enabled()
        self.assertFalse(allowed)
        self.assertIn("still open it", error,
                      "the refusal must say access is unaffected")

    def test_a_proactive_surface_runs_when_it_is_on(self):
        from apps.ai.views import AssistantOpeningView

        view = AssistantOpeningView()
        view.request = type("R", (), {"user": self.open_to_it})()
        self.assertTrue(view.check_proactive_assistance_enabled()[0])

    def test_navigation_offers_cos_with_proactive_off(self):
        self.assertIn(reverse("ai:cos_settings"), self._page(self.quiet))

    def test_the_mobile_tab_offers_cos_with_proactive_off(self):
        body = self._page(self.quiet)
        bar = body[body.index('class="bottom-tab-bar"'):]
        self.assertIn("data-assistant-open", bar[:bar.index("</nav>")])

    def test_the_pullup_is_absent_with_proactive_off(self):
        """It expands on its own, so it is a proactive surface."""
        self.assertNotIn("assistant-pullup", self._page(self.quiet))

    def test_the_pullup_is_present_with_proactive_on(self):
        self.assertIn("assistant-pullup", self._page(self.open_to_it))

    def test_only_one_mobile_entry_point_at_a_time(self):
        body = self._page(self.open_to_it)
        bar = body[body.index('class="bottom-tab-bar"'):]
        self.assertNotIn("data-assistant-open", bar[:bar.index("</nav>")],
                         "the pull-up is already there; two is clutter")


class ConsentStillGovernsAccessTests(TestCase):
    """Proactive is not a way around a permission."""

    def setUp(self):
        self.no_consent = _person("noconsent@example.com",
                                  consent=False, proactive=True)

    def test_without_consent_the_chat_declines(self):
        from apps.ai.views import AssistantChatView

        view = AssistantChatView()
        view.request = type("R", (), {"user": self.no_consent})()
        self.assertFalse(view.check_cos_access()[0])

    def test_without_consent_proactive_declines_too(self):
        from apps.ai.views import AssistantOpeningView

        view = AssistantOpeningView()
        view.request = type("R", (), {"user": self.no_consent})()
        self.assertFalse(view.check_proactive_assistance_enabled()[0])

    def test_without_consent_nothing_is_advertised(self):
        self.client.force_login(self.no_consent)
        body = self.client.get(reverse("dashboard:home"),
                               follow=True).content.decode()
        bar = body[body.index('class="bottom-tab-bar"'):]
        self.assertNotIn("data-assistant-open", bar[:bar.index("</nav>")],
                         "offering a door that will refuse is worse than no door")


class TheFieldMeansOneThingTests(TestCase):
    """No caller may use it as a stand-in for access again."""

    def test_the_access_check_does_not_read_the_preference(self):
        import inspect

        from apps.ai.views import AssistantMixin

        source = inspect.getsource(AssistantMixin.check_cos_access)
        self.assertNotIn("proactive_assistance_enabled", source.split('"""')[2],
                         "access must not depend on whether someone wants to be "
                         "interrupted")

    def test_user_initiated_endpoints_use_the_access_check(self):
        import inspect
        import re

        from apps.ai import views

        source = inspect.getsource(views)
        speaks_first = {"AssistantOpeningView", "AssistantWakeView",
                        "ProactiveBriefingView", "SessionStartView"}
        current, wrong = None, []
        for line in source.split("\n"):
            match = re.match(r"class (\w+)", line)
            if match:
                current = match.group(1)
            if "check_proactive_assistance_enabled()" in line and \
                    current not in speaks_first:
                wrong.append(current)
        self.assertEqual(sorted(set(wrong)), [],
                         "an endpoint the person opened themselves must not require "
                         f"proactive assistance: {sorted(set(wrong))}")

    def test_the_old_name_is_gone(self):
        from apps.users.models import UserPreferences

        names = {f.name for f in UserPreferences._meta.get_fields()}
        self.assertIn("proactive_assistance_enabled", names)
        self.assertNotIn("personal_assistant_enabled", names)

    def test_the_help_text_describes_interruption_not_capability(self):
        from apps.users.models import UserPreferences

        field = UserPreferences._meta.get_field("proactive_assistance_enabled")
        self.assertIn("on its own", field.help_text)
        self.assertIn("full access", field.help_text)


class ExistingChoicesSurviveTests(TestCase):
    """A rename must not change anybody's answer."""

    def test_the_migration_renames_rather_than_recreates(self):
        from django.db.migrations.loader import MigrationLoader

        migration = MigrationLoader(None, ignore_no_migrations=True).disk_migrations[
            ("users", "0096_proactive_assistance_enabled")]
        kinds = [op.__class__.__name__ for op in migration.operations]
        self.assertIn("RenameField", kinds,
                      "AddField + RemoveField would discard every existing choice")
        self.assertNotIn("RemoveField", kinds)

    def test_a_person_who_wanted_interruption_still_gets_it(self):
        person = _person("kept@example.com", proactive=True)
        person.preferences.refresh_from_db()
        self.assertTrue(person.preferences.proactive_assistance_enabled)

    def test_saving_preferences_does_not_silently_flip_it(self):
        """It is bound from the form now, so an unrendered field would zero it."""
        import inspect

        from apps.users.forms import PreferencesForm

        self.assertIn("proactive_assistance_enabled", PreferencesForm.Meta.fields)
        template = open("templates/users/preferences.html").read()
        self.assertIn('name="proactive_assistance_enabled"', template,
                      "a bound field that is never rendered posts as False and turns "
                      "proactive assistance off for everyone who saves preferences")

    def test_revoking_ai_consent_still_stops_everything(self):
        import inspect

        from apps.users.views import PreferencesView

        source = inspect.getsource(PreferencesView.form_valid)
        self.assertIn("instance.proactive_assistance_enabled = False", source)
