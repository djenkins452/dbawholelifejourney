"""
Celebration Detection Service — detects meaningful progress and creates
PreparedCelebration records.

Runs as a nightly Celery task. Checks multiple trigger types with
cooldown enforcement to prevent celebration fatigue.

Key rule: "earned celebration, not constant praise."
"""

import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.utils import get_user_today

logger = logging.getLogger(__name__)

# Cooldown periods per celebration type (minimum days between same type)
COOLDOWNS = {
    "streak_milestone": 7,
    "goal_milestone": 0,
    "weekly_discipline": 7,
    "momentum_surge": 14,
    "health_breakthrough": 7,
    "consistency_pattern": 14,
    "cross_domain": 14,
}

# Streak milestones worth celebrating
STREAK_THRESHOLDS = [7, 14, 21, 30, 60, 90, 180, 365]

# Celebration narrative templates
TEMPLATES = {
    "streak_milestone": {
        "headline": "{days}-Day Streak: {habit_name}",
        "narrative": (
            "You've maintained your {habit_name} habit for {days} consecutive days. "
            "That's {weeks} weeks of consistent effort. The discipline you've built "
            "here compounds over time."
        ),
    },
    "goal_milestone": {
        "headline": "Milestone Reached: {milestone_title}",
        "narrative": (
            'You completed "{milestone_title}" on your "{goal_title}" goal. '
            "You're now at {progress}% overall progress. Keep building on this momentum."
        ),
    },
    "weekly_discipline": {
        "headline": "Strong Week: {score}% Execution",
        "narrative": (
            "This past week you completed {score}% of your daily commitments. "
            "Your strongest areas: {top_areas}. This level of consistency "
            "is what drives real transformation."
        ),
    },
    "momentum_surge": {
        "headline": "Momentum Surge: {goal_title}",
        "narrative": (
            'Your momentum on "{goal_title}" jumped from {old_score} to {new_score} '
            "this week. Key drivers: {drivers}. You're clearly investing more effort here."
        ),
    },
    "health_breakthrough": {
        "headline": "Health Milestone: {detail}",
        "narrative": "{detail_narrative}",
    },
    "consistency_pattern": {
        "headline": "{weeks} Weeks of Consistency",
        "narrative": (
            "You've maintained a daily execution average of {avg_score}% for "
            "{weeks} consecutive weeks. This kind of sustained discipline is rare "
            "and powerful."
        ),
    },
    "cross_domain": {
        "headline": "Cross-Domain Momentum",
        "narrative": (
            "You're showing strong momentum across {domain_count} life domains "
            "simultaneously: {domain_names}. This holistic progress is the essence "
            "of Whole Life Journey."
        ),
    },
}


class CelebrationDetectionService:
    """Detects meaningful progress and creates PreparedCelebration records."""

    def __init__(self, user):
        self.user = user
        self.today = get_user_today(user)

    def detect_and_store(self):
        """Main entry point. Check all triggers, create celebrations."""
        celebrations = []

        for checker in [
            self._check_streak_milestones,
            self._check_goal_milestones,
            self._check_weekly_discipline,
            self._check_momentum_surge,
            self._check_health_breakthroughs,
            self._check_consistency_pattern,
            self._check_cross_domain,
        ]:
            try:
                results = checker()
                celebrations.extend(results)
            except Exception:
                logger.error("Celebration check %s failed", checker.__name__, exc_info=True)

        # Store celebrations (max 1 new ready celebration)
        if celebrations:
            self._store_best(celebrations)

    def get_ready_celebration(self):
        """Get the highest-priority ready celebration for display."""
        from apps.dashboard_v2.models import PreparedCelebration

        return (
            PreparedCelebration.objects.filter(
                user=self.user,
                celebration_status="ready",
                expires_at__gt=timezone.now(),
            )
            .order_by("-generated_at")
            .first()
        )

    def _check_streak_milestones(self):
        """Check if any habit streak hit a milestone threshold."""
        results = []
        try:
            from apps.purpose.models import HabitGoal
            from apps.purpose.services.streak_service import get_streak_data

            habits = HabitGoal.objects.filter(user=self.user, status="active")
            for habit in habits:
                try:
                    streak = get_streak_data(habit)
                    if streak.current in STREAK_THRESHOLDS:
                        dedupe = f"{self.user.pk}:streak:{habit.pk}:{streak.current}"
                        if not self._is_in_cooldown("streak_milestone", dedupe):
                            results.append({
                                "type": "streak_milestone",
                                "dedupe_key": dedupe,
                                "domain": "",
                                "related_goal": None,
                                "headline": TEMPLATES["streak_milestone"]["headline"].format(
                                    days=streak.current,
                                    habit_name=habit.name,
                                ),
                                "narrative": TEMPLATES["streak_milestone"]["narrative"].format(
                                    days=streak.current,
                                    habit_name=habit.name,
                                    weeks=streak.current // 7,
                                ),
                                "evidence": {
                                    "habit_id": habit.pk,
                                    "habit_name": habit.name,
                                    "streak_days": streak.current,
                                },
                            })
                except Exception:
                    continue
        except ImportError:
            pass
        return results

    def _check_goal_milestones(self):
        """Check for recently completed goal milestones."""
        results = []
        try:
            from apps.purpose.models import GoalMilestone

            recent = GoalMilestone.objects.filter(
                goal__user=self.user,
                completed=True,
                completed_date=self.today,
            ).select_related("goal")

            for milestone in recent:
                dedupe = f"{self.user.pk}:milestone:{milestone.pk}"
                if not self._is_in_cooldown("goal_milestone", dedupe):
                    results.append({
                        "type": "goal_milestone",
                        "dedupe_key": dedupe,
                        "domain": milestone.goal.domain.slug if milestone.goal.domain else "",
                        "related_goal": milestone.goal,
                        "headline": TEMPLATES["goal_milestone"]["headline"].format(
                            milestone_title=milestone.title,
                        ),
                        "narrative": TEMPLATES["goal_milestone"]["narrative"].format(
                            milestone_title=milestone.title,
                            goal_title=milestone.goal.title,
                            progress=milestone.goal.milestone_progress_percent,
                        ),
                        "evidence": {
                            "milestone_id": milestone.pk,
                            "milestone_title": milestone.title,
                            "goal_id": milestone.goal.pk,
                            "progress": milestone.goal.milestone_progress_percent,
                        },
                    })
        except ImportError:
            pass
        return results

    def _check_weekly_discipline(self):
        """Check if 7-day average DailyProgressSnapshot score >= 80."""
        results = []
        try:
            from apps.dashboard_v2.models import DailyProgressSnapshot

            cutoff = self.today - timedelta(days=7)
            snapshots = DailyProgressSnapshot.objects.filter(
                user=self.user,
                snapshot_date__gte=cutoff,
                snapshot_date__lte=self.today,
            ).values_list("overall_score", flat=True)

            if len(snapshots) >= 5:  # Need at least 5 days of data
                avg = round(sum(snapshots) / len(snapshots))
                if avg >= 80:
                    dedupe = f"{self.user.pk}:weekly_disc:{self.today.isocalendar()[1]}"
                    if not self._is_in_cooldown("weekly_discipline", dedupe):
                        results.append({
                            "type": "weekly_discipline",
                            "dedupe_key": dedupe,
                            "domain": "",
                            "related_goal": None,
                            "headline": TEMPLATES["weekly_discipline"]["headline"].format(score=avg),
                            "narrative": TEMPLATES["weekly_discipline"]["narrative"].format(
                                score=avg,
                                top_areas="routines, medicine, tasks",
                            ),
                            "evidence": {"avg_score": avg, "days": len(snapshots)},
                        })
        except Exception:
            logger.error("Weekly discipline check failed", exc_info=True)
        return results

    def _check_momentum_surge(self):
        """Check if any goal's 7d momentum avg increased by 20+ points."""
        results = []
        try:
            from apps.dashboard_v2.models import GoalMomentumSnapshot
            from apps.purpose.models import LifeGoal

            goals = LifeGoal.objects.filter(user=self.user, status="active")
            for goal in goals:
                cutoff_current = self.today - timedelta(days=7)
                cutoff_prior = self.today - timedelta(days=14)

                current_scores = list(
                    GoalMomentumSnapshot.objects.filter(
                        user=self.user,
                        goal=goal,
                        snapshot_date__gte=cutoff_current,
                    ).values_list("momentum_score", flat=True)
                )
                prior_scores = list(
                    GoalMomentumSnapshot.objects.filter(
                        user=self.user,
                        goal=goal,
                        snapshot_date__gte=cutoff_prior,
                        snapshot_date__lt=cutoff_current,
                    ).values_list("momentum_score", flat=True)
                )

                if current_scores and prior_scores:
                    current_avg = sum(current_scores) / len(current_scores)
                    prior_avg = sum(prior_scores) / len(prior_scores)
                    if current_avg - prior_avg >= 20:
                        dedupe = f"{self.user.pk}:surge:{goal.pk}:{self.today.isocalendar()[1]}"
                        if not self._is_in_cooldown("momentum_surge", dedupe):
                            results.append({
                                "type": "momentum_surge",
                                "dedupe_key": dedupe,
                                "domain": goal.domain.slug if goal.domain else "",
                                "related_goal": goal,
                                "headline": TEMPLATES["momentum_surge"]["headline"].format(
                                    goal_title=goal.title,
                                ),
                                "narrative": TEMPLATES["momentum_surge"]["narrative"].format(
                                    goal_title=goal.title,
                                    old_score=round(prior_avg),
                                    new_score=round(current_avg),
                                    drivers="increased habit consistency and task completion",
                                ),
                                "evidence": {
                                    "goal_id": goal.pk,
                                    "prior_avg": round(prior_avg),
                                    "current_avg": round(current_avg),
                                },
                            })
        except Exception:
            logger.error("Momentum surge check failed", exc_info=True)
        return results

    def _check_health_breakthroughs(self):
        """Check for new personal records or weight milestones."""
        results = []
        try:
            from apps.health.models import PersonalRecord

            recent_prs = PersonalRecord.objects.filter(
                user=self.user,
                date_achieved=self.today,
            )
            for pr in recent_prs:
                dedupe = f"{self.user.pk}:pr:{pr.pk}"
                if not self._is_in_cooldown("health_breakthrough", dedupe):
                    results.append({
                        "type": "health_breakthrough",
                        "dedupe_key": dedupe,
                        "domain": "health",
                        "related_goal": None,
                        "headline": TEMPLATES["health_breakthrough"]["headline"].format(
                            detail=f"New PR: {pr.exercise_name}",
                        ),
                        "narrative": TEMPLATES["health_breakthrough"]["narrative"].format(
                            detail_narrative=f"You set a new personal record for {pr.exercise_name}. Keep pushing your limits.",
                        ),
                        "evidence": {"pr_id": pr.pk, "exercise": pr.exercise_name},
                    })
        except (ImportError, Exception):
            logger.debug("Health breakthrough check skipped or failed")
        return results

    def _check_consistency_pattern(self):
        """Check for N consecutive weeks with avg progress >= 70."""
        results = []
        try:
            from apps.dashboard_v2.models import DailyProgressSnapshot

            # Check last 4 weeks
            consecutive_weeks = 0
            for week_offset in range(4):
                week_end = self.today - timedelta(days=7 * week_offset)
                week_start = week_end - timedelta(days=6)
                scores = list(
                    DailyProgressSnapshot.objects.filter(
                        user=self.user,
                        snapshot_date__gte=week_start,
                        snapshot_date__lte=week_end,
                    ).values_list("overall_score", flat=True)
                )
                if scores and sum(scores) / len(scores) >= 70:
                    consecutive_weeks += 1
                else:
                    break

            if consecutive_weeks >= 3:
                dedupe = f"{self.user.pk}:consistency:{consecutive_weeks}w:{self.today.isocalendar()[1]}"
                if not self._is_in_cooldown("consistency_pattern", dedupe):
                    results.append({
                        "type": "consistency_pattern",
                        "dedupe_key": dedupe,
                        "domain": "",
                        "related_goal": None,
                        "headline": TEMPLATES["consistency_pattern"]["headline"].format(
                            weeks=consecutive_weeks,
                        ),
                        "narrative": TEMPLATES["consistency_pattern"]["narrative"].format(
                            weeks=consecutive_weeks,
                            avg_score=70,
                        ),
                        "evidence": {"consecutive_weeks": consecutive_weeks},
                    })
        except Exception:
            logger.error("Consistency pattern check failed", exc_info=True)
        return results

    def _check_cross_domain(self):
        """Check if momentum >= 60 in 3+ domains simultaneously."""
        results = []
        try:
            from apps.dashboard_v2.services.momentum_service import GoalMomentumService

            service = GoalMomentumService(self.user)
            momentum_data = service.get_all_momentum()

            strong_domains = [
                m for m in momentum_data if m["momentum"] >= 60
            ]
            unique_domains = {m["domain_slug"] for m in strong_domains}

            if len(unique_domains) >= 3:
                domain_names = ", ".join(sorted(m["domain"] for m in strong_domains))
                dedupe = f"{self.user.pk}:cross_domain:{self.today.isocalendar()[1]}"
                if not self._is_in_cooldown("cross_domain", dedupe):
                    results.append({
                        "type": "cross_domain",
                        "dedupe_key": dedupe,
                        "domain": "",
                        "related_goal": None,
                        "headline": TEMPLATES["cross_domain"]["headline"],
                        "narrative": TEMPLATES["cross_domain"]["narrative"].format(
                            domain_count=len(unique_domains),
                            domain_names=domain_names,
                        ),
                        "evidence": {
                            "domains": list(unique_domains),
                            "domain_count": len(unique_domains),
                        },
                    })
        except Exception:
            logger.error("Cross-domain check failed", exc_info=True)
        return results

    def _is_in_cooldown(self, celebration_type, dedupe_key):
        """Check if this celebration type/key is in cooldown."""
        from apps.dashboard_v2.models import PreparedCelebration

        cooldown_days = COOLDOWNS.get(celebration_type, 7)
        if cooldown_days == 0:
            # Check exact dedupe key only
            return PreparedCelebration.objects.filter(
                user=self.user,
                dedupe_key=dedupe_key,
            ).exists()

        cutoff = timezone.now() - timedelta(days=cooldown_days)
        return PreparedCelebration.objects.filter(
            user=self.user,
            celebration_type=celebration_type,
            generated_at__gte=cutoff,
        ).exists()

    def _store_best(self, celebrations):
        """Store the best celebration from candidates. Max 1 ready at a time."""
        from apps.dashboard_v2.models import PreparedCelebration

        # Priority order (higher index = more celebration-worthy)
        priority = [
            "streak_milestone",
            "weekly_discipline",
            "consistency_pattern",
            "health_breakthrough",
            "momentum_surge",
            "cross_domain",
            "goal_milestone",
        ]

        celebrations.sort(key=lambda c: priority.index(c["type"]) if c["type"] in priority else 0)
        best = celebrations[-1]

        # Expire any existing ready celebrations
        PreparedCelebration.objects.filter(
            user=self.user,
            celebration_status="ready",
        ).update(celebration_status="expired")

        PreparedCelebration.objects.create(
            user=self.user,
            celebration_type=best["type"],
            celebration_status="ready",
            headline=best["headline"],
            narrative=best["narrative"],
            evidence=best["evidence"],
            domain=best.get("domain", ""),
            related_goal=best.get("related_goal"),
            expires_at=timezone.now() + timedelta(days=7),
            dedupe_key=best["dedupe_key"],
        )
