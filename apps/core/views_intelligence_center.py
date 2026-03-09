"""
Intelligence Command Center (ICC) — Unified intelligence dashboard.

Aggregates and displays outputs from all intelligence engines:
SAE (state), PGE (guidance), DBE (briefing), WIRE (weekly reports),
DNE (deliveries), PRIE (predictions), with E3 explainability links.

Phase 8: Integrated maturity framework, domain coverage, and proactive
intelligence as the strategic control interface (War Room).

ICC does NOT generate intelligence — it only presents what engines produce.
"""

import logging
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

logger = logging.getLogger(__name__)


@method_decorator(login_required, name="dispatch")
class IntelligenceCommandCenterView(TemplateView):
    """
    Intelligence Command Center — unified view of all engine outputs.

    Information Hierarchy (Phase 8.4):
    Section 1: System Maturity (strategic header)
    Section 2: Domain Coverage
    Section 3: Proactive Intelligence
    Section 4: Current State (SAE)
    Section 5: Active Guidance (PGE)
    Section 6: Daily Briefing (DBE)
    Section 7: Weekly Report (WIRE)
    Section 8: Recent Deliveries (DNE)
    Section 9: Predictions (PRIE)
    Section 10: System Observability (staff only)
    """

    template_name = "intelligence/command_center.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        now = timezone.now()

        # Phase 8.1: System Maturity (strategic header)
        context.update(self._get_maturity_data(user))

        # Phase 8.2: Domain Coverage
        context["domain_coverage"] = self._get_domain_coverage()

        # Phase 8.3: Proactive Intelligence
        context["proactive_stats"] = self._get_proactive_stats(user, now)

        # Section 4: SAE — Current State
        context["user_state"] = self._get_user_state(user)

        # Section 5: PGE — Active Guidance
        context["guidance_items"] = self._get_active_guidance(user, now)
        context["guidance_count"] = len(context["guidance_items"])

        # Section 6: DBE — Daily Briefing
        context["daily_briefing"] = self._get_daily_briefing(user, now)

        # Section 7: WIRE — Weekly Report
        context["weekly_report"] = self._get_weekly_report(user, now)

        # Section 8: DNE — Recent Deliveries
        context["recent_deliveries"] = self._get_recent_deliveries(user)

        # Section 9: PRIE — Predictions
        context["predictions"] = self._get_predictions(user, now)

        # EAE — Executive Arbitration Engine
        context["eae_state"] = self._get_eae_state(user)
        context["eae_recent_decisions"] = self._get_eae_recent_decisions(user)

        # Section 10: Observability (staff only)
        if user.is_staff:
            context["observability_snapshot"] = self._get_observability()
            context["eae_telemetry"] = self._get_eae_telemetry(user)

        # Page metadata
        context["app_name"] = "intelligence"
        context["help_context_id"] = "INTELLIGENCE_COMMAND_CENTER"
        context["page_title"] = "Intelligence Command Center"

        return context

    # =========================================================================
    # Phase 8: Strategic data methods
    # =========================================================================

    def _get_maturity_data(self, user):
        """Phase 8.1: Fetch system maturity scores, recommendations, regressions."""
        result = {
            'maturity_scores': {},
            'maturity_recommendations': [],
            'maturity_regressions': [],
        }
        try:
            from apps.core.ai_observability.maturity_engine import (
                compute_all_maturity_scores,
                generate_recommendations,
                detect_regressions,
            )
            scores = compute_all_maturity_scores(user)
            result['maturity_scores'] = scores
            result['maturity_recommendations'] = generate_recommendations(scores)
            result['maturity_regressions'] = detect_regressions()
        except ImportError:
            logger.debug("ICC: Maturity engine not available")
        except Exception as e:
            logger.warning("ICC: Maturity data failed: %s", e, exc_info=True)
        return result

    def _get_domain_coverage(self):
        """Phase 8.2: Fetch domain registry coverage data."""
        try:
            from apps.core.domain_registry import registry
            return registry.get_coverage_summary()
        except ImportError:
            return []
        except Exception as e:
            logger.debug("ICC: Domain coverage unavailable: %s", e)
            return []

    def _get_proactive_stats(self, user, now):
        """Phase 8.3: Fetch proactive intelligence stats for last 7 days."""
        try:
            from apps.ai.models import AssistantMessage
            seven_days_ago = now - timedelta(days=7)
            proactive_qs = AssistantMessage.objects.filter(
                conversation__user=user,
                is_proactive=True,
                created_at__gte=seven_days_ago,
            )
            total = proactive_qs.count()

            # Count by check-in type from metadata
            by_type = {}
            for msg in proactive_qs.only('metadata'):
                ci_type = (msg.metadata or {}).get('check_in_type', 'other')
                by_type[ci_type] = by_type.get(ci_type, 0) + 1

            return {
                'total_7d': total,
                'by_type': sorted(by_type.items(), key=lambda x: x[1], reverse=True),
            }
        except Exception as e:
            logger.debug("ICC: Proactive stats unavailable: %s", e)
            return {'total_7d': 0, 'by_type': []}

    # =========================================================================
    # Original data methods
    # =========================================================================

    def _get_user_state(self, user):
        """Fetch SAE state snapshot."""
        try:
            from apps.core.ai_state.models import UserState
            return UserState.objects.filter(user=user).first()
        except Exception as e:
            logger.debug(f"ICC: SAE unavailable: {e}")
            return None

    def _get_active_guidance(self, user, now):
        """Fetch active PGE guidance items."""
        try:
            from apps.core.ai_guidance.models import GuidanceItem
            return list(
                GuidanceItem.objects.filter(
                    user=user,
                    is_active=True,
                    dismissed_at__isnull=True,
                ).exclude(
                    snoozed_until__gt=now,
                ).order_by("priority", "-created_at")[:10]
            )
        except Exception as e:
            logger.debug(f"ICC: PGE unavailable: {e}")
            return []

    def _get_daily_briefing(self, user, now):
        """Fetch today's DBE briefing."""
        try:
            from apps.core.ai_briefing.models import DailyBriefing
            return DailyBriefing.objects.filter(
                user=user,
                briefing_date=now.date(),
            ).first()
        except Exception as e:
            logger.debug(f"ICC: DBE unavailable: {e}")
            return None

    def _get_weekly_report(self, user, now):
        """Fetch latest WIRE weekly report."""
        try:
            from apps.core.ai_weekly_report.models import WeeklyIntelligenceReport
            return WeeklyIntelligenceReport.objects.filter(
                user=user,
            ).order_by("-week_start_date").first()
        except Exception as e:
            logger.debug(f"ICC: WIRE unavailable: {e}")
            return None

    def _get_recent_deliveries(self, user):
        """Fetch recent DNE deliveries."""
        try:
            from apps.core.ai_delivery.models import DeliveredNotification
            return list(
                DeliveredNotification.objects.filter(
                    user=user,
                ).order_by("-delivered_at")[:10]
            )
        except Exception as e:
            logger.debug(f"ICC: DNE unavailable: {e}")
            return []

    def _get_predictions(self, user, now):
        """Fetch active PRIE predictions."""
        try:
            from apps.core.ai_predictions.models import Prediction
            return list(
                Prediction.objects.filter(
                    user=user,
                    status="active",
                    predicted_date__gte=now,
                ).order_by("predicted_date")[:10]
            )
        except Exception as e:
            logger.debug(f"ICC: PRIE unavailable: {e}")
            return []

    def _get_eae_state(self, user):
        """Fetch EAE escalation state for current user."""
        try:
            from apps.core.ai_eae.models import EAEState
            from apps.core.ai_eae.constants import ESCALATION_CHOICES, TONE_CHOICES
            state = EAEState.objects.filter(user=user).first()
            if state:
                # Enrich with display labels
                level_map = dict(ESCALATION_CHOICES)
                return {
                    'escalation_level': state.escalation_level,
                    'escalation_label': level_map.get(state.escalation_level, 'Unknown'),
                    'drift_risk_severity': state.drift_risk_severity,
                    'primary_focus_label': state.primary_focus_label or 'None set',
                    'focus_changes_today': state.focus_changes_today,
                    'noise_budget_used_today': state.noise_budget_used_today,
                    'last_arbitration_at': state.last_arbitration_at,
                    'focus_locked': state.focus_locked,
                }
            return None
        except Exception as e:
            logger.debug(f"ICC: EAE state unavailable: {e}")
            return None

    def _get_eae_recent_decisions(self, user):
        """Fetch recent EAE decision logs for audit visibility."""
        try:
            from apps.core.ai_eae.models import EAEDecisionLog
            return list(
                EAEDecisionLog.objects.filter(
                    user=user,
                ).order_by('-created_at')[:5]
            )
        except Exception as e:
            logger.debug(f"ICC: EAE decisions unavailable: {e}")
            return []

    def _get_eae_telemetry(self, user):
        """Fetch EAE telemetry metrics (staff only)."""
        try:
            from apps.core.ai_eae.models import (
                EAEDecisionLog,
                EAEEscalationEvent,
                EAEOverride,
            )
            from django.db.models import Avg, Count, Max

            now = timezone.now()
            last_24h = now - timedelta(hours=24)
            last_7d = now - timedelta(days=7)

            # Decision metrics (24h)
            decisions_24h = EAEDecisionLog.objects.filter(
                user=user, created_at__gte=last_24h,
            )
            decision_stats = decisions_24h.aggregate(
                count=Count('decision_id'),
                avg_duration_ms=Avg('arbitration_duration_ms'),
                avg_surfaced=Avg('surfaced_count'),
                avg_suppressed=Avg('suppressed_count'),
                avg_candidates=Avg('total_candidates'),
            )

            # Escalation events (7d)
            escalation_events = EAEEscalationEvent.objects.filter(
                user=user, created_at__gte=last_7d,
            ).order_by('-created_at')[:10]

            # Active overrides
            overrides = EAEOverride.objects.filter(user=user)

            return {
                'decisions_24h': decision_stats,
                'escalation_events': list(escalation_events.values(
                    'direction', 'from_level', 'to_level',
                    'trigger_reason', 'created_at',
                )),
                'active_overrides': list(overrides.values(
                    'signal_type', 'override_type', 'strike_count',
                    'cooldown_until', 'created_at',
                )),
                'override_count': overrides.count(),
            }
        except Exception as e:
            logger.debug(f"ICC: EAE telemetry unavailable: {e}")
            return None

    def _get_observability(self):
        """Fetch latest IOCD observability snapshot (staff only)."""
        try:
            from apps.core.ai_observability.observability_engine import (
                get_latest_snapshot,
            )
            return get_latest_snapshot()
        except Exception as e:
            logger.debug(f"ICC: IOCD unavailable: {e}")
            return None
