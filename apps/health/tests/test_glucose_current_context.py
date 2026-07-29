"""Current Context for the GLUCOSE page — Defect #1 of the overnight-lows milestone.

The Glucose dashboard was a BLIND page: a bare TemplateView declaring no Current
Context, so "look at this page" resolved to no focus and the assistant could not see
the readings on screen. It now adopts PageSummaryMixin (`summary:health.glucose`); the
provider resolves to build_glucose_page_summary → glucose_reading_window (the ONE
intra-day producer), so the assistant answers "look at this page" and "my lows
overnight" from the SAME deterministic reading truth the page renders — no retrieval.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.ai.cos_services.current_context import get_current_context_baseline
from apps.core.current_context import resolve_current_context
from apps.health.models import GlucoseEntry

User = get_user_model()

GLUCOSE_URL = "/health/physical/glucose/"
GLUCOSE_REF = "summary:health.glucose"


class GlucoseCurrentContextTests(TestCase):
    def setUp(self):
        self.user = self._mk_user("gcc@example.com")
        self.now = timezone.now()
        # A trailing run of 5-min CGM readings ending ~2 min ago, incl. extreme lows.
        vals = [120, 100, 85, 68, 67, 65, 64, 61, 58, 55, 50, 50, 49, 48, 41, 60, 90, 112]
        for i, v in enumerate(vals):
            GlucoseEntry.objects.create(
                user=self.user, value=Decimal(str(v)), unit="mg/dL", context="cgm",
                source="dexcom",
                recorded_at=self.now - timedelta(minutes=(len(vals) - i) * 5),
            )
        self.client = Client()
        self.client.force_login(self.user)

    def _mk_user(self, email):
        u = User.objects.create_user(email=email, password="pw12345!")
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=u, terms_version=settings.WLJ_SETTINGS["TERMS_VERSION"])
        u.preferences.has_completed_onboarding = True
        u.preferences.save()
        return u

    # -- the page is no longer blind: it declares the overview summary ---------
    def test_glucose_page_emits_page_summary_meta(self):
        resp = self.client.get(GLUCOSE_URL)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('name="wlj-context"', html)
        self.assertIn(f'content="{GLUCOSE_REF}"', html)

    # -- the reference resolves to deterministic facts incl. the actual lows ---
    def test_summary_ref_resolves_with_individual_lows(self):
        summ = resolve_current_context(self.user, ref=GLUCOSE_REF)
        self.assertIsNotNone(summ)
        self.assertEqual(summ["title"], "Glucose")
        self.assertEqual(summ["kind"], "glucose overview")
        content = summ["content"]
        self.assertIn("Latest reading", content)
        self.assertIn("Below 70", content)
        self.assertIn("Low readings", content)
        # the extreme lows the user was pointing at are literally present
        self.assertIn("41", content)
        self.assertIn("48", content)

    # -- it lands in the envelope as authoritative current-request focus -------
    def test_summary_is_current_request_focus_in_envelope(self):
        cc = get_current_context_baseline(
            self.user, page_context={"url": GLUCOSE_URL, "focus_ref": GLUCOSE_REF})
        focus = cc["current_screen"]["focus"]
        self.assertIsNotNone(focus)
        self.assertEqual(focus["authority"], "current_request")
        self.assertEqual(focus["source"], "canonical")
        self.assertIn("Glucose", focus["content"])
        self.assertIn("41", focus["content"])   # the low is IN the executive envelope

    # -- "what happened overnight" is answerable VERBATIM from Current Context --
    def test_overnight_segment_present_so_no_retrieval_needed(self):
        """The page summary carries an explicit local 12 AM–6 AM segment, so
        'what happened overnight' is answered from Current Context (precedence #1),
        never a get_readings retrieval. Data is placed inside the overnight window."""
        u = self._mk_user("overnight-gcc@example.com")
        from apps.core.utils import get_user_now
        now = get_user_now(u)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        vals = [88, 80, 72, 68, 65, 61, 58, 55, 50, 49, 48, 41]
        start = midnight + timedelta(hours=2)     # 2:00 AM onward — in 00:00–06:00
        for i, v in enumerate(vals):
            GlucoseEntry.objects.create(
                user=u, value=Decimal(str(v)), unit="mg/dL", context="cgm",
                source="dexcom", recorded_at=start + timedelta(minutes=5 * i))
        content = resolve_current_context(u, ref=GLUCOSE_REF)["content"]
        self.assertIn("Overnight (12 AM–6 AM)", content)
        self.assertIn("below 70", content)
        self.assertIn("severe", content)          # 41/48/49/50 < 54
        self.assertIn("41", content)              # the extreme low, with its time

    # -- strictly user-scoped (ownership boundary) -----------------------------
    def test_summary_is_user_scoped(self):
        other = self._mk_user("other-gcc@example.com")
        GlucoseEntry.objects.create(user=other, value=Decimal("142"), unit="mg/dL",
                                    context="cgm", source="dexcom",
                                    recorded_at=self.now - timedelta(minutes=3))
        content = resolve_current_context(other, ref=GLUCOSE_REF)["content"]
        self.assertIn("142", content)           # other user's own reading
        self.assertNotIn("41", content)         # never self.user's lows

    # -- empty state degrades gracefully ---------------------------------------
    def test_empty_glucose_summary(self):
        empty = self._mk_user("empty-gcc@example.com")
        summ = resolve_current_context(empty, ref=GLUCOSE_REF)
        self.assertIsNotNone(summ)
        self.assertIn("no readings", summ["content"].lower())
