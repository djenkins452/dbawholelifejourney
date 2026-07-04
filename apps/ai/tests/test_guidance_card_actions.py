# ==============================================================================
# File: apps/ai/tests/test_guidance_card_actions.py
# Description: WI-1 — interactive guidance card buttons must fulfill their promise.
#   "Tell me more" / "How to use this" (action 'chat') ask Beth the card's pre-written
#   question; "Got it" (action 'dismiss') dismisses AND persists so the same
#   observation doesn't resurface unless it materially changes. Origin: the server
#   had no 'chat'/'dismiss' handler, so every click returned "I'm not sure how to
#   handle that action." — the buttons did nothing.
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.ai.quick_reply_handlers import handle_quick_reply

User = get_user_model()


class GuidanceCardActionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="guidance@test.com", password="x")
        cache.clear()

    def _service(self):
        from apps.ai.proactive_checkins import ProactiveCheckInService
        return ProactiveCheckInService(self.user)

    def _card(self, svc, narrative="On 7+ hour nights your mood is more positive",
              strength="strong", ctype="sleep_mood"):
        with mock.patch.object(svc.throttler, "can_send", return_value=True):
            return svc.generate_cdce_correlation_check_in(
                ctype, narrative, strength, ["sleep", "journal"])

    # ── The actions are no longer "unknown" ────────────────────────────────────
    def test_chat_action_recognized(self):
        r = handle_quick_reply(self.user, "chat", {})
        self.assertTrue(r["success"])
        self.assertNotIn("not sure how to handle", (r.get("message") or "").lower())

    def test_dismiss_action_recognized(self):
        r = handle_quick_reply(self.user, "dismiss", {})
        self.assertTrue(r["success"])

    # ── Got it → persists a dismissal keyed by the card's identity + content hash ─
    def test_dismiss_persists_marker(self):
        svc = self._service()
        card = self._card(svc)
        self.assertIsNotNone(card)
        handle_quick_reply(self.user, "dismiss", {"message_id": card.id})
        marker = cache.get(f"wlj:guidance_dismissed:{self.user.id}:sleep_mood")
        self.assertEqual(marker, (card.metadata or {}).get("content_hash"))

    # ── Dismissed observation does not resurface — unless materially changed ────
    def test_dismissed_does_not_resurface_unless_changed(self):
        svc = self._service()
        m1 = self._card(svc)
        self.assertIsNotNone(m1)
        handle_quick_reply(self.user, "dismiss", {"message_id": m1.id})

        # Same observation → suppressed.
        self.assertIsNone(self._card(svc))

        # Materially changed (different narrative + strength → different hash) → surfaces.
        m3 = self._card(svc, narrative="Now a NEGATIVE pattern on nights under 6 hours",
                        strength="moderate")
        self.assertIsNotNone(m3)
