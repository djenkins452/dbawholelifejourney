"""
ISE — Scheduler Runner.

Task runner functions that call existing intelligence engines.
Each function wraps an engine's public API — no logic duplication.
"""

import logging

from apps.core.ai_observability.trace import trace_context
from apps.users.models import User

logger = logging.getLogger(__name__)


def _get_active_ai_users():
    """
    Get all active users with AI enabled.

    Returns:
        QuerySet of User instances.
    """
    return User.objects.filter(
        is_active=True,
        preferences__ai_enabled=True,
    ).select_related("preferences")


def run_daily_briefings():
    """
    Generate daily briefings for all active AI users.

    Calls DBE generate_daily_briefing() for each user.

    Returns:
        dict — {generated: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.ai_briefing.briefing_engine import generate_daily_briefing
        except ImportError:
            logger.error("ISE: DBE not available (import failed)")
            return {"generated": 0, "errors": 0}

        users = _get_active_ai_users()
        generated = 0
        errors = 0

        for user in users:
            try:
                result = generate_daily_briefing(user)
                if result:
                    generated += 1
            except Exception as e:
                errors += 1
                logger.error(f"ISE: DBE failed for user {user.id}: {e}")

        logger.info(f"ISE: Daily briefings — generated={generated}, errors={errors}")
        return {"generated": generated, "errors": errors}


def run_learning_profile_updates():
    """
    Recalculate GLOE learning profiles for all active AI users.

    Calls GLOE update_learning_profile() for each user.

    Returns:
        dict — {updated: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.ai_guidance_learning.learning_engine import update_learning_profile
        except ImportError:
            logger.error("ISE: GLOE not available (import failed)")
            return {"updated": 0, "errors": 0}

        users = _get_active_ai_users()
        updated = 0
        errors = 0

        for user in users:
            try:
                update_learning_profile(user)
                updated += 1
            except Exception as e:
                errors += 1
                logger.error(f"ISE: GLOE failed for user {user.id}: {e}")

        logger.info(f"ISE: Learning profiles — updated={updated}, errors={errors}")
        return {"updated": updated, "errors": errors}


def run_guidance_refresh():
    """
    Refresh proactive guidance for all active AI users.

    Calls PGE generate_guidance() for each user.
    Also expires old guidance items.

    Returns:
        dict — {refreshed: int, expired: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.ai_guidance.guidance_engine import (
                expire_old_guidance,
                generate_guidance,
            )
        except ImportError:
            logger.error("ISE: PGE not available (import failed)")
            return {"refreshed": 0, "expired": 0, "errors": 0}

        # Step 1: Expire old guidance globally
        expired = expire_old_guidance()

        # Step 2: Generate fresh guidance per user
        users = _get_active_ai_users()
        refreshed = 0
        errors = 0

        for user in users:
            try:
                items = generate_guidance(user)
                if items:
                    refreshed += 1
            except Exception as e:
                errors += 1
                logger.error(f"ISE: PGE failed for user {user.id}: {e}")

        logger.info(
            f"ISE: Guidance refresh — refreshed={refreshed}, "
            f"expired={expired}, errors={errors}"
        )
        return {"refreshed": refreshed, "expired": expired or 0, "errors": errors}


def run_weekly_reports():
    """
    Generate weekly intelligence reports for all active AI users.

    Calls WIRE generate_weekly_report() for each user.

    Returns:
        dict — {generated: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.ai_weekly_report.report_engine import generate_weekly_report
        except ImportError:
            logger.error("ISE: WIRE not available (import failed)")
            return {"generated": 0, "errors": 0}

        users = _get_active_ai_users()
        generated = 0
        errors = 0

        for user in users:
            try:
                result = generate_weekly_report(user)
                if result:
                    generated += 1
            except Exception as e:
                errors += 1
                logger.error(f"ISE: WIRE failed for user {user.id}: {e}")

        logger.info(f"ISE: Weekly reports — generated={generated}, errors={errors}")
        return {"generated": generated, "errors": errors}


def run_delivery_cycle():
    """
    Run one cycle of the Delivery & Notification Engine.

    Calls DNE deliver_due_notifications() to route intelligence
    outputs to user-configured channels.

    Returns:
        dict — {delivered: int, skipped: int, failed: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.ai_delivery.delivery_engine import deliver_due_notifications
        except ImportError:
            logger.error("ISE: DNE not available (import failed)")
            return {"delivered": 0, "skipped": 0, "failed": 0}

        result = deliver_due_notifications()
        logger.info(
            f"ISE: Delivery cycle — delivered={result['delivered']}, "
            f"skipped={result['skipped']}, failed={result['failed']}"
        )
        return result


def run_quality_metrics_aggregation():
    """
    Aggregate ICQG quality metrics for all rule/domain combinations.

    Calls ICQG aggregate_weekly_metrics() to compute usefulness scores.

    Returns:
        dict — {created: int, updated: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.ai_quality.quality_metrics import aggregate_weekly_metrics
        except ImportError:
            logger.error("ISE: ICQG not available (import failed)")
            return {"created": 0, "updated": 0, "errors": 0}

        result = aggregate_weekly_metrics()
        logger.info(
            f"ISE: Quality metrics — created={result['created']}, "
            f"updated={result['updated']}, errors={result['errors']}"
        )
        return result


def run_observability_snapshot():
    """
    Generate daily intelligence observability metrics snapshot.

    Calls IOCD generate_daily_snapshot() — system-wide, not per-user.

    Returns:
        dict — {generated: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.ai_observability.observability_engine import (
                generate_daily_snapshot,
            )
        except ImportError:
            logger.error("ISE: IOCD not available (import failed)")
            return {"generated": 0, "errors": 0}

        result = generate_daily_snapshot()
        if result:
            logger.info(f"ISE: Observability snapshot generated for {result.snapshot_date}")
            return {"generated": 1, "errors": 0}
        else:
            logger.warning("ISE: Observability snapshot generation failed")
            return {"generated": 0, "errors": 1}


def run_architecture_pass():
    """
    Run nightly architecture pass for all active AI users.

    Calls the CoS Architecture Engine to build tomorrow's plan for each user.
    Also runs drift prediction update and creates a nudge intervention
    so the user knows their tomorrow plan is ready.

    Returns:
        dict — {generated: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.blueprint.architecture_engine import run_architecture_pass as arch_pass
        except ImportError:
            logger.error("ISE: Architecture engine not available (import failed)")
            return {"generated": 0, "errors": 0}

        users = _get_active_ai_users()
        generated = 0
        errors = 0

        for user in users:
            try:
                # Only run if auto_architect is enabled in blueprint
                from apps.core.blueprint.engine import get_blueprint
                blueprint = get_blueprint(user)
                if not blueprint.auto_architect_enabled:
                    continue

                plan = arch_pass(user)
                generated += 1

                # Update drift prediction alongside architecture
                try:
                    from apps.core.blueprint.drift_engine import predict_drift_probability
                    predict_drift_probability(user)
                except Exception:
                    pass

                # Notify user that their plan is ready (nudge level)
                try:
                    from apps.core.blueprint.intervention_engine import create_intervention
                    from apps.core.blueprint.models import InterventionLog
                    block_count = plan.blocks.count() if plan else 0
                    if block_count > 0:
                        warnings = plan.risk_warnings or []
                        msg = f"Tomorrow's architecture is ready: {block_count} blocks planned."
                        if warnings:
                            msg += f" {len(warnings)} risk warning(s) flagged."
                        create_intervention(
                            user=user,
                            level=InterventionLog.LEVEL_NUDGE,
                            trigger_type='architecture_ready',
                            message=msg,
                            delivered_via='in_app',
                        )
                except Exception:
                    pass

            except Exception as e:
                logger.warning(f"ISE: Architecture pass failed for {user.email}: {e}")
                errors += 1

        logger.info(f"ISE: Architecture pass completed — generated={generated}, errors={errors}")
        return {"generated": generated, "errors": errors}


def run_drift_scoring():
    """
    Compute daily drift scores and predictions for all active AI users.

    Returns:
        dict — {scored: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.blueprint.drift_engine import (
                compute_daily_drift_score,
                predict_drift_probability,
            )
        except ImportError:
            logger.error("ISE: Drift engine not available (import failed)")
            return {"scored": 0, "errors": 0}

        users = _get_active_ai_users()
        scored = 0
        errors = 0

        for user in users:
            try:
                compute_daily_drift_score(user)
                predict_drift_probability(user)
                scored += 1
            except Exception as e:
                logger.warning(f"ISE: Drift scoring failed for {user.email}: {e}")
                errors += 1

        logger.info(f"ISE: Drift scoring completed — scored={scored}, errors={errors}")
        return {"scored": scored, "errors": errors}


def run_assistant_triggers():
    """
    Check and execute assistant trigger conditions for all active AI users.

    Returns:
        dict — {checked: int, triggered: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.blueprint.assistant_triggers import execute_all_triggers
        except ImportError:
            logger.error("ISE: Assistant triggers not available (import failed)")
            return {"checked": 0, "triggered": 0, "errors": 0}

        users = _get_active_ai_users()
        checked = 0
        triggered = 0
        errors = 0

        for user in users:
            try:
                interventions = execute_all_triggers(user)
                checked += 1
                triggered += len(interventions)
            except Exception as e:
                logger.warning(f"ISE: Trigger check failed for {user.email}: {e}")
                errors += 1

        logger.info(
            f"ISE: Trigger check completed — checked={checked}, triggered={triggered}, errors={errors}"
        )
        return {"checked": checked, "triggered": triggered, "errors": errors}


def run_weekly_pressure():
    """
    Compute weekly pressure forecasts for all active PA users.

    Returns:
        dict — {computed: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.blueprint.weekly_pressure import compute_weekly_pressure
        except ImportError:
            logger.error("ISE: Weekly pressure engine not available (import failed)")
            return {"computed": 0, "errors": 0}

        users = _get_active_ai_users().filter(
            preferences__personal_assistant_enabled=True,
        )
        computed = 0
        errors = 0

        for user in users:
            try:
                compute_weekly_pressure(user)
                computed += 1
            except Exception as e:
                logger.warning(f"ISE: Weekly pressure failed for {user.email}: {e}")
                errors += 1

        logger.info(
            f"ISE: Weekly pressure completed — computed={computed}, errors={errors}"
        )
        return {"computed": computed, "errors": errors}


def run_reflection_queue():
    """
    Scan previous day's events and queue post-event reflections for all
    active PA users with event_reflections_enabled.

    Also expires stale reflections.

    Returns:
        dict — {queued: int, expired: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.blueprint.reflection_engine import (
                detect_reflectable_events,
                expire_stale_reflections,
                queue_reflection,
            )
        except ImportError:
            logger.error("ISE: Reflection engine not available (import failed)")
            return {"queued": 0, "expired": 0, "errors": 0}

        # Step 1: Expire stale reflections globally
        expired = expire_stale_reflections()

        # Step 2: Queue new reflections per user
        users = _get_active_ai_users().filter(
            preferences__personal_assistant_enabled=True,
        )
        queued = 0
        errors = 0

        for user in users:
            try:
                events = detect_reflectable_events(user)
                for event_dict in events:
                    queue_reflection(user, event_dict)
                    queued += 1
            except Exception as e:
                logger.warning(f"ISE: Reflection queue failed for {user.email}: {e}")
                errors += 1

        logger.info(
            f"ISE: Reflection queue completed — queued={queued}, "
            f"expired={expired}, errors={errors}"
        )
        return {"queued": queued, "expired": expired, "errors": errors}


def run_relational_drift():
    """
    Detect relational drift for all users with relationship_suggestions_enabled.

    Generates GuidanceItem via PGE for each drift alert.

    Returns:
        dict — {checked: int, alerts: int, guidance_created: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.ai_relationships.relationship_engine import (
                detect_relational_drift,
                generate_relationship_suggestion,
            )
        except ImportError:
            logger.error("ISE: Relationship engine not available (import failed)")
            return {"checked": 0, "alerts": 0, "guidance_created": 0, "errors": 0}

        users = _get_active_ai_users().filter(
            preferences__personal_assistant_enabled=True,
        )
        checked = 0
        total_alerts = 0
        guidance_created = 0
        errors = 0

        for user in users:
            try:
                alerts = detect_relational_drift(user)
                checked += 1
                total_alerts += len(alerts)

                # Create guidance items for top alerts (max 2 per user)
                for alert in alerts[:2]:
                    try:
                        suggestion = generate_relationship_suggestion(user, alert)
                        _create_relational_guidance(user, suggestion)
                        guidance_created += 1
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"ISE: Relational drift failed for {user.email}: {e}")
                errors += 1

        logger.info(
            f"ISE: Relational drift completed — checked={checked}, "
            f"alerts={total_alerts}, guidance={guidance_created}, errors={errors}"
        )
        return {
            "checked": checked,
            "alerts": total_alerts,
            "guidance_created": guidance_created,
            "errors": errors,
        }


def _create_relational_guidance(user, suggestion):
    """Create a GuidanceItem from a relationship suggestion."""
    try:
        from apps.core.ai_guidance.models import GuidanceItem
        from django.utils import timezone
        import datetime

        # Dedupe: don't create if similar guidance exists in last 7 days
        recent = GuidanceItem.objects.filter(
            user=user,
            guidance_type='relational_drift',
            evidence__person_id=suggestion.get('person_id'),
            created_at__gte=timezone.now() - datetime.timedelta(days=7),
        ).exists()

        if not recent:
            GuidanceItem.objects.create(
                user=user,
                title=suggestion['title'],
                message=suggestion['message'],
                priority=4,  # Low priority (non-intrusive)
                guidance_type='relational_drift',
                source='composite',
                module='relationships',
                evidence={
                    'person_id': suggestion.get('person_id'),
                    'suggestion_type': suggestion.get('suggestion_type'),
                },
                expires_at=timezone.now() + datetime.timedelta(days=14),
            )
    except (ImportError, Exception) as e:
        logger.debug("Relational guidance creation failed: %s", e)


# =========================================================================
# PHASE 4 — FEEDBACK LOOP RUNNERS
# =========================================================================


def run_prediction_validation():
    """
    Validate expired predictions against actual outcomes for all active users.

    Calls PredictionValidator.validate_expired_predictions() per user.

    Returns:
        dict — {validated: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.ai_feedback.prediction_validator import validate_expired_predictions
        except ImportError:
            logger.error("ISE: PredictionValidator not available (import failed)")
            return {"validated": 0, "errors": 0}

        users = _get_active_ai_users()
        validated = 0
        errors = 0

        for user in users:
            try:
                outcomes = validate_expired_predictions(user)
                validated += len(outcomes) if outcomes else 0
            except Exception as e:
                errors += 1
                logger.warning(f"ISE: Prediction validation failed for {user.email}: {e}")

        logger.info(f"ISE: Prediction validation — validated={validated}, errors={errors}")
        return {"validated": validated, "errors": errors}


def run_intervention_effectiveness():
    """
    Evaluate intervention effectiveness for all active users.

    Calls InterventionEffectivenessTracker per user to update
    effectiveness scores and escalation speed modifiers.

    Returns:
        dict — {evaluated: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.ai_feedback.intervention_tracker import evaluate_intervention_effectiveness
        except ImportError:
            logger.error("ISE: InterventionEffectivenessTracker not available (import failed)")
            return {"evaluated": 0, "errors": 0}

        users = _get_active_ai_users()
        evaluated = 0
        errors = 0

        for user in users:
            try:
                evaluate_intervention_effectiveness(user)
                evaluated += 1
            except Exception as e:
                errors += 1
                logger.warning(f"ISE: Intervention effectiveness failed for {user.email}: {e}")

        logger.info(f"ISE: Intervention effectiveness — evaluated={evaluated}, errors={errors}")
        return {"evaluated": evaluated, "errors": errors}


def run_cdce_synthetic():
    """
    Synthetic batch: run CDCE cross-domain correlations for all active AI users.

    Discovers cross-domain patterns (sleep→mood, exercise→mood, etc.)
    and stores DomainCorrelation records. Also expires stale correlations.

    Returns:
        dict — {processed: int, checked: int, correlations_found: int, errors: int}
    """
    with trace_context(source="manual_synthetic"):
        try:
            from apps.core.ai_cross_domain.cdce_engine import (
                expire_stale_correlations,
                run_cdce,
            )
        except ImportError:
            logger.error("ISE: CDCE not available (import failed)")
            return {"processed": 0, "checked": 0, "correlations_found": 0, "errors": 0}

        # Step 1: Expire stale correlations globally
        expire_stale_correlations()

        # Step 2: Run CDCE per user
        users = _get_active_ai_users()
        checked = 0
        total_correlations = 0
        errors = 0

        for user in users:
            try:
                results = run_cdce(user)
                checked += 1
                total_correlations += len(results) if results else 0
            except Exception as e:
                errors += 1
                logger.warning(f"ISE: CDCE failed for user {user.email}: {e}")

        logger.info(
            f"ISE: CDCE synthetic — processed={len(users)}, "
            f"checked={checked}, found={total_correlations}, errors={errors}"
        )
        return {
            "processed": len(users),
            "checked": checked,
            "correlations_found": total_correlations,
            "errors": errors,
        }


def run_cross_domain_insights():
    """
    Run cross-domain correlation insight rules for all active users.

    Fires a 'scheduled_check' event through the insight engine,
    which triggers cross-domain rules registered via @register.

    Returns:
        dict — {checked: int, insights_created: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.ai_insights.insight_engine import run_insights
        except ImportError:
            logger.error("ISE: Insight engine not available (import failed)")
            return {"checked": 0, "insights_created": 0, "errors": 0}

        users = _get_active_ai_users()
        checked = 0
        total_insights = 0
        errors = 0

        for user in users:
            try:
                event = {
                    "event_type": "scheduled_check",
                    "module": "cross_domain",
                }
                insights = run_insights(user, event)
                checked += 1
                total_insights += len(insights) if insights else 0
            except Exception as e:
                errors += 1
                logger.warning(f"ISE: Cross-domain insights failed for {user.email}: {e}")

        logger.info(
            f"ISE: Cross-domain insights — checked={checked}, "
            f"created={total_insights}, errors={errors}"
        )
        return {"checked": checked, "insights_created": total_insights, "errors": errors}


# =========================================================================
# SYNTHETIC BATCH RUNNERS (Phase 2.5 — Manual Execution)
# =========================================================================
# These runners enable manual execution of context-dependent engines
# from the Ops Command Center.  Each iterates all active AI users and
# calls the engine's per-user entry point with current stored data.
# No fake events are created; no raw user data is altered.
# =========================================================================


def run_ual_synthetic():
    """
    Synthetic batch: run UAL arbitration for all active AI users.

    Re-evaluates current state via signal collectors per user.
    Writes ArbitrationDecisionLog, histories, nudge memory.

    Returns:
        dict — {processed: int, evaluated: int, errors: int}
    """
    with trace_context(source="manual_synthetic"):
        try:
            from apps.core.ai_arbitration.arbitration_engine import run_arbitration
        except ImportError:
            logger.error("ISE: UAL not available (import failed)")
            return {"processed": 0, "evaluated": 0, "errors": 0}

        users = _get_active_ai_users()
        evaluated = 0
        errors = 0

        for user in users:
            try:
                result = run_arbitration(user)
                if result is not None and result.dominant_scenario:
                    evaluated += 1
            except Exception as e:
                errors += 1
                logger.warning(f"ISE: UAL synthetic failed for user {user.id}: {e}")

        logger.info(
            f"ISE: UAL synthetic — processed={len(users)}, "
            f"evaluated={evaluated}, errors={errors}"
        )
        return {"processed": len(users), "evaluated": evaluated, "errors": errors}


def run_sae_synthetic():
    """
    Synthetic batch: full SAE state rebuild for all active AI users.

    Calls rebuild_user_state() which rebuilds all modules (health, goals,
    habits, journal, faith, nutrition, fasting, fitness, transformation).

    Returns:
        dict — {processed: int, rebuilt: int, errors: int}
    """
    with trace_context(source="manual_synthetic"):
        try:
            from apps.core.ai_state.state_engine import rebuild_user_state
        except ImportError:
            logger.error("ISE: SAE state_engine not available (import failed)")
            return {"processed": 0, "rebuilt": 0, "errors": 0}

        users = _get_active_ai_users()
        rebuilt = 0
        errors = 0

        for user in users:
            try:
                rebuild_user_state(user)
                rebuilt += 1
            except Exception as e:
                errors += 1
                logger.warning(f"ISE: SAE synthetic failed for user {user.id}: {e}")

        logger.info(
            f"ISE: SAE synthetic — processed={len(users)}, "
            f"rebuilt={rebuilt}, errors={errors}"
        )
        return {"processed": len(users), "rebuilt": rebuilt, "errors": errors}


def run_pie_synthetic():
    """
    Synthetic batch: run PIE insight rules for all active AI users.

    Fires a scheduled_check event with module='cross_domain' to trigger
    broad rule evaluation using current user data.

    Returns:
        dict — {processed: int, checked: int, insights_created: int, errors: int}
    """
    with trace_context(source="manual_synthetic"):
        try:
            from apps.core.ai_insights.insight_engine import run_insights
        except ImportError:
            logger.error("ISE: PIE insight engine not available (import failed)")
            return {"processed": 0, "checked": 0, "insights_created": 0, "errors": 0}

        users = _get_active_ai_users()
        checked = 0
        total_insights = 0
        errors = 0

        for user in users:
            try:
                event = {
                    "event_type": "scheduled_check",
                    "module": "cross_domain",
                }
                insights = run_insights(user, event)
                checked += 1
                total_insights += len(insights) if insights else 0
            except Exception as e:
                errors += 1
                logger.warning(f"ISE: PIE synthetic failed for user {user.id}: {e}")

        logger.info(
            f"ISE: PIE synthetic — processed={len(users)}, "
            f"checked={checked}, created={total_insights}, errors={errors}"
        )
        return {
            "processed": len(users),
            "checked": checked,
            "insights_created": total_insights,
            "errors": errors,
        }


def run_prie_synthetic():
    """
    Synthetic batch: generate predictions for all active AI users.

    Calls generate_predictions(user, module=None) which runs ALL
    applicable prediction rules.

    Returns:
        dict — {processed: int, checked: int, predictions_created: int, errors: int}
    """
    with trace_context(source="manual_synthetic"):
        try:
            from apps.core.ai_predictions.prediction_engine import generate_predictions
        except ImportError:
            logger.error("ISE: PRIE prediction engine not available (import failed)")
            return {"processed": 0, "checked": 0, "predictions_created": 0, "errors": 0}

        users = _get_active_ai_users()
        checked = 0
        total_predictions = 0
        errors = 0

        for user in users:
            try:
                predictions = generate_predictions(user, module=None)
                checked += 1
                total_predictions += len(predictions) if predictions else 0
            except Exception as e:
                errors += 1
                logger.warning(f"ISE: PRIE synthetic failed for user {user.id}: {e}")

        logger.info(
            f"ISE: PRIE synthetic — processed={len(users)}, "
            f"checked={checked}, created={total_predictions}, errors={errors}"
        )
        return {
            "processed": len(users),
            "checked": checked,
            "predictions_created": total_predictions,
            "errors": errors,
        }


def run_icqg_synthetic():
    """
    Synthetic batch: re-validate ICQG quality gate for all active AI users.

    Pulls each user's active GuidanceItem records, converts to candidate
    dicts, and passes through filter_guidance_candidates().  This validates
    the quality gate against current data without generating new guidance.

    Items that would be suppressed are counted but NOT deleted (read-only
    validation).

    Returns:
        dict — {processed: int, checked: int, items_evaluated: int,
                would_suppress: int, errors: int}
    """
    with trace_context(source="manual_synthetic"):
        try:
            from apps.core.ai_guidance.models import GuidanceItem
            from apps.core.ai_quality.quality_gate import filter_guidance_candidates
        except ImportError:
            logger.error("ISE: ICQG quality gate not available (import failed)")
            return {
                "processed": 0, "checked": 0,
                "items_evaluated": 0, "would_suppress": 0, "errors": 0,
            }

        users = _get_active_ai_users()
        checked = 0
        total_items = 0
        total_suppressed = 0
        errors = 0

        for user in users:
            try:
                active_items = GuidanceItem.objects.filter(
                    user=user,
                    is_active=True,
                    dismissed_at__isnull=True,
                ).values(
                    "id", "title", "message", "priority", "guidance_type",
                    "source", "module", "evidence", "confidence_score",
                )
                candidates = list(active_items)

                if not candidates:
                    checked += 1
                    continue

                filtered = filter_guidance_candidates(user, candidates)
                suppressed = len(candidates) - len(filtered)

                checked += 1
                total_items += len(candidates)
                total_suppressed += suppressed
            except Exception as e:
                errors += 1
                logger.warning(f"ISE: ICQG synthetic failed for user {user.id}: {e}")

        logger.info(
            f"ISE: ICQG synthetic — processed={len(users)}, checked={checked}, "
            f"evaluated={total_items}, would_suppress={total_suppressed}, "
            f"errors={errors}"
        )
        return {
            "processed": len(users),
            "checked": checked,
            "items_evaluated": total_items,
            "would_suppress": total_suppressed,
            "errors": errors,
        }


# =========================================================================
# PHASE 5 — GOVERNANCE RUNNERS
# =========================================================================


def run_deadline_snapshots():
    """
    Phase 2: Compute deadline snapshots for all active AI users.

    ISE-driven, runs every 5 minutes. Only computes for users with
    pending commitments, future goal deadlines, or scheduled blocks.

    Returns:
        dict — {computed: int, skipped: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.blueprint.deadline_engine import (
                compute_deadline_snapshot,
                should_compute_snapshot,
            )
        except ImportError:
            logger.error("ISE: Deadline engine not available (import failed)")
            return {"computed": 0, "skipped": 0, "errors": 0}

        users = _get_active_ai_users()
        computed = 0
        skipped = 0
        errors = 0

        for user in users:
            try:
                if should_compute_snapshot(user):
                    compute_deadline_snapshot(user)
                    computed += 1
                else:
                    skipped += 1
            except Exception as e:
                errors += 1
                logger.error(f"ISE: Deadline snapshot failed for user {user.id}: {e}")

        logger.info(
            f"ISE: Deadline snapshots — computed={computed}, "
            f"skipped={skipped}, errors={errors}"
        )
        return {"computed": computed, "skipped": skipped, "errors": errors}


def run_tomorrow_protection_pass():
    """
    Run tomorrow protection pass for all active AI users.

    Locks non-negotiable blocks, detects overload, moves flexible items.

    Returns:
        dict — {processed: int, protected: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.ai_governance.tomorrow_protection import run_protection_pass_all_users
            return run_protection_pass_all_users()
        except ImportError:
            logger.error("ISE: Tomorrow protection pass not available (import failed)")
            return {"processed": 0, "protected": 0, "errors": 0}


def run_escalation_updates():
    """
    Phase 3: Daily update of escalation states and behavioral trends.

    For each active AI user:
    1. Update consecutive_clean_days and peak_level_7d
    2. Compute behavioral trends per behavior_key

    Returns:
        dict — {updated: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.blueprint.escalation_engine import (
                compute_behavioral_trends,
                update_daily_escalation_state,
            )
        except ImportError:
            logger.error("ISE: Escalation engine not available (import failed)")
            return {"updated": 0, "errors": 0}

        users = _get_active_ai_users()
        updated = 0
        errors = 0

        for user in users:
            try:
                update_daily_escalation_state(user)
                compute_behavioral_trends(user)
                updated += 1
            except Exception as e:
                errors += 1
                logger.error(
                    "ISE: Escalation update failed for user %s: %s",
                    user.id, e,
                )

        logger.info(
            "ISE: Escalation updates complete — updated=%d, errors=%d",
            updated, errors,
        )
        return {"updated": updated, "errors": errors}


def run_pressure_snapshots():
    """
    Phase 4: Compute pressure snapshots for all active AI users.

    Daily ISE sweep. Creates a PressureSnapshot for each user with
    an active blueprint. Idempotent — creates new records, never overwrites.

    Returns:
        dict — {computed: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.blueprint.pressure_engine import update_pressure_snapshot
        except ImportError:
            logger.error("ISE: Pressure engine not available (import failed)")
            return {"computed": 0, "errors": 0}

        users = _get_active_ai_users().filter(
            preferences__personal_assistant_enabled=True,
        )
        computed = 0
        errors = 0

        for user in users:
            try:
                result = update_pressure_snapshot(user)
                if result is not None:
                    computed += 1
            except Exception as e:
                errors += 1
                logger.warning(
                    "ISE: Pressure snapshot failed for user %s: %s",
                    user.id, e,
                )

        logger.info(
            "ISE: Pressure snapshots complete — computed=%d, errors=%d",
            computed, errors,
        )
        return {"computed": computed, "errors": errors}


# =========================================================================
# Phase 5: Protective Action Engine
# =========================================================================

def run_protective_sweep():
    """
    Phase 5: Daily protective sweep — recompute recommendations and
    schedule alerts for all active users.

    Returns:
        dict — {users_processed: int, recommendations: int, alerts: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.blueprint.protective_engine import run_protective_sweep as sweep
        except ImportError:
            logger.error("ISE: Protective engine not available (import failed)")
            return {"users_processed": 0, "recommendations": 0, "alerts": 0, "errors": 0}

        result = sweep()
        logger.info(
            "ISE: Protective sweep complete — users=%d, recs=%d, alerts=%d, errors=%d",
            result['users_processed'], result['recommendations'],
            result['alerts'], result['errors'],
        )
        return result


def run_protective_alert_delivery():
    """
    Phase 5: Deliver due protective alerts via DNE with throttle respect.

    Runs every 5 minutes. Fetches pending alerts that are due and delivers
    them, respecting per-user throttle limits.

    Returns:
        dict — {delivered: int, suppressed: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.core.blueprint.protective_engine import deliver_due_alerts
        except ImportError:
            logger.error("ISE: Protective engine not available (import failed)")
            return {"delivered": 0, "suppressed": 0, "errors": 0}

        result = deliver_due_alerts()
        logger.info(
            "ISE: Protective alert delivery complete — delivered=%d, suppressed=%d, errors=%d",
            result['delivered'], result['suppressed'], result['errors'],
        )
        return result


def run_cos_prompt_scheduling():
    """
    Schedule CoS prompts for upcoming habits, goals, milestones, and events.

    Runs every 6 hours. Generates pre/post prompts for the next 24-48h window.

    Returns:
        dict — {scheduled: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.cos.services.cos_prompt_scheduler import CosPromptScheduler
        except ImportError:
            logger.error("ISE: CosPromptScheduler not available (import failed)")
            return {"scheduled": 0, "errors": 0}

        result = CosPromptScheduler.schedule_upcoming_prompts_for_all_users()
        logger.info(
            "ISE: CoS prompt scheduling complete — scheduled=%d, errors=%d",
            result['scheduled'], result['errors'],
        )
        return result


def run_cos_prompt_delivery():
    """
    Deliver due CoS prompts to all users.

    Runs every 5 minutes. Finds pending prompts where scheduled_for <= now
    and delivers them via DNE.

    Returns:
        dict — {delivered: int, errors: int}
    """
    with trace_context(source="scheduler"):
        try:
            from apps.cos.services.prompt_service import CosPromptService
        except ImportError:
            logger.error("ISE: CosPromptService not available (import failed)")
            return {"delivered": 0, "errors": 0}

        result = CosPromptService.deliver_all_due_for_all_users()
        logger.info(
            "ISE: CoS prompt delivery complete — delivered=%d, errors=%d",
            result.get('delivered', 0), result.get('errors', 0),
        )
        return result


def run_maturity_snapshot():
    """
    Phase 7.4: Compute and persist daily system maturity snapshot.

    Returns:
        dict — {overall_score: int, created: bool}
    """
    try:
        from apps.core.ai_observability.maturity_engine import create_daily_snapshot
        snapshot = create_daily_snapshot()
        return {
            "overall_score": snapshot.overall_score if snapshot else 0,
            "created": True,
        }
    except Exception as e:
        logger.error("ISE: Maturity snapshot failed: %s", e, exc_info=True)
        return {"overall_score": 0, "created": False, "error": str(e)[:200]}


def run_cdce_check_ins():
    """
    Phase 7.2: Generate proactive check-ins from CDCE correlations.

    Returns:
        dict — {users_processed: int}
    """
    from apps.users.models import User

    users = User.objects.filter(
        is_active=True,
        preferences__personal_assistant_enabled=True,
    ).select_related('preferences')[:50]

    processed = 0
    for user in users:
        try:
            from apps.ai.proactive_checkins import (
                generate_cdce_correlation_check_ins_for_user,
            )
            generate_cdce_correlation_check_ins_for_user(user)
            processed += 1
        except Exception as e:
            logger.warning(
                "ISE: CDCE check-in failed for user %s: %s",
                user.pk, e,
            )

    logger.info("ISE: CDCE check-ins processed for %d users", processed)
    return {"users_processed": processed}
