"""Current Context for the Bible Reading page: the declared reference must resolve to
DETERMINISTIC scripture truth (plan, day, refs, translation, verses) — so the model never
infers scripture from page text. Malachi 3:1-7 / 4:1-6 is the reported scenario."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.current_context import resolve_current_context
from apps.faith.journey.models import (
    JourneyArc, JourneyDay, JourneyPath, UserJourney, UserJourneyDayProgress,
)

User = get_user_model()


class JourneyCurrentContextTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="j@example.com", password="x")
        self.path = JourneyPath.objects.create(
            slug="walking-with-god", name="Walking With God",
            narrative_overview="A journey through Scripture.",
        )
        self.arc = JourneyArc.objects.create(
            journey_path=self.path, slug="arc-1", name="The Prophets", order=1,
            opening_note="o", closing_note="c",
        )
        self.day = JourneyDay.objects.create(
            arc=self.arc, day_number=7,
            scripture_refs=["Malachi 3:1-7", "Malachi 4:1-6"],
            scripture_content={
                "translation": "WEB",
                "blocks": [
                    {"ref": "Malachi 3:1", "text": "Behold, I send my messenger…"},
                    {"ref": "Malachi 4:1", "text": "For behold, the day comes…"},
                ],
            },
            context_before="Malachi closes the Old Testament.",
            plain_english_simple="s", plain_english_standard="std",
            plain_english_deeper="d", key_insight="God promises a coming messenger.",
            reflection_prompt="Where are you waiting on God?",
            application_action="Write one line of hope.", retention_anchor="a",
        )
        self.uj = UserJourney.objects.create(
            user=self.user, journey_path=self.path,
            current_arc=self.arc, current_day_number=7,
        )
        self.progress = UserJourneyDayProgress.objects.create(
            user=self.user, user_journey=self.uj, journey_day=self.day,
        )

    def test_progress_ref_resolves_to_deterministic_scripture(self):
        ref = self.progress.context_ref()
        self.assertEqual(ref, f"journey.userjourneydayprogress:{self.progress.pk}")
        resolved = resolve_current_context(self.user, ref=ref)
        self.assertIsNotNone(resolved)
        content = resolved["content"]
        # The exact scripture on screen — deterministic, not inferred.
        self.assertIn("Malachi 3:1-7", content)
        self.assertIn("Malachi 4:1-6", content)
        self.assertIn("WEB", content)                 # translation
        self.assertIn("Day: 7", content)              # day
        self.assertIn("Walking With God", content)    # reading plan
        self.assertIn("Behold, I send my messenger", content)  # verse text
        self.assertEqual(resolved["kind"], "scripture reading")

    def test_ownership_still_enforced(self):
        other = User.objects.create_user(email="o@example.com", password="x")
        self.assertIsNone(
            resolve_current_context(other, ref=self.progress.context_ref())
        )
