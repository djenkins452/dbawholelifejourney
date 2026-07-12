"""
Tests for the Body Intelligence feature — read-only dashboard, event-driven check-in
(BodyMeasurementSession) grouping, progress photos, and the deterministic composition
service.

Location: apps/health/tests/test_body_intelligence.py
"""

from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.health.models import (
    BodyCompositionEntry,
    BodyMeasurementSession,
    BodyProgressPhoto,
    WeightEntry,
)
from apps.health.services.body_intelligence import build_body_intelligence
from apps.users.models import TermsAcceptance

User = get_user_model()


def create_test_user(email="bi@example.com", password="testpass123"):
    user = User.objects.create_user(email=email, password=password)
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _tiny_png():
    """A 1x1 PNG so ImageField validation passes without Pillow decoding a real file."""
    # Minimal valid PNG bytes.
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
        b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return SimpleUploadedFile("pose.png", png, content_type="image/png")


class BodyMeasurementSessionModelTest(TestCase):
    def setUp(self):
        self.user = create_test_user()

    def test_session_groups_measurement_and_delete_preserves_it(self):
        """Deleting a session must NEVER destroy the underlying measurement (SET_NULL)."""
        session = BodyMeasurementSession.objects.create(user=self.user, title="Q1")
        entry = BodyCompositionEntry.objects.create(
            user=self.user, metric_name="waist", value=Decimal("34.0"),
            unit="in", measurement_date=timezone.now().date(), session=session,
        )
        self.assertEqual(entry.session_id, session.pk)
        self.assertEqual(session.measurement_count, 1)

        # Hard delete the session → measurement survives with session NULL.
        session.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.session_id)
        self.assertTrue(
            BodyCompositionEntry.objects.filter(pk=entry.pk).exists(),
            "Measurement must survive session deletion",
        )

    def test_weight_entry_optional_session_fk(self):
        session = BodyMeasurementSession.objects.create(user=self.user)
        w = WeightEntry.objects.create(user=self.user, value=Decimal("200.0"), session=session)
        self.assertEqual(w.session_id, session.pk)
        session.delete()
        w.refresh_from_db()
        self.assertIsNone(w.session_id)

    def test_legacy_ungrouped_entries_remain_valid(self):
        """Existing rows without a session (NULL) stay valid and queryable."""
        entry = BodyCompositionEntry.objects.create(
            user=self.user, metric_name="chest", value=Decimal("42.0"),
            unit="in", measurement_date=timezone.now().date(),
        )
        self.assertIsNone(entry.session_id)
        self.assertIn(entry, BodyCompositionEntry.objects.filter(user=self.user))


class BodyIntelligenceServiceTest(TestCase):
    def setUp(self):
        self.user = create_test_user()

    def test_empty_state(self):
        bi = build_body_intelligence(self.user)
        self.assertFalse(bi["has_any_data"])
        self.assertIn("headline", bi)

    def test_composes_measurement_snapshot(self):
        today = timezone.now().date()
        earlier = today - timedelta(days=30)
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="waist", value=Decimal("36.0"),
            unit="in", measurement_date=earlier,
        )
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="waist", value=Decimal("34.0"),
            unit="in", measurement_date=today,
        )
        bi = build_body_intelligence(self.user)
        self.assertTrue(bi["has_any_data"])
        waist_rows = [r for r in bi["circumference_rows"] if r["metric"] == "waist"]
        self.assertEqual(len(waist_rows), 1)
        row = waist_rows[0]
        self.assertEqual(row["value"], 34.0)
        self.assertEqual(row["previous"], 36.0)
        self.assertEqual(row["delta"], -2.0)
        # Waist down is an improvement.
        self.assertTrue(row["improved"])

    def test_deterministic(self):
        WeightEntry.objects.create(user=self.user, value=Decimal("210.0"))
        a = build_body_intelligence(self.user)
        b = build_body_intelligence(self.user)
        self.assertEqual(a["headline"], b["headline"])


class BodyIntelligenceCanonicalWeightTest(TestCase):
    """BI must consume the SAME canonical Weight truth as the Weight page — never the
    DailyHealthSummary rollup copy (regression for the '51.0 lb in Body Intelligence
    while the Weight page shows 283.5' gap)."""

    def setUp(self):
        self.user = create_test_user(email="canon@example.com")

    def test_current_weight_is_canonical_not_stale_rollup(self):
        from apps.health.models import DailyHealthSummary

        today = timezone.now().date()
        # Canonical Weight truth: 283.5 lb.
        WeightEntry.objects.create(
            user=self.user, value=Decimal("311.0"), unit="lb",
            recorded_at=timezone.now() - timedelta(days=40),
        )
        WeightEntry.objects.create(
            user=self.user, value=Decimal("283.5"), unit="lb", recorded_at=timezone.now(),
        )
        # A STALE/corrupted rollup that still says 51.0 (as prod had post-contamination).
        DailyHealthSummary.objects.create(
            user=self.user, summary_date=today,
            weight=Decimal("51.0"), body_fat_pct=Decimal("36.8"),
            fat_mass=Decimal("18.77"), lean_mass=Decimal("32.2"),
        )

        bi = build_body_intelligence(self.user)
        # Current snapshot weight must be the canonical 283.5, NOT the rollup's 51.0.
        self.assertEqual(bi["current"]["weight"], 283.5)
        self.assertEqual(bi["body_comp"]["weight"], 283.5)
        # Headline weight matches too.
        self.assertIn("283.5", bi["headline"]["primary"])
        # Weight graph is the canonical WeightEntry series (values are real weights).
        chart_vals = [p["value"] for p in bi["body_comp"]["weight_trend_56d"]]
        self.assertIn(283.5, chart_vals)
        self.assertNotIn(51.0, chart_vals)

    def test_weight_matches_weight_summary_source(self):
        WeightEntry.objects.create(user=self.user, value=Decimal("200.0"), unit="lb")
        from apps.health.services.weight_summary import build_weight_summary
        bi = build_body_intelligence(self.user)
        self.assertEqual(bi["current"]["weight"], build_weight_summary(self.user)["current_lb"])


class BodyCheckInAutoAssociationTest(TestCase):
    """Workflow: a new check-in adopts today's ungrouped measurements + weigh-in."""

    def setUp(self):
        self.user = create_test_user(email="assoc@example.com")
        self.client = Client()
        self.client.force_login(self.user)

    def test_session_create_links_todays_ungrouped(self):
        today = timezone.now().date()
        # Ungrouped measurements + weigh-in already logged today.
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="waist", value=Decimal("34.0"),
            unit="in", measurement_date=today,
        )
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="chest", value=Decimal("42.0"),
            unit="in", measurement_date=today,
        )
        w = WeightEntry.objects.create(user=self.user, value=Decimal("200.0"), unit="lb")

        self.client.post(reverse("health:body_session_create"), {
            "title": "Today", "checked_in_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "source": "manual", "notes": "",
        })
        session = BodyMeasurementSession.objects.get(user=self.user)
        self.assertEqual(
            BodyCompositionEntry.objects.filter(user=self.user, session=session).count(), 2
        )
        w.refresh_from_db()
        self.assertEqual(w.session_id, session.pk)

    def test_does_not_steal_other_sessions_measurements(self):
        today = timezone.now().date()
        other = BodyMeasurementSession.objects.create(user=self.user, title="earlier")
        grouped = BodyCompositionEntry.objects.create(
            user=self.user, metric_name="hips", value=Decimal("40.0"),
            unit="in", measurement_date=today, session=other,
        )
        self.client.post(reverse("health:body_session_create"), {
            "title": "New", "checked_in_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "source": "manual", "notes": "",
        })
        grouped.refresh_from_db()
        self.assertEqual(grouped.session_id, other.pk)  # untouched

    def test_measurement_create_auto_attaches_to_existing_checkin(self):
        session = BodyMeasurementSession.objects.create(user=self.user, title="today")
        self.client.post(reverse("health:body_composition_create"), {
            "metric_name": "waist", "value": "33.0", "unit": "in",
            "measurement_date": timezone.now().date().isoformat(), "source": "manual",
        })
        entry = BodyCompositionEntry.objects.get(user=self.user, metric_name="waist")
        self.assertEqual(entry.session_id, session.pk)


class BodyIntelligenceViewsTest(TestCase):
    def setUp(self):
        self.user = create_test_user()
        self.client = Client()
        self.client.force_login(self.user)

    def test_dashboard_renders(self):
        resp = self.client.get(reverse("health:body_intelligence"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Body Intelligence")

    def test_dashboard_declares_current_context(self):
        resp = self.client.get(reverse("health:body_intelligence"))
        self.assertContains(resp, "summary:health.body_intelligence")

    def test_session_crud_flow(self):
        # Create
        resp = self.client.post(reverse("health:body_session_create"), {
            "title": "Test check-in",
            "checked_in_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "source": "manual",
            "notes": "",
        })
        self.assertEqual(resp.status_code, 302)
        session = BodyMeasurementSession.objects.get(user=self.user)

        # Detail
        detail = self.client.get(reverse("health:body_session_detail", args=[session.pk]))
        self.assertEqual(detail.status_code, 200)

        # Add a measurement into the session via the existing create view.
        self.client.post(
            reverse("health:body_composition_create") + f"?session={session.pk}",
            {"metric_name": "waist", "value": "33.5", "unit": "in",
             "measurement_date": timezone.now().date().isoformat(), "source": "manual"},
        )
        self.assertEqual(
            BodyCompositionEntry.objects.filter(user=self.user, session=session).count(), 1
        )

        # Soft-delete the session.
        self.client.post(reverse("health:body_session_delete", args=[session.pk]))
        session.refresh_from_db()
        self.assertTrue(session.is_deleted)
        # Measurement preserved, now ungrouped.
        entry = BodyCompositionEntry.objects.get(user=self.user, metric_name="waist")
        self.assertIsNone(entry.session_id)

    def test_photo_upload_and_replace(self):
        session = BodyMeasurementSession.objects.create(user=self.user)
        url = reverse("health:body_photo_create", args=[session.pk])
        resp = self.client.post(url, {"pose": "front_relaxed", "image": _tiny_png()})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            BodyProgressPhoto.objects.filter(user=self.user, session=session, pose="front_relaxed").count(),
            1,
        )
        # Upload again for same pose → replace (old soft-deleted).
        self.client.post(url, {"pose": "front_relaxed", "image": _tiny_png()})
        active = BodyProgressPhoto.objects.filter(
            user=self.user, session=session, pose="front_relaxed"
        )
        self.assertEqual(active.count(), 1)

    def test_comparison_view_renders(self):
        resp = self.client.get(reverse("health:body_photo_compare"))
        self.assertEqual(resp.status_code, 200)

    def test_ownership_isolation(self):
        other = create_test_user(email="other@example.com")
        session = BodyMeasurementSession.objects.create(user=other, title="theirs")
        resp = self.client.get(reverse("health:body_session_detail", args=[session.pk]))
        self.assertEqual(resp.status_code, 404)


class WaistHealthKitIngestTest(TestCase):
    """M3 — native HealthKit waistCircumference lands as a canonical BodyCompositionEntry."""

    def setUp(self):
        self.user = create_test_user(email="waist@example.com")

    def test_waist_metric_creates_body_composition_entry(self):
        from apps.mobile.views import process_health_metric

        result = process_health_metric(self.user, {
            "type": "waist", "value": 34.5, "unit": "in",
            "date": "2026-07-12", "sync_id": "w1", "source": "apple_health",
        })
        self.assertEqual(result, "created")
        row = BodyCompositionEntry.objects.get(user=self.user, metric_name="waist")
        self.assertEqual(float(row.value), 34.5)
        self.assertEqual(row.unit, "in")
        self.assertEqual(row.source, "apple_health")

    def test_waist_out_of_range_rejected(self):
        from apps.mobile.views import process_health_metric

        with self.assertRaises(ValueError):
            process_health_metric(self.user, {
                "type": "waist", "value": 999, "date": "2026-07-12",
            })
