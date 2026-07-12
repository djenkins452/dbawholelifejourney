"""SAE state JSON must never contain Decimal/date objects.

Regression for the deploy failure in migration 0102 →
`rebuild_user_state` → `UserState.save()`:
    TypeError: Object of type Decimal is not JSON serializable

Builders can leak a Decimal (e.g. build_finance_state does
`round(g.progress_percentage, 1)`, and `round(Decimal, n)` returns a Decimal).
Rather than cast at every builder, the canonical serialization boundary
(`UserState.save` → `to_json_safe`) normalises state_data to JSON-native types.
"""
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.ai_state.models import UserState, to_json_safe
from apps.users.models import TermsAcceptance

User = get_user_model()


class StateJsonBoundaryTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="jsonb@example.com", password="x" * 12)
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        )

    def test_to_json_safe_normalises_types(self):
        out = to_json_safe({
            "d": Decimal("33.3"),
            "dt": datetime(2026, 7, 12, 8, 15),
            "day": date(2026, 7, 12),
            "nested": [{"x": Decimal("1.5")}, (Decimal("2.0"),)],
            "keep": {"i": 3, "f": 1.2, "s": "ok", "b": True, "n": None},
        })
        self.assertIsInstance(out["d"], float)
        self.assertEqual(out["d"], 33.3)
        self.assertEqual(out["dt"], "2026-07-12T08:15:00")
        self.assertEqual(out["day"], "2026-07-12")
        self.assertIsInstance(out["nested"][0]["x"], float)
        self.assertIsInstance(out["nested"][1][0], float)
        # JSON-native values pass through unchanged (incl. bool, not coerced to float).
        self.assertIs(out["keep"]["b"], True)
        self.assertEqual(out["keep"]["i"], 3)

    def test_save_sanitizes_decimal_in_state_data(self):
        us, _ = UserState.objects.get_or_create(user=self.user)
        # A Decimal deep in state_data (as a leaking builder would produce).
        us.state_data = {"finance": {"goals": [{"progress_pct": Decimal("33.3")}]}}
        us.save()  # must NOT raise "Decimal is not JSON serializable"
        us.refresh_from_db()
        self.assertIsInstance(
            us.state_data["finance"]["goals"][0]["progress_pct"], float
        )

    def test_state_data_is_json_serializable_after_save(self):
        import json
        us, _ = UserState.objects.get_or_create(user=self.user)
        us.state_data = {"a": Decimal("1.1"), "b": date(2026, 1, 1)}
        us.save()
        us.refresh_from_db()
        json.dumps(us.state_data)  # no error → genuinely JSON-native
