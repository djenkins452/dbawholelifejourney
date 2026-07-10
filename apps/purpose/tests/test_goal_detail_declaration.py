"""TRACE: does the Goal Detail page actually emit <meta name="wlj-context">?
Proves View → HTML → Meta with the real template, via the test client.

Also guards the CLASS this trace exposed: a chat surface that does not read the
wlj-context meta silently drops focus_ref, so Current Context reads as absent on that
surface. BOTH Beth surfaces must implement the transport."""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.purpose.models import LifeGoal

User = get_user_model()

_TEMPLATES = Path(settings.BASE_DIR) / "templates" / "components"
_CHAT_SURFACES = ("chat_widget.html", "assistant_panel.html")


class GoalDetailDeclarationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="gd@example.com", password="pw12345!")
        # Onboarding gate (else 302 to onboarding).
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS["TERMS_VERSION"],
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.goal = LifeGoal.objects.create(
            user=self.user, title="Launch Whole Life Journey",
            description="I would like ultimately market this product and take it global.",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_goal_detail_emits_wlj_context_meta(self):
        # 1) the model self-declares the reference
        self.assertEqual(self.goal.context_ref(), f"purpose.lifegoal:{self.goal.pk}")

        # 2) the rendered HEAD contains the meta with that exact ref
        resp = self.client.get(f"/purpose/goals/{self.goal.pk}/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('name="wlj-context"', html)
        self.assertIn(f'content="purpose.lifegoal:{self.goal.pk}"', html)


class ChatSurfaceTransportContractTests(TestCase):
    """Class guard: EVERY Beth chat surface must read the wlj-context meta and send the
    focus_ref reference. The Goal Detail bug was a surface (assistant_panel.html) that
    rendered the meta upstream but never read it — so Current Context never arrived."""

    def test_all_chat_surfaces_read_the_current_context_meta(self):
        for name in _CHAT_SURFACES:
            src = (_TEMPLATES / name).read_text()
            self.assertIn(
                'meta[name="wlj-context"]', src,
                msg=(f"{name} does not read the Current Context meta — it will drop "
                     "focus_ref and Current Context will be absent on that surface."),
            )
            self.assertIn(
                "focus_ref", src,
                msg=f"{name} never sets focus_ref from the declared reference.",
            )

    def test_all_chat_surfaces_handle_the_relay_timeout_event(self):
        # The relay emits `event: timeout` at its single-connection cap; generation
        # continues in the background. A surface that ignores it abandons the request and
        # the completed answer never renders until a manual refresh (the reported hang).
        for name in _CHAT_SURFACES:
            src = (_TEMPLATES / name).read_text()
            self.assertIn(
                "'timeout'", src,
                msg=(f"{name} does not handle the relay 'timeout' event — a long "
                     "generation will hang unrendered until the user refreshes."),
            )
