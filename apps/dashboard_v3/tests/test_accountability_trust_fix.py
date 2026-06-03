"""Dashboard Accountability Cards — Phase A trust fix tests.

Guards three changes:

  1. `apps/core/ai_guidance/guidance_logger.py` — `_apply_persona` is
     removed from the log path; new GuidanceItem.message rows are
     persisted NEUTRAL (no "Good morning!" greeting baked in).

  2. `apps/dashboard_v3/services/composer.py` — defensive
     `_strip_leading_greeting` runs at render time in
     `_build_accountability_cards` so existing rows already in the DB
     don't surface stale time-of-day phrasing.

  3. `templates/dashboard_v3/sections/accountability_cards.html` +
     `templates/dashboard_v3/home.html` JS — long recommendations get
     a Read more / Show less affordance that reuses the existing
     v3 `data-expanded`/`aria-expanded` pattern. NO `<details>`.

Phase B (event-driven freshness convergence) is explicitly out of
scope; not tested here.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.ai_guidance.guidance_logger import log_guidance
from apps.core.ai_guidance.models import GuidanceItem
from apps.users.models import TermsAcceptance


User = get_user_model()


def _make_user(email="acct-trust@test.com"):
    u = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=u,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


_GREETING_PREFIXES = (
    "Good morning",
    "Good afternoon",
    "Good evening",
    "Good day",
    "Hey",
    "Hi",
    "Hello",
)


# ── 1. Storage-side fix ────────────────────────────────────────────

class GuidanceLoggerPersistsNeutralMessageTests(TestCase):
    """log_guidance() must persist GuidanceItem.message WITHOUT a
    persona greeting prefixed. Storage-time fix."""

    def setUp(self):
        self.user = _make_user("storage@test.com")

    def _log(self, message, dedupe_key, title="Train rest day"):
        candidate = {
            "title": title,
            "message": message,
            "dedupe_key": dedupe_key,
            "priority": 3,
            "guidance_type": "workout_freq",
            "module": "health",
            "source": "rule:test",
            "confidence_score": 0.9,
            "evidence": {},
        }
        return log_guidance(self.user, [candidate])

    def test_new_guidance_row_has_no_greeting_prefix(self):
        """The user-reported failure mode: 'Good morning!' baked into
        a stored row. This must never happen again for new rows."""
        body = (
            "You've been training consistently but haven't set new PRs "
            "in three weeks — consider adjusting your program."
        )
        self._log(body, dedupe_key="test:no-greeting:1")
        row = GuidanceItem.objects.filter(user=self.user).first()
        self.assertIsNotNone(row)
        # Stored message must equal the candidate's neutral text —
        # NO leading greeting prepended.
        self.assertEqual(row.message, body)
        for prefix in _GREETING_PREFIXES:
            self.assertFalse(
                row.message.startswith(prefix),
                f"persisted message must not start with {prefix!r}: "
                f"{row.message[:60]!r}",
            )

    def test_existing_row_message_update_does_not_introduce_greeting(self):
        """The update path (when a dedupe_key already exists) must
        also persist neutral text — the bug previously affected both
        the create and update branches."""
        body_v1 = "You've been training consistently."
        body_v2 = "You've been training consistently — set a deload day."
        self._log(body_v1, dedupe_key="test:no-greeting:upd")
        row = GuidanceItem.objects.filter(user=self.user).first()
        self.assertEqual(row.message, body_v1)
        # Re-log same dedupe_key with different body → update branch.
        self._log(body_v2, dedupe_key="test:no-greeting:upd")
        row.refresh_from_db()
        self.assertEqual(row.message, body_v2)
        for prefix in _GREETING_PREFIXES:
            self.assertFalse(row.message.startswith(prefix))


# ── 2. Render-side defensive strip ────────────────────────────────

class DefensiveGreetingStripTests(TestCase):
    """Existing production rows already contain baked-in greetings.
    The composer must strip them at render time so the dashboard
    never surfaces 'Good morning!' at 8 PM."""

    def test_strip_helper_removes_known_greetings(self):
        from apps.dashboard_v3.services.composer import _strip_leading_greeting
        cases = [
            ("Good morning! You've been training consistently.",
             "You've been training consistently."),
            ("Good afternoon, You've been training consistently.",
             "You've been training consistently."),
            ("Good evening! Bible reading streak holding.",
             "Bible reading streak holding."),
            ("Hey! Time to log a journal entry.",
             "Time to log a journal entry."),
            ("Hi, Glucose trend is steady.",
             "Glucose trend is steady."),
            # No greeting → unchanged.
            ("You've been training consistently.",
             "You've been training consistently."),
            # Greeting embedded mid-sentence is NOT stripped (only leading).
            ("Day 5 complete — good morning routine intact.",
             "Day 5 complete — good morning routine intact."),
        ]
        for inp, expected in cases:
            self.assertEqual(
                _strip_leading_greeting(inp), expected,
                f"strip failed for {inp!r}",
            )

    def test_strip_helper_is_noop_on_empty(self):
        from apps.dashboard_v3.services.composer import _strip_leading_greeting
        self.assertEqual(_strip_leading_greeting(""), "")
        self.assertEqual(_strip_leading_greeting(None), None)


class ComposerAppliesGreetingStripTests(TestCase):
    """End-to-end: a pre-existing row with a baked-in greeting must
    NOT appear with the greeting on the dashboard."""

    def setUp(self):
        self.user = _make_user("strip@test.com")

    def test_composer_strips_greeting_from_pre_existing_row(self):
        # Simulate a production-aged row with a baked greeting.
        GuidanceItem.objects.create(
            user=self.user,
            title="Workout consistency",
            message="Good morning! You've been training consistently.",
            module="health",
            guidance_type="workout_freq",
            source="rule:test",
            priority=3,
            dedupe_key="legacy-row-1",
            is_active=True,
            expires_at=timezone.now() + timedelta(days=1),
        )
        from apps.dashboard_v3.services.composer import _build_accountability_cards
        cards = _build_accountability_cards(self.user)
        health = next((c for c in cards if c["slug"] == "health"), None)
        self.assertIsNotNone(
            health, "health accountability card must render when "
            "guidance exists",
        )
        rec = health.get("recommendation") or {}
        self.assertEqual(
            rec.get("message"), "You've been training consistently.",
            f"composer should have stripped the leading greeting; got "
            f"{rec.get('message')!r}",
        )


# ── 3. Inline expand affordance ────────────────────────────────────

class ExpandAffordanceTests(TestCase):
    """Dashboard recommendation cards expand inline (no modal, no
    <details>, no navigation). Reuses the v3 data-expanded /
    aria-expanded pattern that already exists for rhythm tiles."""

    def setUp(self):
        self.user = _make_user("expand@test.com")
        self.client = Client()
        self.client.force_login(self.user)
        # Long-enough body to trigger truncation (>18 words).
        long_body = (
            "You've been training consistently but haven't set new PRs "
            "in three weeks — consider varying intensity, increasing "
            "load progression, or scheduling a deload week to allow "
            "recovery and adaptation before the next training block."
        )
        GuidanceItem.objects.create(
            user=self.user,
            title="Workout consistency",
            message=long_body,
            module="health",
            guidance_type="workout_freq",
            source="rule:test",
            priority=3,
            dedupe_key="long-row-1",
            is_active=True,
            expires_at=timezone.now() + timedelta(days=1),
        )

    def test_long_recommendation_renders_read_more_button(self):
        """When the message is longer than the truncation threshold,
        the dashboard surfaces an inline Read more affordance."""
        resp = self.client.get(reverse("dashboard_v3:home"))
        body = resp.content.decode("utf-8")
        self.assertIn("v3-acc-readmore", body)
        self.assertIn("Read more →", body)
        # The data-expanded/aria-expanded pattern that the home.html JS
        # already toggles for rhythm tiles must be present here too.
        self.assertIn('data-expanded="false"', body)
        self.assertIn('aria-expanded="false"', body)

    def test_full_message_present_in_dom_hidden_until_expand(self):
        """The expand handler reveals an already-rendered span — the
        full text must be in the DOM (just hidden) on initial render
        so toggling is instant (no fetch, no reload)."""
        resp = self.client.get(reverse("dashboard_v3:home"))
        body = resp.content.decode("utf-8")
        self.assertIn("v3-acc-msg-full", body)
        # The full text contains the LAST sentence of the message —
        # if only the truncated version were in the DOM, this would
        # be missing.
        self.assertIn(
            "before the next training block", body,
            "full message must be rendered (hidden) so the expand "
            "affordance can reveal it client-side without a fetch",
        )

    def test_no_browser_native_details_in_accountability_cards(self):
        """Regression guard: prior design considered <details>. The
        approved direction is the v3 data-expanded pattern only."""
        resp = self.client.get(reverse("dashboard_v3:home"))
        body = resp.content.decode("utf-8")
        # Search inside the accountability card region — be tolerant
        # of <details> appearing elsewhere on the page (e.g. Django
        # error pages won't be in normal renders, but be precise).
        import re
        section = re.search(
            r'<section class="v3-cards">(.*?)</section>',
            body, re.DOTALL,
        )
        if section:
            self.assertNotIn(
                "<details", section.group(1).lower(),
                "accountability cards must NOT use browser-native "
                "<details> — reuse the existing v3 data-expanded "
                "pattern for visual consistency",
            )
