# ==============================================================================
# File: apps/core/tests/test_mobile_chrome_overlap.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Nothing floats over page content on mobile.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The Chief-of-Staff button must not sit on top of the page.

A fixed circle in the bottom-right corner covers a 48px patch of whatever is scrolling
underneath it. On a 375px screen a card's action row is full width, so the button sat on
its last button — "View details" on Recurring — and no scroll position freed it.
Reserving page padding does not help: padding clears the END of a page, and a fixed
element covers its band the whole way down.

`assistant_panel.html` already hid the button at <=1024px — but that rule sits inside the
panel's own "personal assistant enabled" guard, and **the preference defaults to False**.
So the button was hidden for people who had the assistant switched ON, and left floating
over the content of everyone who had not — which is every new account.

That asymmetry is what these tests pin. The earlier version would pass a check written
against Danny's account and fail for a default one, which is exactly how it survived.
"""
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import get_template
from django.test import TestCase
from django.urls import reverse

from apps.users.models import TermsAcceptance

User = get_user_model()

#: The rule that stops the button floating, wherever it is written.
HIDE_RULE = re.compile(
    r"@media[^{]*max-width:\s*1024px[^{]*\{[^}]*?\.assistant-toggle-btn\s*\{[^}]*"
    r"display:\s*none\s*!important", re.S | re.I)


def _usable(user, *, assistant):
    TermsAcceptance.objects.get_or_create(
        user=user,
        defaults={"terms_version": settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")})
    prefs = user.preferences
    prefs.has_completed_onboarding = True
    prefs.finances_enabled = True
    prefs.personal_assistant_enabled = assistant
    prefs.save()
    return user


class TheFloatingButtonNeverFloatsOnMobileTests(TestCase):
    """Both preference states, because only one of them was ever broken."""

    def setUp(self):
        self.off = _usable(User.objects.create_user(
            email="chrome-off@example.com", password="pw" * 8), assistant=False)
        self.on = _usable(User.objects.create_user(
            email="chrome-on@example.com", password="pw" * 8), assistant=True)

    def _page(self, user):
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:home"), follow=True)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_default_account_gets_the_hide_rule(self):
        """`personal_assistant_enabled` defaults to False — THE broken case."""
        self.assertTrue(
            HIDE_RULE.search(self._page(self.off)),
            "a user with the assistant switched off had a floating button sitting on "
            "top of the page; the hide rule must not depend on that preference")

    def test_the_assistant_account_gets_it_too(self):
        self.assertTrue(HIDE_RULE.search(self._page(self.on)))

    def test_the_rule_lives_with_the_button_not_in_the_gated_panel(self):
        """Where it is matters: inside the panel it only fires for some people."""
        widget = get_template("components/chat_widget.html").template.source
        self.assertTrue(
            HIDE_RULE.search(widget),
            "the hide rule belongs in the template that DEFINES the button, so it "
            "cannot be switched off by an unrelated preference")

    def test_the_button_is_not_the_only_way_in_on_mobile(self):
        """Hiding it without a replacement would just remove access."""
        self.assertIn("data-assistant-open", self._page(self.off),
                      "a mobile user without the pull-up needs a docked way in")

    def test_the_docked_entry_is_inside_the_bottom_chrome(self):
        """Reserved space the page already pads for — not a new floating band."""
        body = self._page(self.off)
        bar = body[body.index('class="bottom-tab-bar"'):]
        bar = bar[:bar.index("</nav>")]
        self.assertIn("data-assistant-open", bar)

    def test_the_pullup_user_does_not_get_a_second_entry_point(self):
        """With the panel present there is already a full-width handle."""
        body = self._page(self.on)
        bar = body[body.index('class="bottom-tab-bar"'):]
        self.assertNotIn("data-assistant-open", bar[:bar.index("</nav>")])
        self.assertIn("assistant-pullup", body)

    def test_the_docked_entry_opens_the_same_drawer(self):
        widget = get_template("components/chat_widget.html").template.source
        self.assertIn("data-assistant-open", widget)
        self.assertIn("openDrawer", widget)

    def test_the_page_reserves_room_for_the_bottom_chrome(self):
        """Padding does not stop mid-scroll overlap, but it must stop content being
        trapped under the bar at rest."""
        from pathlib import Path

        css = (Path(settings.BASE_DIR) / "static" / "css" / "main.css").read_text()
        block = css[css.index("@media (max-width: 768px)"):]
        self.assertIn("padding-bottom", block[:block.index("}\n}")])


class NoOtherFixedElementFloatsOverContentTests(TestCase):
    """A second floating band is the defect; bottom nav chrome is not.

    Content passing under a fixed bottom nav while scrolling is how every mobile app
    works, and the page pads for it so nothing is trapped at rest. What is not
    acceptable is an ADDITIONAL fixed element hovering over the content column — that
    is what the button was, and what nothing else may become.
    """

    #: Fixed elements that are legitimate bottom/top chrome.
    ALLOWED = {
        ".bottom-tab-bar", ".site-header", ".assistant-panel", ".assistant-pullup",
        ".assistant-drawer", ".assistant-overlay", ".ap-focus-backdrop",
        ".assistant-toggle-btn",       # allowed BECAUSE it is hidden <=1024px
        ".nav-menu",                   # the desktop/mobile nav drawer, pre-existing
    }

    def test_the_toggle_button_is_the_only_floating_element_and_it_is_hidden(self):
        from pathlib import Path

        css = (Path(settings.BASE_DIR) / "static" / "css" / "main.css").read_text()
        floating = set()
        for match in re.finditer(r"([^{}]+)\{[^}]*position:\s*fixed", css):
            for selector in match.group(1).split(","):
                selector = selector.strip().split()[0] if selector.strip() else ""
                if selector.startswith(".") or selector.startswith("#"):
                    floating.add(selector)
        unexpected = sorted(s for s in floating if s not in self.ALLOWED)
        self.assertEqual(
            unexpected, [],
            "a new fixed element appeared in the global stylesheet. If it sits over "
            f"the content column on mobile it will cover controls: {unexpected}")
