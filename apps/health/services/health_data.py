"""
Health Data Service Layer (Part 3)

Cross-domain read abstraction for:
- Labs (apps.medical.models.LabResult)
- Vitals (apps.health.models: HeartRateEntry, BloodPressureEntry, etc.)
- Body Composition (apps.health.models.BodyCompositionEntry)
- Weight (apps.health.models.WeightEntry)

The Insight Engine and all cross-domain consumers MUST use this service
instead of querying models directly. This creates abstraction and future
scalability.

No cross-domain data duplication. Read-only access.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Max, Min
from django.utils import timezone


# Category mapping for get_metrics_by_category
CATEGORY_MAP = {
    "vitals": [
        "heart_rate", "blood_pressure_systolic", "blood_pressure_diastolic",
        "blood_oxygen", "body_temperature", "respiratory_rate",
    ],
    "weight": ["weight"],
    "body_composition": [
        "body_fat_pct", "lean_mass", "fat_mass", "skeletal_muscle_mass",
        "waist", "chest", "hips", "arm_left", "arm_right",
        "thigh_left", "thigh_right",
    ],
    "labs": ["lab_result"],
    "fitness": ["steps", "workout"],
    "nutrition": ["calories", "water"],
    "sleep": ["sleep_duration", "sleep_quality"],
}


def _normalize_entry(value, unit, date, source, domain, metric_name, raw_obj=None):
    """Create a normalized metric dict."""
    return {
        "metric_name": metric_name,
        "value": float(value) if value is not None else None,
        "unit": unit or "",
        "date": date,
        "source": source or "manual",
        "domain": domain,
    }


class HealthDataService:
    """
    Read-only service layer for cross-domain health data access.

    All methods return normalized dicts — no model instances leak out.
    """

    def __init__(self, user):
        self.user = user

    # ------------------------------------------------------------------
    # Core query methods
    # ------------------------------------------------------------------

    def get_latest_metric(self, metric_name):
        """
        Get the most recent value for a metric across all domains.

        Returns a normalized dict or None.
        """
        fetchers = [
            self._latest_weight,
            self._latest_vital,
            self._latest_body_composition,
            self._latest_lab,
            self._latest_sleep,
            self._latest_steps,
        ]
        for fetcher in fetchers:
            result = fetcher(metric_name)
            if result:
                return result
        return None

    def get_metric_trend(self, metric_name, days=30):
        """
        Get a time-series of values for a metric over the given period.

        Returns list of normalized dicts ordered oldest-first.
        """
        cutoff = timezone.now().date() - timedelta(days=days)
        results = []

        # Weight
        if metric_name == "weight":
            results = self._weight_trend(cutoff)
        # Vitals
        elif metric_name in ("heart_rate", "blood_pressure_systolic",
                             "blood_pressure_diastolic", "blood_oxygen",
                             "body_temperature"):
            results = self._vital_trend(metric_name, cutoff)
        # Body composition
        elif self._is_body_comp_metric(metric_name):
            results = self._body_comp_trend(metric_name, cutoff)
        # Labs
        elif metric_name == "lab_result":
            results = self._lab_trend(cutoff)
        # Sleep
        elif metric_name in ("sleep_duration", "sleep_quality"):
            results = self._sleep_trend(metric_name, cutoff)
        # Steps
        elif metric_name == "steps":
            results = self._steps_trend(cutoff)

        return sorted(results, key=lambda r: r["date"])

    def get_metrics_by_category(self, category):
        """
        Get latest value for each metric in a category.

        Returns list of normalized dicts.
        """
        metric_names = CATEGORY_MAP.get(category, [])
        results = []
        for name in metric_names:
            latest = self.get_latest_metric(name)
            if latest:
                results.append(latest)
        return results

    def get_recent_activity_summary(self, days=7):
        """
        Summary of recent activity across all domains.

        Returns dict with counts and latest values per domain.
        """
        cutoff = timezone.now().date() - timedelta(days=days)
        summary = {}

        # Weight entries count
        from apps.health.models import WeightEntry
        weight_count = WeightEntry.objects.filter(
            user=self.user, recorded_at__date__gte=cutoff
        ).count()
        if weight_count:
            summary["weight"] = {"count": weight_count, "domain": "weight"}

        # Body composition count
        from apps.health.models import BodyCompositionEntry
        bc_count = BodyCompositionEntry.objects.filter(
            user=self.user, measurement_date__gte=cutoff
        ).count()
        if bc_count:
            summary["body_composition"] = {"count": bc_count, "domain": "body_composition"}

        # Vitals (heart rate as proxy)
        from apps.health.models import HeartRateEntry
        hr_count = HeartRateEntry.objects.filter(
            user=self.user, recorded_at__date__gte=cutoff
        ).count()
        if hr_count:
            summary["vitals"] = {"count": hr_count, "domain": "vitals"}

        # Sleep
        from apps.health.models import SleepEntry
        sleep_count = SleepEntry.objects.filter(
            user=self.user, sleep_date__gte=cutoff
        ).count()
        if sleep_count:
            summary["sleep"] = {"count": sleep_count, "domain": "sleep"}

        # Steps
        from apps.health.models import StepsEntry
        steps_count = StepsEntry.objects.filter(
            user=self.user, logged_date__gte=cutoff
        ).count()
        if steps_count:
            summary["steps"] = {"count": steps_count, "domain": "fitness"}

        # Labs
        try:
            from apps.medical.models import LabResult
            lab_count = LabResult.objects.filter(
                user=self.user, collected_at__date__gte=cutoff
            ).count()
            if lab_count:
                summary["labs"] = {"count": lab_count, "domain": "labs"}
        except Exception:
            pass

        return summary

    # ------------------------------------------------------------------
    # Weight
    # ------------------------------------------------------------------

    def _latest_weight(self, metric_name):
        if metric_name != "weight":
            return None
        from apps.health.models import WeightEntry
        entry = WeightEntry.objects.filter(user=self.user).first()
        if not entry:
            return None
        return _normalize_entry(
            entry.value_in_lb, "lb", entry.recorded_at.date(),
            entry.source, "weight", "weight",
        )

    def _weight_trend(self, cutoff):
        from apps.health.models import WeightEntry
        entries = WeightEntry.objects.filter(
            user=self.user, recorded_at__date__gte=cutoff
        ).order_by("recorded_at")
        return [
            _normalize_entry(
                e.value_in_lb, "lb", e.recorded_at.date(),
                e.source, "weight", "weight",
            )
            for e in entries
        ]

    # ------------------------------------------------------------------
    # Vitals
    # ------------------------------------------------------------------

    def _latest_vital(self, metric_name):
        if metric_name == "heart_rate":
            from apps.health.models import HeartRateEntry
            entry = HeartRateEntry.objects.filter(user=self.user).first()
            if not entry:
                return None
            return _normalize_entry(
                entry.bpm, "bpm", entry.recorded_at.date(),
                "manual", "vitals", "heart_rate",
            )
        elif metric_name == "blood_pressure_systolic":
            from apps.health.models import BloodPressureEntry
            entry = BloodPressureEntry.objects.filter(user=self.user).first()
            if not entry:
                return None
            return _normalize_entry(
                entry.systolic, "mmHg", entry.recorded_at.date(),
                "manual", "vitals", "blood_pressure_systolic",
            )
        elif metric_name == "blood_pressure_diastolic":
            from apps.health.models import BloodPressureEntry
            entry = BloodPressureEntry.objects.filter(user=self.user).first()
            if not entry:
                return None
            return _normalize_entry(
                entry.diastolic, "mmHg", entry.recorded_at.date(),
                "manual", "vitals", "blood_pressure_diastolic",
            )
        elif metric_name == "blood_oxygen":
            from apps.health.models import BloodOxygenEntry
            entry = BloodOxygenEntry.objects.filter(user=self.user).first()
            if not entry:
                return None
            return _normalize_entry(
                entry.spo2, "%", entry.recorded_at.date(),
                "manual", "vitals", "blood_oxygen",
            )
        elif metric_name == "body_temperature":
            from apps.health.models import BodyTemperatureEntry
            entry = BodyTemperatureEntry.objects.filter(user=self.user).first()
            if not entry:
                return None
            return _normalize_entry(
                entry.value, entry.unit, entry.recorded_at.date(),
                "manual", "vitals", "body_temperature",
            )
        return None

    def _vital_trend(self, metric_name, cutoff):
        results = []
        if metric_name == "heart_rate":
            from apps.health.models import HeartRateEntry
            for e in HeartRateEntry.objects.filter(
                user=self.user, recorded_at__date__gte=cutoff
            ).order_by("recorded_at"):
                results.append(_normalize_entry(
                    e.bpm, "bpm", e.recorded_at.date(),
                    "manual", "vitals", "heart_rate",
                ))
        elif metric_name in ("blood_pressure_systolic", "blood_pressure_diastolic"):
            from apps.health.models import BloodPressureEntry
            for e in BloodPressureEntry.objects.filter(
                user=self.user, recorded_at__date__gte=cutoff
            ).order_by("recorded_at"):
                val = e.systolic if "systolic" in metric_name else e.diastolic
                results.append(_normalize_entry(
                    val, "mmHg", e.recorded_at.date(),
                    "manual", "vitals", metric_name,
                ))
        elif metric_name == "blood_oxygen":
            from apps.health.models import BloodOxygenEntry
            for e in BloodOxygenEntry.objects.filter(
                user=self.user, recorded_at__date__gte=cutoff
            ).order_by("recorded_at"):
                results.append(_normalize_entry(
                    e.spo2, "%", e.recorded_at.date(),
                    "manual", "vitals", "blood_oxygen",
                ))
        elif metric_name == "body_temperature":
            from apps.health.models import BodyTemperatureEntry
            for e in BodyTemperatureEntry.objects.filter(
                user=self.user, recorded_at__date__gte=cutoff
            ).order_by("recorded_at"):
                results.append(_normalize_entry(
                    e.value, e.unit, e.recorded_at.date(),
                    "manual", "vitals", "body_temperature",
                ))
        return results

    # ------------------------------------------------------------------
    # Body Composition
    # ------------------------------------------------------------------

    def _is_body_comp_metric(self, metric_name):
        from apps.health.models import BODY_COMPOSITION_METRIC_CHOICES
        known = {c[0] for c in BODY_COMPOSITION_METRIC_CHOICES}
        known.discard("custom")
        return metric_name in known

    def _latest_body_composition(self, metric_name):
        if not self._is_body_comp_metric(metric_name):
            return None
        from apps.health.models import BodyCompositionEntry
        entry = BodyCompositionEntry.objects.filter(
            user=self.user, metric_name=metric_name
        ).first()
        if not entry:
            return None
        return _normalize_entry(
            entry.value, entry.unit, entry.measurement_date,
            entry.source, "body_composition", metric_name,
        )

    def _body_comp_trend(self, metric_name, cutoff):
        from apps.health.models import BodyCompositionEntry
        entries = BodyCompositionEntry.objects.filter(
            user=self.user, metric_name=metric_name,
            measurement_date__gte=cutoff,
        ).order_by("measurement_date")
        return [
            _normalize_entry(
                e.value, e.unit, e.measurement_date,
                e.source, "body_composition", metric_name,
            )
            for e in entries
        ]

    # ------------------------------------------------------------------
    # Labs (from apps.medical)
    # ------------------------------------------------------------------

    def _latest_lab(self, metric_name):
        if metric_name != "lab_result":
            return None
        try:
            from apps.medical.models import LabResult
            entry = LabResult.objects.filter(user=self.user).order_by("-collected_at").first()
            if not entry:
                return None
            return _normalize_entry(
                entry.value_numeric, entry.unit, entry.collected_at.date(),
                "lab", "labs", entry.raw_test_name,
            )
        except Exception:
            return None

    def _lab_trend(self, cutoff):
        results = []
        try:
            from apps.medical.models import LabResult
            for e in LabResult.objects.filter(
                user=self.user, collected_at__date__gte=cutoff
            ).order_by("collected_at"):
                if e.value_numeric is not None:
                    results.append(_normalize_entry(
                        e.value_numeric, e.unit, e.collected_at.date(),
                        "lab", "labs", e.raw_test_name,
                    ))
        except Exception:
            pass
        return results

    # ------------------------------------------------------------------
    # Sleep
    # ------------------------------------------------------------------

    def _latest_sleep(self, metric_name):
        if metric_name not in ("sleep_duration", "sleep_quality"):
            return None
        from apps.health.models import SleepEntry
        entry = SleepEntry.objects.filter(user=self.user).order_by("-sleep_date").first()
        if not entry:
            return None
        if metric_name == "sleep_duration":
            val = entry.total_duration_minutes
            return _normalize_entry(
                val, "min", entry.sleep_date,
                entry.source, "sleep", "sleep_duration",
            )
        else:
            val = entry.quality_score if hasattr(entry, "quality_score") else None
            return _normalize_entry(
                val, "score", entry.sleep_date,
                entry.source, "sleep", "sleep_quality",
            )

    def _sleep_trend(self, metric_name, cutoff):
        from apps.health.models import SleepEntry
        results = []
        for e in SleepEntry.objects.filter(
            user=self.user, sleep_date__gte=cutoff
        ).order_by("sleep_date"):
            if metric_name == "sleep_duration":
                val = e.total_duration_minutes
                results.append(_normalize_entry(
                    val, "min", e.sleep_date,
                    e.source, "sleep", "sleep_duration",
                ))
            else:
                val = e.quality_score if hasattr(e, "quality_score") else None
                if val is not None:
                    results.append(_normalize_entry(
                        val, "score", e.sleep_date,
                        e.source, "sleep", "sleep_quality",
                    ))
        return results

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _latest_steps(self, metric_name):
        if metric_name != "steps":
            return None
        from apps.health.models import StepsEntry
        entry = StepsEntry.objects.filter(user=self.user).order_by("-logged_date").first()
        if not entry:
            return None
        return _normalize_entry(
            entry.count, "steps", entry.logged_date,
            entry.source, "fitness", "steps",
        )

    def _steps_trend(self, cutoff):
        from apps.health.models import StepsEntry
        results = []
        for e in StepsEntry.objects.filter(
            user=self.user, logged_date__gte=cutoff
        ).order_by("logged_date"):
            results.append(_normalize_entry(
                e.count, "steps", e.logged_date,
                e.source, "fitness", "steps",
            ))
        return results

    # ------------------------------------------------------------------
    # Aggregate helpers for the insight engine
    # ------------------------------------------------------------------

    def get_weight_entries_count(self, days=30):
        """Return count of weight entries in period."""
        from apps.health.models import WeightEntry
        cutoff = timezone.now().date() - timedelta(days=days)
        return WeightEntry.objects.filter(
            user=self.user, recorded_at__date__gte=cutoff
        ).count()

    def get_body_comp_entries_count(self, days=30):
        """Return count of body composition entries in period."""
        from apps.health.models import BodyCompositionEntry
        cutoff = timezone.now().date() - timedelta(days=days)
        return BodyCompositionEntry.objects.filter(
            user=self.user, measurement_date__gte=cutoff
        ).count()

    def get_body_comp_metrics_logged(self):
        """Return distinct metric names the user has logged."""
        from apps.health.models import BodyCompositionEntry
        return list(
            BodyCompositionEntry.objects.filter(user=self.user)
            .values_list("metric_name", flat=True)
            .distinct()
        )
