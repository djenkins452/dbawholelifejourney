"""Current Context LIFECYCLE across navigation — the stale-focus regression.

Production bug (2026-07-11): Journal → Goal → Workout navigation, then
"Tell me about what I'm looking at" answered about the earlier GOAL, because
(1) the workout detail page (a TemplateView) declared NO <meta name="wlj-context">
    so no focus_ref was ever sent, and
(2) the conversation fallback served the last-remembered object (the goal) with no
    check that the user was still on that page.

Authority rules under test:
  1. A valid focus_ref from the current request always wins.
  2. Conversation fallback is used ONLY when the current request truly has no focus
     AND the turn is still on the SAME page it was remembered on.
  3. Navigation immediately replaces/clears the previous focus.
  4. A stale fallback is never presented as the current screen.
"""
from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase

from apps.ai.cos_services.current_context import get_current_context_baseline
from apps.ai.models import AssistantConversation
from apps.health.models import WorkoutSession
from apps.journal.models import JournalEntry
from apps.purpose.models import LifeGoal

User = get_user_model()


class CurrentContextNavigationLifecycleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="nav@example.com", password="pw12345!")
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS["TERMS_VERSION"],
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        self.journal = JournalEntry.objects.create(
            user=self.user, title="Long work day",
            body="Worked on WLJ and Step/PFP; hoping for pool time after tomorrow's workout.",
        )
        self.goal = LifeGoal.objects.create(
            user=self.user, title="Relationship with God",
            description="Grow closer to God through daily prayer and scripture.",
        )
        self.workout = WorkoutSession.objects.create(
            user=self.user, name="Adjusted Lower Body", date=date(2026, 7, 11),
            notes="Reduced volume; focus on form.",
        )
        self.journal_url = f"/journal/entry/{self.journal.pk}/"
        self.goal_url = f"/purpose/goals/{self.goal.pk}/"
        self.workout_url = f"/health/physical/fitness/workout/{self.workout.pk}/"
        self.conv = AssistantConversation.objects.create(user=self.user)

    def _focus(self, url, focus_ref=None):
        """Resolve current_screen.focus exactly as the envelope would for one turn."""
        pc = {"url": url, "module": "x", "page_title": "x"}
        if focus_ref is not None:
            pc["focus_ref"] = focus_ref
        cc = get_current_context_baseline(
            self.user, page_context=pc, conversation=self.conv,
        )
        return cc["current_screen"].get("focus")

    def _navigate_journal_goal_workout(self):
        """Steps 1–3: user visits journal, then goal, then workout (each declares focus)."""
        self._focus(self.journal_url, self.journal.context_ref())
        self._focus(self.goal_url, self.goal.context_ref())
        # Step 3: workout page NOW declares its ref (Fix A).
        return self._focus(self.workout_url, self.workout.context_ref())

    # -- The production repro ------------------------------------------------
    def test_workout_focus_wins_after_goal_navigation(self):
        """Journal → Goal → Workout, then 'tell me about what I'm looking at' (still on the
        workout page, focus_ref present): focus MUST be the workout, never the goal."""
        self._navigate_journal_goal_workout()
        # Step 4 — same workout page, focus_ref present (the normal client).
        focus = self._focus(self.workout_url, self.workout.context_ref())
        self.assertIsNotNone(focus)
        self.assertEqual(focus["ref"], self.workout.context_ref())
        self.assertEqual(focus["authority"], "current_request")
        self.assertIn("Adjusted Lower Body", focus["title"])
        # The earlier goal must NOT leak into the current screen.
        self.assertNotIn(self.goal.context_ref(), focus["ref"])
        self.assertNotIn("Relationship with God", focus.get("content", ""))

    def test_navigation_clears_stale_goal_when_new_page_declares_no_focus(self):
        """The class-killer: after the goal was remembered, a turn on a DIFFERENT page
        (the workout url) that declared NO focus_ref must NOT fall back to the goal —
        navigation invalidates the stale fallback (rules 2–4)."""
        self._focus(self.goal_url, self.goal.context_ref())          # remember goal @ goal_url
        # Now on the workout page but the client omitted focus_ref (HTMX-stale-head case).
        focus = self._focus(self.workout_url, focus_ref=None)
        self.assertIsNone(
            focus,
            "stale goal focus leaked onto the workout page — navigation guard failed",
        )

    def test_same_page_transient_omission_still_uses_fallback(self):
        """Guard we did NOT break the legitimate net: a focus_ref omission on the SAME url
        it was remembered on still falls back (authority conversation_fallback)."""
        self._focus(self.goal_url, self.goal.context_ref())          # remember goal @ goal_url
        focus = self._focus(self.goal_url, focus_ref=None)           # same page, omitted
        self.assertIsNotNone(focus)
        self.assertEqual(focus["authority"], "conversation_fallback")
        self.assertEqual(focus["ref"], self.goal.context_ref())

    # -- Fix A end-to-end: the workout page actually emits the meta ----------
    def test_workout_detail_page_emits_wlj_context_meta(self):
        client = Client()
        client.force_login(self.user)
        resp = client.get(self.workout_url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('name="wlj-context"', html)
        self.assertIn(f'content="health.workoutsession:{self.workout.pk}"', html)
