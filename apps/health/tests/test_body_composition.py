"""
Tests for Body Composition, Health Profile, Insight Engine, and Health Data Service.

Location: apps/health/tests/test_body_composition.py
"""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.health.models import (
    BODY_COMPOSITION_METRIC_CHOICES,
    BodyCompositionEntry,
    HealthProfile,
    InsightResult,
    WeightEntry,
)
from apps.health.services.health_data import HealthDataService
from apps.health.services.insight_engine import InsightEngine
from apps.users.models import TermsAcceptance

User = get_user_model()


def create_test_user(email="test@example.com", password="testpass123"):
    """Create a test user with onboarding + terms completed."""
    user = User.objects.create_user(email=email, password=password)
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# =========================================================================
# Model Tests
# =========================================================================


class BodyCompositionEntryModelTest(TestCase):
    """Tests for BodyCompositionEntry model."""

    def setUp(self):
        self.user = create_test_user()

    def test_create_entry(self):
        entry = BodyCompositionEntry.objects.create(
            user=self.user,
            metric_name="body_fat_pct",
            value=Decimal("18.5"),
            unit="pct",
            measurement_date=date.today(),
        )
        self.assertEqual(entry.value, Decimal("18.5"))
        self.assertEqual(entry.metric_name, "body_fat_pct")

    def test_str_representation(self):
        entry = BodyCompositionEntry.objects.create(
            user=self.user,
            metric_name="lean_mass",
            value=Decimal("155.0"),
            unit="lb",
            measurement_date=date.today(),
        )
        self.assertIn("Lean Mass", str(entry))
        self.assertIn("155.0", str(entry))

    def test_get_metric_display_known(self):
        entry = BodyCompositionEntry(metric_name="waist")
        self.assertEqual(entry.get_metric_display(), "Waist")

    def test_get_metric_display_custom(self):
        entry = BodyCompositionEntry(metric_name="my_custom_metric")
        self.assertEqual(entry.get_metric_display(), "my_custom_metric")

    def test_ordering(self):
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="waist",
            value=Decimal("32"), measurement_date=date.today() - timedelta(days=5),
        )
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="waist",
            value=Decimal("31.5"), measurement_date=date.today(),
        )
        entries = list(BodyCompositionEntry.objects.filter(user=self.user))
        self.assertEqual(entries[0].value, Decimal("31.5"))  # newest first

    def test_soft_delete(self):
        entry = BodyCompositionEntry.objects.create(
            user=self.user, metric_name="chest",
            value=Decimal("42"), measurement_date=date.today(),
        )
        entry.soft_delete()
        self.assertEqual(BodyCompositionEntry.objects.filter(user=self.user).count(), 0)
        self.assertEqual(
            BodyCompositionEntry.all_objects.filter(user=self.user).count(), 1
        )

    def test_custom_metric_name(self):
        entry = BodyCompositionEntry.objects.create(
            user=self.user,
            metric_name="neck_circumference",
            value=Decimal("15.5"),
            unit="in",
            measurement_date=date.today(),
        )
        self.assertEqual(entry.metric_name, "neck_circumference")

    def test_source_choices(self):
        entry = BodyCompositionEntry.objects.create(
            user=self.user, metric_name="body_fat_pct",
            value=Decimal("20"), measurement_date=date.today(),
            source="dexa_scan",
        )
        self.assertEqual(entry.source, "dexa_scan")


class HealthProfileModelTest(TestCase):
    """Tests for HealthProfile model."""

    def setUp(self):
        self.user = create_test_user()

    def test_create_profile(self):
        profile = HealthProfile.objects.create(
            user=self.user,
            height_inches=Decimal("70"),
            activity_level="moderately_active",
        )
        self.assertEqual(profile.height_inches, Decimal("70"))
        self.assertEqual(profile.activity_level, "moderately_active")

    def test_height_feet_inches(self):
        profile = HealthProfile(height_inches=Decimal("70"))
        self.assertEqual(profile.height_feet_inches, (5, 10.0))

    def test_height_display(self):
        profile = HealthProfile(height_inches=Decimal("70"))
        self.assertEqual(profile.height_display, "5'10\"")

    def test_height_cm(self):
        profile = HealthProfile(height_inches=Decimal("70"))
        self.assertAlmostEqual(profile.height_cm, 177.8, places=1)

    def test_height_none(self):
        profile = HealthProfile(height_inches=None)
        self.assertIsNone(profile.height_feet_inches)
        self.assertEqual(profile.height_display, "")
        self.assertIsNone(profile.height_cm)

    def test_str(self):
        profile = HealthProfile.objects.create(user=self.user)
        self.assertIn(self.user.email, str(profile))


class InsightResultModelTest(TestCase):
    """Tests for InsightResult model."""

    def setUp(self):
        self.user = create_test_user()

    def test_create_insight(self):
        insight = InsightResult.objects.create(
            user=self.user,
            insight_type="trend",
            text="Weight declining over 6 weeks.",
            related_domains=["weight"],
            confidence_score=Decimal("0.85"),
        )
        self.assertEqual(insight.insight_type, "trend")
        self.assertFalse(insight.is_dismissed)

    def test_dismiss_insight(self):
        insight = InsightResult.objects.create(
            user=self.user,
            insight_type="gap",
            text="No entries logged.",
            related_domains=["body_composition"],
            confidence_score=Decimal("0.90"),
        )
        insight.is_dismissed = True
        insight.save()
        self.assertTrue(insight.is_dismissed)

    def test_str(self):
        insight = InsightResult.objects.create(
            user=self.user,
            insight_type="correlation",
            text="Lean mass stable during weight reduction.",
            related_domains=["weight", "body_composition"],
            confidence_score=Decimal("0.75"),
        )
        self.assertIn("[correlation]", str(insight))


# =========================================================================
# View Tests
# =========================================================================


class BodyCompositionViewTests(TestCase):
    """Tests for body composition views."""

    def setUp(self):
        self.user = create_test_user()
        self.client = Client()
        self.client.login(email="test@example.com", password="testpass123")

    def test_list_view(self):
        response = self.client.get(reverse("health:body_composition_list"))
        self.assertEqual(response.status_code, 200)

    def test_list_view_with_entries(self):
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="body_fat_pct",
            value=Decimal("20"), unit="pct",
            measurement_date=date.today(),
        )
        response = self.client.get(reverse("health:body_composition_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "20")

    def test_list_view_metric_filter(self):
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="waist",
            value=Decimal("32"), measurement_date=date.today(),
        )
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="chest",
            value=Decimal("42"), measurement_date=date.today(),
        )
        response = self.client.get(
            reverse("health:body_composition_list") + "?metric=waist"
        )
        self.assertEqual(response.status_code, 200)

    def test_create_view_get(self):
        response = self.client.get(reverse("health:body_composition_create"))
        self.assertEqual(response.status_code, 200)

    def test_create_view_post(self):
        response = self.client.post(
            reverse("health:body_composition_create"),
            {
                "metric_name": "body_fat_pct",
                "value": "18.5",
                "unit": "pct",
                "measurement_date": date.today().isoformat(),
                "source": "manual",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(BodyCompositionEntry.objects.count(), 1)

    def test_create_custom_metric(self):
        response = self.client.post(
            reverse("health:body_composition_create"),
            {
                "metric_name": "custom",
                "custom_metric_name": "grip_strength",
                "value": "95",
                "unit": "lb",
                "measurement_date": date.today().isoformat(),
                "source": "manual",
            },
        )
        self.assertEqual(response.status_code, 302)
        entry = BodyCompositionEntry.objects.first()
        self.assertEqual(entry.metric_name, "grip_strength")

    def test_update_view(self):
        entry = BodyCompositionEntry.objects.create(
            user=self.user, metric_name="waist",
            value=Decimal("32"), measurement_date=date.today(),
        )
        response = self.client.get(
            reverse("health:body_composition_update", args=[entry.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_delete_view(self):
        entry = BodyCompositionEntry.objects.create(
            user=self.user, metric_name="waist",
            value=Decimal("32"), measurement_date=date.today(),
        )
        response = self.client.post(
            reverse("health:body_composition_delete", args=[entry.pk])
        )
        self.assertEqual(response.status_code, 302)
        # Soft deleted
        self.assertEqual(BodyCompositionEntry.objects.count(), 0)

    def test_unauthenticated_redirect(self):
        self.client.logout()
        response = self.client.get(reverse("health:body_composition_list"))
        self.assertEqual(response.status_code, 302)


class HealthProfileViewTests(TestCase):
    """Tests for health profile view."""

    def setUp(self):
        self.user = create_test_user()
        self.client = Client()
        self.client.login(email="test@example.com", password="testpass123")

    def test_profile_get(self):
        response = self.client.get(reverse("health:health_profile"))
        self.assertEqual(response.status_code, 200)

    def test_profile_creates_on_first_visit(self):
        self.assertFalse(HealthProfile.objects.filter(user=self.user).exists())
        self.client.get(reverse("health:health_profile"))
        self.assertTrue(HealthProfile.objects.filter(user=self.user).exists())

    def test_profile_update(self):
        response = self.client.post(
            reverse("health:health_profile"),
            {
                "height_feet": "5",
                "height_remaining_inches": "10",
                "activity_level": "moderately_active",
                "weight_goal_unit": "lb",
            },
        )
        self.assertEqual(response.status_code, 302)
        profile = HealthProfile.objects.get(user=self.user)
        self.assertEqual(profile.height_inches, 70)
        self.assertEqual(profile.activity_level, "moderately_active")


class InsightViewTests(TestCase):
    """Tests for insight views."""

    def setUp(self):
        self.user = create_test_user()
        self.client = Client()
        self.client.login(email="test@example.com", password="testpass123")

    def test_list_view(self):
        response = self.client.get(reverse("health:insights_list"))
        self.assertEqual(response.status_code, 200)

    def test_list_shows_disclaimer(self):
        response = self.client.get(reverse("health:insights_list"))
        self.assertContains(response, "not medical advice")

    def test_refresh_creates_insights(self):
        response = self.client.post(reverse("health:insights_refresh"))
        self.assertEqual(response.status_code, 302)

    def test_dismiss_insight(self):
        insight = InsightResult.objects.create(
            user=self.user,
            insight_type="trend",
            text="Test insight.",
            related_domains=["weight"],
            confidence_score=Decimal("0.85"),
        )
        response = self.client.post(
            reverse("health:insights_dismiss", args=[insight.pk])
        )
        self.assertEqual(response.status_code, 302)
        insight.refresh_from_db()
        self.assertTrue(insight.is_dismissed)


# =========================================================================
# Health Data Service Tests
# =========================================================================


class HealthDataServiceTest(TestCase):
    """Tests for the cross-domain Health Data Service."""

    def setUp(self):
        self.user = create_test_user()
        self.service = HealthDataService(self.user)

    def test_get_latest_weight(self):
        WeightEntry.objects.create(
            user=self.user, value=Decimal("185"), unit="lb",
        )
        result = self.service.get_latest_metric("weight")
        self.assertIsNotNone(result)
        self.assertEqual(result["metric_name"], "weight")
        self.assertEqual(result["value"], 185.0)
        self.assertEqual(result["domain"], "weight")

    def test_get_latest_weight_none(self):
        result = self.service.get_latest_metric("weight")
        self.assertIsNone(result)

    def test_get_latest_body_comp(self):
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="body_fat_pct",
            value=Decimal("18.5"), unit="pct",
            measurement_date=date.today(),
        )
        result = self.service.get_latest_metric("body_fat_pct")
        self.assertIsNotNone(result)
        self.assertEqual(result["domain"], "body_composition")

    def test_weight_trend(self):
        for i in range(5):
            WeightEntry.objects.create(
                user=self.user,
                value=Decimal(str(185 - i)),
                unit="lb",
                recorded_at=timezone.now() - timedelta(days=5 * i),
            )
        trend = self.service.get_metric_trend("weight", days=30)
        self.assertEqual(len(trend), 5)
        # Oldest first
        self.assertTrue(trend[0]["date"] <= trend[-1]["date"])

    def test_body_comp_trend(self):
        for i in range(3):
            BodyCompositionEntry.objects.create(
                user=self.user, metric_name="waist",
                value=Decimal(str(34 - i * 0.5)),
                unit="in",
                measurement_date=date.today() - timedelta(days=10 * i),
            )
        trend = self.service.get_metric_trend("waist", days=30)
        self.assertEqual(len(trend), 3)

    def test_get_metrics_by_category_weight(self):
        WeightEntry.objects.create(
            user=self.user, value=Decimal("185"), unit="lb",
        )
        results = self.service.get_metrics_by_category("weight")
        self.assertEqual(len(results), 1)

    def test_get_recent_activity_summary(self):
        WeightEntry.objects.create(
            user=self.user, value=Decimal("185"), unit="lb",
        )
        summary = self.service.get_recent_activity_summary(days=7)
        self.assertIn("weight", summary)

    def test_get_body_comp_entries_count(self):
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="waist",
            value=Decimal("32"), measurement_date=date.today(),
        )
        count = self.service.get_body_comp_entries_count(days=30)
        self.assertEqual(count, 1)

    def test_get_body_comp_metrics_logged(self):
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="waist",
            value=Decimal("32"), measurement_date=date.today(),
        )
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="chest",
            value=Decimal("42"), measurement_date=date.today(),
        )
        metrics = self.service.get_body_comp_metrics_logged()
        self.assertEqual(len(metrics), 2)
        self.assertIn("waist", metrics)
        self.assertIn("chest", metrics)

    def test_normalized_output_format(self):
        """Verify all outputs follow normalized dict format."""
        WeightEntry.objects.create(
            user=self.user, value=Decimal("185"), unit="lb",
        )
        result = self.service.get_latest_metric("weight")
        required_keys = {"metric_name", "value", "unit", "date", "source", "domain"}
        self.assertEqual(set(result.keys()), required_keys)


# =========================================================================
# Insight Engine Tests
# =========================================================================


class InsightEngineTest(TestCase):
    """Tests for the Insight Engine service."""

    def setUp(self):
        self.user = create_test_user()
        self.engine = InsightEngine(self.user)

    def test_generate_no_data(self):
        """No data = no insights (except potentially gaps)."""
        count = self.engine.generate_insights()
        self.assertEqual(count, 0)  # No prior data to detect gaps from

    def test_weight_trend_decline(self):
        """Weight declining over 6 weeks generates trend insight."""
        # Create entries where older entries are heavier (declining over time)
        for i in range(10):
            WeightEntry.objects.create(
                user=self.user,
                value=Decimal(str(182 + i * 2)),  # older = heavier
                unit="lb",
                recorded_at=timezone.now() - timedelta(days=4 * i),
            )
        count = self.engine.generate_insights()
        self.assertGreater(count, 0)
        trends = InsightResult.objects.filter(
            user=self.user, insight_type="trend",
        )
        self.assertTrue(trends.exists())
        texts = " ".join([t.text for t in trends])
        self.assertIn("declined", texts)

    def test_weight_stable(self):
        """Stable weight generates stable insight."""
        for i in range(5):
            WeightEntry.objects.create(
                user=self.user,
                value=Decimal("185"),
                unit="lb",
                recorded_at=timezone.now() - timedelta(days=7 * i),
            )
        self.engine.generate_insights()
        trends = InsightResult.objects.filter(
            user=self.user, insight_type="trend",
        )
        texts = [t.text for t in trends]
        self.assertTrue(any("stable" in t for t in texts))

    def test_body_comp_trend(self):
        """Body composition trends generate insights."""
        for i in range(4):
            BodyCompositionEntry.objects.create(
                user=self.user, metric_name="body_fat_pct",
                value=Decimal(str(22 - i * 0.5)),
                unit="pct",
                measurement_date=date.today() - timedelta(days=10 * i),
            )
        self.engine.generate_insights()
        # Check for body_composition insights (SQLite-compatible approach)
        bc_insights = [
            i for i in InsightResult.objects.filter(user=self.user)
            if "body_composition" in i.related_domains
        ]
        self.assertTrue(len(bc_insights) > 0)

    def test_logging_gap_weight(self):
        """Old weight entry + no recent = gap insight."""
        WeightEntry.objects.create(
            user=self.user, value=Decimal("185"), unit="lb",
            recorded_at=timezone.now() - timedelta(days=60),
        )
        self.engine.generate_insights()
        gaps = [
            i for i in InsightResult.objects.filter(user=self.user, insight_type="gap")
            if "weight" in i.related_domains
        ]
        self.assertTrue(len(gaps) > 0)

    def test_logging_gap_body_comp(self):
        """Old body comp entry + no recent = gap insight."""
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="waist",
            value=Decimal("32"),
            measurement_date=date.today() - timedelta(days=60),
        )
        self.engine.generate_insights()
        gaps = [
            i for i in InsightResult.objects.filter(user=self.user, insight_type="gap")
            if "body_composition" in i.related_domains
        ]
        self.assertTrue(len(gaps) > 0)

    def test_extreme_value_insight(self):
        """Rapid weight loss generates caloric modeling insight."""
        # 5 lb/week loss over 3 weeks
        for i in range(4):
            WeightEntry.objects.create(
                user=self.user,
                value=Decimal(str(200 - i * 5)),
                unit="lb",
                recorded_at=timezone.now() - timedelta(days=7 * i),
            )
        self.engine.generate_insights()
        extreme = InsightResult.objects.filter(
            user=self.user, text__icontains="commonly referenced",
        )
        self.assertTrue(extreme.exists())
        # Verify NO judgment language
        for insight in extreme:
            self.assertNotIn("unsafe", insight.text.lower())
            self.assertNotIn("dangerous", insight.text.lower())
            self.assertNotIn("harmful", insight.text.lower())
            self.assertNotIn("you should", insight.text.lower())

    def test_insights_are_descriptive_only(self):
        """All generated insights must be descriptive, not directive."""
        for i in range(10):
            WeightEntry.objects.create(
                user=self.user,
                value=Decimal(str(182 + i * 2)),  # older = heavier
                unit="lb",
                recorded_at=timezone.now() - timedelta(days=4 * i),
            )
        self.engine.generate_insights()
        for insight in InsightResult.objects.filter(user=self.user):
            text_lower = insight.text.lower()
            self.assertNotIn("you should", text_lower)
            self.assertNotIn("recommend", text_lower)
            self.assertNotIn("unsafe", text_lower)
            self.assertNotIn("dangerous", text_lower)
            self.assertNotIn("harmful", text_lower)

    def test_confidence_score_range(self):
        """Confidence scores must be between 0 and 1."""
        for i in range(5):
            WeightEntry.objects.create(
                user=self.user,
                value=Decimal(str(185 - i)),
                unit="lb",
                recorded_at=timezone.now() - timedelta(days=7 * i),
            )
        self.engine.generate_insights()
        for insight in InsightResult.objects.filter(user=self.user):
            self.assertGreaterEqual(insight.confidence_score, Decimal("0"))
            self.assertLessEqual(insight.confidence_score, Decimal("1"))

    def test_related_domains_not_empty(self):
        """Every insight must have at least one related domain."""
        WeightEntry.objects.create(
            user=self.user, value=Decimal("185"), unit="lb",
            recorded_at=timezone.now() - timedelta(days=60),
        )
        self.engine.generate_insights()
        for insight in InsightResult.objects.filter(user=self.user):
            self.assertTrue(len(insight.related_domains) > 0)

    def test_refresh_alias(self):
        """refresh_insights() works as alias for generate_insights()."""
        count = self.engine.refresh_insights()
        self.assertEqual(count, 0)


# =========================================================================
# Form Tests
# =========================================================================


class BodyCompositionFormTest(TestCase):
    """Tests for body composition form."""

    def setUp(self):
        self.user = create_test_user()

    def test_valid_form(self):
        from apps.health.forms import BodyCompositionEntryForm
        form = BodyCompositionEntryForm(data={
            "metric_name": "body_fat_pct",
            "value": "18.5",
            "unit": "pct",
            "measurement_date": date.today().isoformat(),
            "source": "manual",
        }, user=self.user)
        self.assertTrue(form.is_valid())

    def test_custom_metric_requires_name(self):
        from apps.health.forms import BodyCompositionEntryForm
        form = BodyCompositionEntryForm(data={
            "metric_name": "custom",
            "custom_metric_name": "",
            "value": "10",
            "measurement_date": date.today().isoformat(),
        }, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("custom_metric_name", form.errors)

    def test_custom_metric_replaces_name(self):
        from apps.health.forms import BodyCompositionEntryForm
        form = BodyCompositionEntryForm(data={
            "metric_name": "custom",
            "custom_metric_name": "grip_strength",
            "value": "95",
            "unit": "lb",
            "measurement_date": date.today().isoformat(),
            "source": "manual",
        }, user=self.user)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["metric_name"], "grip_strength")


class HealthProfileFormTest(TestCase):
    """Tests for health profile form."""

    def setUp(self):
        self.user = create_test_user()
        self.profile = HealthProfile.objects.create(user=self.user)

    def test_valid_form(self):
        from apps.health.forms import HealthProfileForm
        form = HealthProfileForm(
            data={
                "height_feet": "5",
                "height_remaining_inches": "10",
                "activity_level": "moderately_active",
                "weight_goal_unit": "lb",
            },
            instance=self.profile,
        )
        self.assertTrue(form.is_valid())
        saved = form.save()
        self.assertEqual(saved.height_inches, 70)

    def test_empty_height_ok(self):
        from apps.health.forms import HealthProfileForm
        form = HealthProfileForm(
            data={"activity_level": "sedentary", "weight_goal_unit": "lb"},
            instance=self.profile,
        )
        self.assertTrue(form.is_valid())

    def test_weight_goal_saved(self):
        """Weight goal fields save to HealthProfile."""
        from apps.health.forms import HealthProfileForm
        form = HealthProfileForm(
            data={
                "activity_level": "moderately_active",
                "weight_goal": "180",
                "weight_goal_unit": "lb",
                "weight_goal_target_date": "2026-06-01",
            },
            instance=self.profile,
        )
        self.assertTrue(form.is_valid())
        saved = form.save()
        self.assertEqual(float(saved.weight_goal), 180.0)
        self.assertEqual(saved.weight_goal_unit, "lb")

    def test_clear_weight_goal(self):
        """Clearing weight goal field sets it to None."""
        from apps.health.forms import HealthProfileForm
        self.profile.weight_goal = 200
        self.profile.save()
        form = HealthProfileForm(
            data={
                "activity_level": "sedentary",
                "weight_goal": "",
                "weight_goal_unit": "lb",
            },
            instance=self.profile,
        )
        self.assertTrue(form.is_valid())
        saved = form.save()
        self.assertIsNone(saved.weight_goal)
