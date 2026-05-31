"""Quick-log hydration buttons on the dashboard.

Three static buttons in `templates/dashboard_v3/sections/utilities.html`
post to the existing `health:water_quick_log` endpoint. This file proves:

  - The three buttons render on the dashboard
  - Each button posts the exact amount + drink_type that its label promises
    (Trust contract: button label number = stored WaterEntry.amount)
  - The existing hydration coefficient logic (effective_oz) is preserved —
    the new buttons do NOT change hydration math
"""

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.health.models import WaterEntry
from apps.users.models import TermsAcceptance


User = get_user_model()


def _make_user(email="quicklog@test.com"):
    u = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=u,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class QuickLogHydrationButtonRenderTests(TestCase):
    """Buttons must be present on the dashboard so the one-tap UX exists."""

    def setUp(self):
        self.user = _make_user()
        self.client = Client()
        self.client.force_login(self.user)
        # Seed a water entry so the utilities section renders at all
        # (gated by `{% if utilities.water %}`).
        from apps.core.utils import get_user_today
        WaterEntry.objects.create(
            user=self.user, amount=Decimal("8"), unit="oz",
            drink_type="water", logged_date=get_user_today(self.user),
        )

    def test_water_button_renders_on_dashboard(self):
        resp = self.client.get(reverse("dashboard_v3:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("+8 oz Water", resp.content.decode())

    def test_coffee_button_renders_on_dashboard(self):
        resp = self.client.get(reverse("dashboard_v3:home"))
        self.assertIn("+8 oz Coffee", resp.content.decode())

    def test_electrolytes_button_renders_on_dashboard(self):
        resp = self.client.get(reverse("dashboard_v3:home"))
        self.assertIn("+16 oz Electrolytes", resp.content.decode())


class QuickLogHydrationEndpointTests(TestCase):
    """Hitting the endpoint with the exact params each button sends must
    create a WaterEntry whose amount + drink_type match the button label.
    The hydration coefficient logic must be preserved unchanged."""

    def setUp(self):
        self.user = _make_user("endpoint@test.com")
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse("health:water_quick_log")

    def test_post_water_quick_creates_water_entry_with_exact_amount(self):
        """Trust contract — '+8 oz Water' label ⇒ amount=8.0, drink_type=water."""
        resp = self.client.post(self.url, {
            "preset": "8", "drink_type": "water", "next": "/dashboard/",
        })
        # 302 to /dashboard/ on success (non-AJAX path).
        self.assertIn(resp.status_code, (200, 302))

        entries = WaterEntry.objects.filter(user=self.user, drink_type="water")
        self.assertEqual(entries.count(), 1)
        entry = entries.first()
        self.assertEqual(float(entry.amount), 8.0)
        self.assertEqual(entry.unit, "oz")
        self.assertEqual(entry.drink_type, "water")

    def test_post_coffee_quick_creates_coffee_entry(self):
        """Trust contract — '+8 oz Coffee' label ⇒ amount=8.0, drink_type=coffee."""
        self.client.post(self.url, {
            "preset": "8", "drink_type": "coffee", "next": "/dashboard/",
        })
        entries = WaterEntry.objects.filter(user=self.user, drink_type="coffee")
        self.assertEqual(entries.count(), 1)
        entry = entries.first()
        self.assertEqual(float(entry.amount), 8.0)
        self.assertEqual(entry.drink_type, "coffee")

    def test_post_electrolyte_quick_creates_entry_and_preserves_hydration_math(self):
        """Trust contract — '+16 oz Electrolytes' label ⇒ amount=16.0,
        drink_type=electrolyte. AND the existing hydration coefficient
        (1.05 for electrolyte) is preserved unchanged on the displayed
        daily total: 16 × 1.05 = 16.8 effective oz."""
        from apps.core.utils import get_user_today
        self.client.post(self.url, {
            "preset": "16", "drink_type": "electrolyte", "next": "/dashboard/",
        })

        entry = WaterEntry.objects.get(
            user=self.user, drink_type="electrolyte",
        )
        # Stored amount equals the label number — no hidden conversion.
        self.assertEqual(float(entry.amount), 16.0)

        # Hydration coefficient logic intact — effective contribution
        # uses the existing 1.05 multiplier from WaterEntry.HYDRATION_COEFFICIENTS.
        self.assertAlmostEqual(entry.effective_oz, 16.8, places=1)

        # Daily total reflects coefficient — proves we did NOT regress
        # the existing hydration math.
        total = WaterEntry.get_daily_total(self.user, get_user_today(self.user))
        self.assertAlmostEqual(float(total), 16.8, places=1)
