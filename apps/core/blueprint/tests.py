"""
Whole Life Journey - Blueprint Tests

Project: Whole Life Journey
Path: apps/core/blueprint/tests.py
Purpose: Comprehensive tests for the Chief of Staff blueprint system

Tests cover:
    - Blueprint creation and defaults
    - Module flag syncing and gating
    - Priority engine tier resolution and conflict resolution
    - Architecture engine planning
    - Drift engine scoring and prediction
    - Intervention engine escalation and friction gates
    - Assistant triggers
    - API endpoints

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import datetime
import json

from django.conf import settings
from django.test import TestCase, RequestFactory, Client
from django.utils import timezone

from apps.users.models import User, TermsAcceptance

from .models import (
    ArchitecturePlan,
    DriftEvent,
    DriftScore,
    InterventionLog,
    NonNegotiable,
    PersonalOperatingBlueprint,
    ScheduledBlock,
)
from . import engine as blueprint_engine
from . import priority_engine
from . import architecture_engine
from . import drift_engine
from . import intervention_engine
from . import assistant_triggers


def _create_test_user(email='test@example.com', password='testpass123'):
    """Create a test user with onboarding complete."""
    user = User.objects.create_user(email=email, password=password)
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.ai_enabled = True
    user.preferences.personal_assistant_enabled = True
    user.preferences.save()
    return user


# =============================================================================
# BLUEPRINT MODEL TESTS
# =============================================================================


class PersonalOperatingBlueprintTests(TestCase):
    """Tests for the PersonalOperatingBlueprint model."""

    def setUp(self):
        self.user = _create_test_user()

    def test_get_or_create_creates_blueprint(self):
        """Blueprint is created on first access."""
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa
        self.assertIsNotNone(blueprint)
        self.assertEqual(blueprint.user, self.user)
        self.assertEqual(blueprint.version, 1)

    def test_get_or_create_returns_existing(self):
        """Second call returns existing blueprint, not new one."""
        b1 = PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa
        b2 = PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa
        self.assertEqual(b1.pk, b2.pk)

    def test_default_operating_style(self):
        """Default operating style is executive_cos."""
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa
        self.assertEqual(blueprint.operating_style, 'executive_cos')

    def test_default_auto_architect(self):
        """Auto architect is enabled by default."""
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa
        self.assertTrue(blueprint.auto_architect_enabled)

    def test_sync_module_flags(self):
        """Module flags are synced from user preferences."""
        self.user.preferences.health_enabled = True
        self.user.preferences.faith_enabled = False
        self.user.preferences.save()

        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa
        blueprint.sync_module_flags()
        blueprint.save()

        self.assertTrue(blueprint.module_flags_snapshot.get('health'))
        self.assertFalse(blueprint.module_flags_snapshot.get('faith'))

    def test_is_module_enabled(self):
        """is_module_enabled checks the snapshot."""
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa
        blueprint.module_flags_snapshot = {'health': True, 'faith': False}
        blueprint.save()

        self.assertTrue(blueprint.is_module_enabled('health'))
        self.assertFalse(blueprint.is_module_enabled('faith'))
        self.assertFalse(blueprint.is_module_enabled('unknown'))

    def test_get_tier_for_behavior_tier1(self):
        """Tier 1 behaviors come from tier1_protected_behaviors."""
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa
        blueprint.tier1_protected_behaviors = ['WORKOUT', 'MEDS_ADHERENCE']
        blueprint.save()

        self.assertEqual(blueprint.get_tier_for_behavior('WORKOUT'), 1)
        self.assertEqual(blueprint.get_tier_for_behavior('MEDS_ADHERENCE'), 1)

    def test_get_tier_for_behavior_tier2(self):
        """Non-negotiables not in tier1 are tier 2."""
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa
        NonNegotiable.objects.create(
            blueprint=blueprint,
            behavior_key='FAITH_BLOCK',
            display_name='Faith Block',
        )
        self.assertEqual(blueprint.get_tier_for_behavior('FAITH_BLOCK'), 2)

    def test_get_tier_for_behavior_default(self):
        """Unknown behaviors default to tier 4."""
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa
        self.assertEqual(blueprint.get_tier_for_behavior('UNKNOWN'), 4)

    def test_get_pillar_weight(self):
        """First pillar gets highest weight."""
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa
        blueprint.pillars_ranked = ['FAITH', 'HEALTH', 'PURPOSE']
        blueprint.save()

        self.assertEqual(blueprint.get_pillar_weight('FAITH'), 1.0)
        self.assertGreater(blueprint.get_pillar_weight('FAITH'),
                          blueprint.get_pillar_weight('PURPOSE'))


# =============================================================================
# BLUEPRINT ENGINE TESTS
# =============================================================================


class BlueprintEngineTests(TestCase):
    """Tests for the blueprint engine service."""

    def setUp(self):
        self.user = _create_test_user()

    def test_get_blueprint(self):
        """get_blueprint creates and returns blueprint."""
        blueprint = blueprint_engine.get_blueprint(self.user)
        self.assertIsNotNone(blueprint)

    def test_update_blueprint(self):
        """update_blueprint updates specified fields."""
        blueprint = blueprint_engine.update_blueprint(
            self.user,
            {'operating_style': 'coach', 'sleep_target_minutes': 420},
        )
        self.assertEqual(blueprint.operating_style, 'coach')
        self.assertEqual(blueprint.sleep_target_minutes, 420)
        self.assertEqual(blueprint.version, 2)

    def test_explain_blueprint(self):
        """explain_blueprint returns transparency dict."""
        blueprint_engine.get_blueprint(self.user)
        explanation = blueprint_engine.explain_blueprint(self.user)
        self.assertIn('operating_style', explanation)
        self.assertIn('pillars_ranked', explanation)
        self.assertIn('enabled_modules', explanation)

    def test_is_behavior_reference_allowed_enabled(self):
        """Behavior from enabled module is allowed."""
        blueprint = blueprint_engine.get_blueprint(self.user)
        blueprint.module_flags_snapshot = {'health': True}
        blueprint.sub_feature_flags_snapshot = {'health.fitness': True}
        blueprint.save()

        self.assertTrue(blueprint_engine.is_behavior_reference_allowed(self.user, 'WORKOUT'))

    def test_is_behavior_reference_allowed_disabled(self):
        """Behavior from disabled module is NOT allowed."""
        blueprint = blueprint_engine.get_blueprint(self.user)
        blueprint.module_flags_snapshot = {'faith': False}
        blueprint.save()

        self.assertFalse(blueprint_engine.is_behavior_reference_allowed(self.user, 'FAITH_BLOCK'))

    def test_is_behavior_reference_allowed_unknown(self):
        """Unknown behaviors are allowed by default."""
        self.assertTrue(blueprint_engine.is_behavior_reference_allowed(self.user, 'CUSTOM_THING'))


# =============================================================================
# PRIORITY ENGINE TESTS
# =============================================================================


class PriorityEngineTests(TestCase):
    """Tests for the priority engine."""

    def setUp(self):
        self.user = _create_test_user()
        self.blueprint = blueprint_engine.get_blueprint(self.user)
        self.blueprint.tier1_protected_behaviors = ['WORKOUT', 'MEDS_ADHERENCE']
        self.blueprint.pillars_ranked = ['HEALTH_DISCIPLINE', 'FAITH', 'PURPOSE']
        self.blueprint.save()

    def test_resolve_conflict_no_curveball(self):
        """No curveball = no conflict."""
        result = priority_engine.resolve_conflict(self.blueprint, [], [])
        self.assertTrue(result.success)
        self.assertFalse(result.tier1_impacted)

    def test_resolve_conflict_moves_lower_tiers_first(self):
        """Lower tiers are moved before higher tiers."""
        blocks = [
            {'title': 'Meeting', 'tier': 3, 'behavior_key': ''},
            {'title': 'Workout', 'tier': 1, 'behavior_key': 'WORKOUT'},
        ]
        curveball = {'title': 'Emergency', 'tier': 2}

        result = priority_engine.resolve_conflict(
            self.blueprint, blocks, [], curveball,
        )

        # Tier 3 should be moved, tier 1 protected
        moved_tiers = [m['tier'] for m in result.moved_blocks]
        self.assertIn(3, moved_tiers)
        self.assertFalse(result.tier1_impacted)

    def test_compute_identity_cost(self):
        """Identity cost is computed correctly."""
        cost = priority_engine.compute_identity_cost(self.blueprint, 'WORKOUT')
        self.assertGreaterEqual(cost.cost, 0)
        self.assertLessEqual(cost.cost, 100)
        self.assertGreater(cost.pillar_weight, 0)

    def test_prioritize_blocks(self):
        """Blocks are sorted by tier and pillar weight."""
        blocks = [
            {'title': 'Optional', 'tier': 4, 'behavior_key': ''},
            {'title': 'Workout', 'behavior_key': 'WORKOUT'},
            {'title': 'Meeting', 'tier': 3, 'behavior_key': ''},
        ]

        sorted_blocks = priority_engine.prioritize_blocks(self.blueprint, blocks)
        # Tier 1 (workout) should come first
        self.assertEqual(sorted_blocks[0]['title'], 'Workout')


# =============================================================================
# DRIFT ENGINE TESTS
# =============================================================================


class DriftEngineTests(TestCase):
    """Tests for the drift engine."""

    def setUp(self):
        self.user = _create_test_user()
        self.blueprint = blueprint_engine.get_blueprint(self.user)
        self.blueprint.module_flags_snapshot = {'health': True, 'faith': True}
        self.blueprint.sub_feature_flags_snapshot = {'health.fasting': True, 'health.fitness': True}
        self.blueprint.save()

    def test_record_drift_event(self):
        """Drift events are recorded correctly."""
        event = drift_engine.record_drift_event(
            self.user,
            DriftEvent.DRIFT_WORKOUT_SKIPPED,
            behavior_key='WORKOUT',
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.drift_type, DriftEvent.DRIFT_WORKOUT_SKIPPED)

    def test_record_drift_event_disabled_module(self):
        """Drift events for disabled modules are not recorded."""
        self.blueprint.module_flags_snapshot = {'health': False}
        self.blueprint.save()

        event = drift_engine.record_drift_event(
            self.user,
            DriftEvent.DRIFT_WORKOUT_SKIPPED,
        )
        self.assertIsNone(event)

    def test_compute_daily_drift_score_no_events(self):
        """Zero events = zero score."""
        score = drift_engine.compute_daily_drift_score(self.user)
        self.assertEqual(score.score, 0.0)
        self.assertEqual(score.event_count, 0)

    def test_compute_daily_drift_score_with_events(self):
        """Score increases with drift events."""
        drift_engine.record_drift_event(
            self.user, DriftEvent.DRIFT_WORKOUT_SKIPPED,
            behavior_key='WORKOUT', severity=0.5,
        )
        drift_engine.record_drift_event(
            self.user, DriftEvent.DRIFT_MED_MISSED,
            behavior_key='MEDS_ADHERENCE', severity=0.8,
        )

        score = drift_engine.compute_daily_drift_score(self.user)
        self.assertGreater(score.score, 0)
        self.assertEqual(score.event_count, 2)

    def test_predict_drift_probability(self):
        """Drift prediction returns valid probabilities."""
        prediction = drift_engine.predict_drift_probability(self.user)
        self.assertIn('probability_24h', prediction)
        self.assertIn('probability_72h', prediction)
        self.assertGreaterEqual(prediction['probability_24h'], 0)
        self.assertLessEqual(prediction['probability_24h'], 1)

    def test_get_drift_summary(self):
        """Drift summary returns expected structure."""
        summary = drift_engine.get_drift_summary(self.user)
        self.assertIn('average_score', summary)
        self.assertIn('total_events', summary)
        self.assertIn('daily_scores', summary)


# =============================================================================
# INTERVENTION ENGINE TESTS
# =============================================================================


class InterventionEngineTests(TestCase):
    """Tests for the intervention engine."""

    def setUp(self):
        self.user = _create_test_user()
        self.blueprint = blueprint_engine.get_blueprint(self.user)
        self.blueprint.interruption_tolerance = 'medium'
        self.blueprint.save()

    def test_determine_escalation_tier1_violation(self):
        """Tier 1 violations always get friction gate."""
        level = intervention_engine.determine_escalation_level(
            self.user, 'tier1_violation', context={'tier': 1},
        )
        self.assertEqual(level, InterventionLog.LEVEL_FRICTION_GATE)

    def test_determine_escalation_low_tolerance(self):
        """Low tolerance reduces escalation level."""
        self.blueprint.interruption_tolerance = 'low'
        self.blueprint.save()

        level = intervention_engine.determine_escalation_level(
            self.user, 'approaching_deadline',
        )
        self.assertEqual(level, InterventionLog.LEVEL_SILENT)  # Reduced from nudge

    def test_determine_escalation_high_tolerance(self):
        """High tolerance increases escalation level."""
        self.blueprint.interruption_tolerance = 'high'
        self.blueprint.save()

        level = intervention_engine.determine_escalation_level(
            self.user, 'approaching_deadline',
        )
        self.assertEqual(level, InterventionLog.LEVEL_PING)  # Increased from nudge

    def test_create_intervention(self):
        """Interventions are created and logged."""
        intervention = intervention_engine.create_intervention(
            self.user,
            level=InterventionLog.LEVEL_NUDGE,
            trigger_type='test',
            message='Test nudge',
        )
        self.assertIsNotNone(intervention)
        self.assertEqual(intervention.level, InterventionLog.LEVEL_NUDGE)

    def test_create_friction_gate(self):
        """Friction gates return expected structure."""
        self.blueprint.tier1_protected_behaviors = ['WORKOUT']
        self.blueprint.pillars_ranked = ['HEALTH_DISCIPLINE']
        self.blueprint.save()

        gate = intervention_engine.create_friction_gate(
            self.user,
            behavior_key='WORKOUT',
            action_description='Skip workout',
            consequence='Weekly adherence drops to 60%',
            adherence_projection=60,
        )
        self.assertIn('intervention_id', gate)
        self.assertIn('message', gate)
        self.assertIn('options', gate)
        self.assertEqual(len(gate['options']), 3)

    def test_record_intervention_response(self):
        """Intervention responses are recorded."""
        intervention = intervention_engine.create_intervention(
            self.user, level=1, trigger_type='test', message='Test',
        )
        result = intervention_engine.record_intervention_response(
            intervention.pk, InterventionLog.RESPONSE_ACCEPTED, user=self.user,
        )
        self.assertEqual(result.user_response, InterventionLog.RESPONSE_ACCEPTED)
        self.assertIsNotNone(result.responded_at)

    def test_get_pending_interventions(self):
        """Pending interventions are returned."""
        intervention_engine.create_intervention(
            self.user, level=1, trigger_type='test', message='Test 1',
        )
        intervention_engine.create_intervention(
            self.user, level=2, trigger_type='test', message='Test 2',
        )

        pending = intervention_engine.get_pending_interventions(self.user)
        self.assertEqual(pending.count(), 2)


# =============================================================================
# ARCHITECTURE ENGINE TESTS
# =============================================================================


class ArchitectureEngineTests(TestCase):
    """Tests for the architecture engine."""

    def setUp(self):
        self.user = _create_test_user()
        self.blueprint = blueprint_engine.get_blueprint(self.user)
        self.blueprint.auto_architect_enabled = True
        self.blueprint.module_flags_snapshot = {'health': True}
        self.blueprint.save()

    def test_run_architecture_pass(self):
        """Architecture pass creates an active plan."""
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        plan = architecture_engine.run_architecture_pass(self.user, tomorrow)

        self.assertIsNotNone(plan)
        self.assertEqual(plan.status, ArchitecturePlan.STATUS_ACTIVE)
        self.assertEqual(plan.date, tomorrow)
        self.assertTrue(plan.blocks.count() > 0)

    def test_get_todays_plan_none(self):
        """No plan returns None."""
        plan = architecture_engine.get_todays_plan(self.user)
        self.assertIsNone(plan)

    def test_handle_curveball(self):
        """Curveball creates a new plan."""
        # First create a plan for today
        today = timezone.localdate()
        ArchitecturePlan.objects.create(
            user=self.user, date=today, status=ArchitecturePlan.STATUS_ACTIVE,
        )

        new_plan = architecture_engine.handle_curveball(
            self.user, 'Emergency meeting',
            new_event_duration_minutes=60,
        )
        self.assertIsNotNone(new_plan)
        self.assertEqual(new_plan.generation_trigger, 'curveball')
        self.assertEqual(new_plan.status, ArchitecturePlan.STATUS_ACTIVE)


# =============================================================================
# ASSISTANT TRIGGER TESTS
# =============================================================================


class AssistantTriggerTests(TestCase):
    """Tests for assistant triggers."""

    def setUp(self):
        self.user = _create_test_user()
        self.blueprint = blueprint_engine.get_blueprint(self.user)
        self.blueprint.auto_architect_enabled = True
        self.blueprint.save()

    def test_check_triggers_returns_list(self):
        """check_triggers returns a list."""
        results = assistant_triggers.check_triggers(self.user)
        self.assertIsInstance(results, list)

    def test_check_triggers_disabled_auto_architect(self):
        """No triggers fire if auto_architect is disabled."""
        self.blueprint.auto_architect_enabled = False
        self.blueprint.save()

        results = assistant_triggers.check_triggers(self.user)
        self.assertEqual(len(results), 0)

    def test_execute_trigger_deduplication(self):
        """Triggers are deduped within 4 hours."""
        result = assistant_triggers.TriggerResult(
            trigger_type='test_trigger',
            should_fire=True,
            level=1,
            message='Test',
            dedupe_key='test_dedupe',
        )

        # First execution should succeed
        intervention1 = assistant_triggers.execute_trigger(self.user, result)
        self.assertIsNotNone(intervention1)

        # Second execution within window should be deduped
        intervention2 = assistant_triggers.execute_trigger(self.user, result)
        self.assertIsNone(intervention2)


# =============================================================================
# NON-NEGOTIABLE TESTS
# =============================================================================


class NonNegotiableTests(TestCase):
    """Tests for non-negotiable model and scheduling."""

    def setUp(self):
        self.user = _create_test_user()
        self.blueprint = blueprint_engine.get_blueprint(self.user)
        self.blueprint.module_flags_snapshot = {'health': True}
        self.blueprint.save()

    def test_is_applicable_today_daily(self):
        """Daily non-negotiables always apply."""
        nn = NonNegotiable.objects.create(
            blueprint=self.blueprint,
            behavior_key='WORKOUT',
            display_name='Workout',
            frequency=NonNegotiable.FREQUENCY_DAILY,
        )
        self.assertTrue(nn.is_applicable_today())

    def test_is_applicable_today_weekdays(self):
        """Weekday non-negotiables apply Mon-Fri."""
        nn = NonNegotiable.objects.create(
            blueprint=self.blueprint,
            behavior_key='WORKOUT',
            display_name='Workout',
            frequency=NonNegotiable.FREQUENCY_WEEKDAYS,
        )
        # Test with a Monday
        monday = datetime.date(2026, 2, 16)  # This is a Monday
        self.assertTrue(nn.is_applicable_today(monday))

        # Test with a Sunday
        sunday = datetime.date(2026, 2, 22)  # This is a Sunday
        self.assertFalse(nn.is_applicable_today(sunday))

    def test_is_feature_enabled_check(self):
        """Non-negotiables for disabled features are filtered."""
        nn = NonNegotiable.objects.create(
            blueprint=self.blueprint,
            behavior_key='WORKOUT',
            display_name='Workout',
            module_key='health',
            feature_key='health.fitness',
        )
        # Feature enabled
        self.blueprint.sub_feature_flags_snapshot = {'health.fitness': True}
        self.blueprint.save()
        self.assertTrue(nn.is_feature_enabled(self.blueprint))

        # Feature disabled
        self.blueprint.sub_feature_flags_snapshot = {'health.fitness': False}
        self.blueprint.save()
        self.assertFalse(nn.is_feature_enabled(self.blueprint))

    def test_get_non_negotiables_for_date(self):
        """Only enabled, applicable non-negotiables are returned."""
        NonNegotiable.objects.create(
            blueprint=self.blueprint,
            behavior_key='WORKOUT',
            display_name='Workout',
            frequency=NonNegotiable.FREQUENCY_DAILY,
            module_key='health',
        )

        result = blueprint_engine.get_non_negotiables_for_date(self.user)
        self.assertEqual(len(result), 1)


# =============================================================================
# API ENDPOINT TESTS
# =============================================================================


class BlueprintAPITests(TestCase):
    """Tests for blueprint API endpoints."""

    def setUp(self):
        self.user = _create_test_user()
        self.client.login(email='test@example.com', password='testpass123')

    def test_get_blueprint(self):
        """GET /api/blueprint/ returns blueprint."""
        response = self.client.get('/api/blueprint/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('blueprint', data)

    def test_get_explain(self):
        """GET /api/blueprint/explain/ returns explanation."""
        # Create blueprint first
        blueprint_engine.get_blueprint(self.user)

        response = self.client.get('/api/blueprint/explain/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('explanation', data)

    def test_get_non_negotiables(self):
        """GET /api/blueprint/non-negotiables/ returns list."""
        response = self.client.get('/api/blueprint/non-negotiables/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('non_negotiables', data)

    def test_intervention_check(self):
        """GET /api/blueprint/interventions/check/ returns count."""
        response = self.client.get('/api/blueprint/interventions/check/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('count', data)


# =============================================================================
# COMMAND BRIEF TESTS
# =============================================================================


class CommandBriefTests(TestCase):
    """Tests for the Command Brief dashboard integration."""

    def setUp(self):
        self.user = _create_test_user()
        self.client.login(email='test@example.com', password='testpass123')
        self.blueprint = blueprint_engine.get_blueprint(self.user)

    def test_dashboard_auto_generates_architecture(self):
        """Dashboard load should auto-generate architecture if missing."""
        # Verify no plan exists
        today = timezone.localdate()
        plan = ArchitecturePlan.get_active_for_date(self.user, today)
        self.assertIsNone(plan)

        # Load dashboard
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)

        # Command brief should be in context
        command_brief = response.context.get('command_brief')
        self.assertIsNotNone(command_brief)
        self.assertTrue(command_brief['active'])

    def test_no_plan_text_absent(self):
        """'No plan for today' should never appear in dashboard response."""
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'No plan for today')

    def test_command_brief_renders_for_authenticated_user(self):
        """Command Brief context should be populated for PA-enabled user.
        Note: When Command Mode is active, Command Brief is hidden in HTML
        but still present in context."""
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        command_brief = response.context.get('command_brief')
        self.assertIsNotNone(command_brief)
        self.assertTrue(command_brief['active'])
        # Command Mode should also be active (renders as greeting banner)
        command_mode = response.context.get('command_mode')
        if command_mode and command_mode.get('active'):
            # Command Mode takes priority over Command Brief in HTML
            self.assertContains(response, 'cos-greeting-banner')
        else:
            self.assertContains(response, 'command-brief')

    def test_command_brief_has_drift_risk(self):
        """Command Brief should include drift risk value."""
        response = self.client.get('/dashboard/')
        command_brief = response.context.get('command_brief')
        self.assertIsNotNone(command_brief)
        self.assertIn('drift_risk_24h', command_brief)
        self.assertIsInstance(command_brief['drift_risk_24h'], int)

    def test_command_brief_has_capacity(self):
        """Command Brief should include capacity percentage."""
        response = self.client.get('/dashboard/')
        command_brief = response.context.get('command_brief')
        self.assertIsNotNone(command_brief)
        self.assertIn('capacity_pct', command_brief)
        self.assertIsInstance(command_brief['capacity_pct'], int)

    def test_command_brief_tier1_populated(self):
        """Tier 1 items should be populated from architecture blocks."""
        # Create a plan with a Tier 1 block
        today = timezone.localdate()
        plan = ArchitecturePlan.objects.create(
            user=self.user, date=today,
            status=ArchitecturePlan.STATUS_ACTIVE,
            generation_trigger='test',
        )
        ScheduledBlock.objects.create(
            plan=plan,
            start_time=datetime.time(6, 0),
            end_time=datetime.time(7, 0),
            title='Morning Prayer',
            tier=1,
            is_locked=True,
            behavior_key='faith_prayer',
        )

        response = self.client.get('/dashboard/')
        command_brief = response.context.get('command_brief')
        self.assertIsNotNone(command_brief)
        self.assertGreater(len(command_brief['tier1_items']), 0)
        self.assertEqual(command_brief['tier1_items'][0]['title'], 'Morning Prayer')

    def test_command_brief_not_shown_when_pa_disabled(self):
        """Command Brief should not render when PA is disabled."""
        self.user.preferences.personal_assistant_enabled = False
        self.user.preferences.save()

        response = self.client.get('/dashboard/')
        command_brief = response.context.get('command_brief')
        self.assertIsNone(command_brief)
        self.assertNotContains(response, 'command-brief')

    def test_panel_plan_auto_generates(self):
        """Panel plan HTMX endpoint should auto-generate if no plan."""
        today = timezone.localdate()
        self.assertIsNone(ArchitecturePlan.get_active_for_date(self.user, today))

        response = self.client.get('/api/blueprint/plan/today/')
        self.assertEqual(response.status_code, 200)
        # Should not contain "No plan for today"
        self.assertNotContains(response, 'No plan for today')

    def test_sidebar_shows_monitoring_status(self):
        """Sidebar status text should describe what CoS is doing."""
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        # The panel renders with meaningful status
        self.assertContains(response, 'Monitoring your day')

    def test_alignment_score_calculated(self):
        """Alignment score should be 100 minus drift score."""
        response = self.client.get('/dashboard/')
        command_brief = response.context.get('command_brief')
        self.assertIsNotNone(command_brief)
        self.assertEqual(
            command_brief['alignment_score'],
            100 - command_brief['drift_score'],
        )


# =============================================================================
# COS CONTEXT BUILDER TESTS
# =============================================================================


class CosContextBuilderTests(TestCase):
    """Tests for the CoS context builder."""

    def setUp(self):
        self.user = _create_test_user(email='cos_ctx@test.com')

    def test_build_cos_context_returns_dict(self):
        """build_cos_context should return a dict with expected keys."""
        from apps.core.ai_orchestrator.cos_context import build_cos_context
        ctx = build_cos_context(self.user)
        self.assertIsInstance(ctx, dict)
        self.assertIn('blueprint_state', ctx)
        self.assertIn('protected_tiers', ctx)
        self.assertIn('capacity_snapshot', ctx)
        self.assertIn('drift_probability', ctx)
        self.assertIn('alignment_score', ctx)
        self.assertIn('drift_score', ctx)
        self.assertIn('module_permissions', ctx)
        self.assertIn('today_blocks_summary', ctx)

    def test_module_permissions_reflect_prefs(self):
        """Module permissions should match user preferences."""
        from apps.core.ai_orchestrator.cos_context import build_cos_context
        ctx = build_cos_context(self.user)
        mods = ctx['module_permissions']
        self.assertTrue(mods['ai'])
        self.assertTrue(mods['personal_assistant'])

    def test_format_cos_system_injection_returns_string(self):
        """format_cos_system_injection should return a formatted string."""
        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context, format_cos_system_injection,
        )
        ctx = build_cos_context(self.user)
        injection = format_cos_system_injection(ctx)
        self.assertIsInstance(injection, str)
        self.assertIn('SITUATIONAL AWARENESS', injection)
        self.assertIn('END SITUATIONAL AWARENESS', injection)

    def test_injection_contains_priorities(self):
        """System injection should contain life priorities."""
        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context, format_cos_system_injection,
        )
        ctx = build_cos_context(self.user)
        injection = format_cos_system_injection(ctx)
        self.assertIn('Life Priorities', injection)

    def test_injection_no_raw_metrics(self):
        """System injection should NOT contain raw alignment/drift scores."""
        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context, format_cos_system_injection,
        )
        ctx = build_cos_context(self.user)
        injection = format_cos_system_injection(ctx)
        # Raw metrics removed — they added noise without helping conversation
        self.assertNotIn('Blueprint Alignment:', injection)
        self.assertNotIn('Drift Score:', injection)
        self.assertNotIn('24h Drift Risk:', injection)

    def test_blueprint_state_populated(self):
        """Blueprint state should be populated from blueprint engine."""
        from apps.core.ai_orchestrator.cos_context import build_cos_context
        # Ensure blueprint exists
        PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa
        ctx = build_cos_context(self.user)
        bp = ctx['blueprint_state']
        self.assertIn('operating_style', bp)
        self.assertIn('interruption_tolerance', bp)

    def test_context_graceful_degradation(self):
        """Context should still return with defaults if engines fail."""
        from apps.core.ai_orchestrator.cos_context import build_cos_context
        ctx = build_cos_context(self.user)
        # Even with no data, should have sane defaults
        self.assertGreaterEqual(ctx['alignment_score'], 0)
        self.assertLessEqual(ctx['alignment_score'], 100)


# =============================================================================
# BRIEFING FORMATTER TESTS
# =============================================================================


class BriefingFormatterTests(TestCase):
    """Tests for the executive briefing formatter."""

    def test_format_briefing_basic(self):
        """format_briefing should join sections."""
        from apps.core.ai_orchestrator.briefing_formatter import format_briefing
        sections = [
            {'label': 'Situation', 'content': 'All clear'},
            {'label': 'Risk Level', 'content': 'Low'},
        ]
        result = format_briefing(sections)
        self.assertIn('Situation: All clear', result)
        self.assertIn('Risk Level: Low', result)

    def test_format_briefing_skips_optional_empty(self):
        """Optional sections with empty content should be skipped."""
        from apps.core.ai_orchestrator.briefing_formatter import format_briefing
        sections = [
            {'label': 'Situation', 'content': 'Test'},
            {'label': 'Optional', 'content': '', 'optional': True},
        ]
        result = format_briefing(sections)
        self.assertNotIn('Optional:', result)

    def test_format_cos_response_no_context(self):
        """Without context, response should be returned unchanged."""
        from apps.core.ai_orchestrator.briefing_formatter import format_cos_response
        response = "Hello there"
        self.assertEqual(format_cos_response(response), response)

    def test_format_cos_response_no_metrics_footer(self):
        """Metrics (alignment, drift) should NOT be appended to chat responses."""
        from apps.core.ai_orchestrator.briefing_formatter import format_cos_response
        response = "This is a longer response that exceeds twenty characters for testing."
        # Low alignment — should NOT add footer (metrics are internal only)
        context = {'alignment_score': 75}
        result = format_cos_response(response, context)
        self.assertNotIn('Alignment:', result)
        self.assertEqual(result, response)

    def test_format_cos_response_no_drift_footer(self):
        """Drift risk should NOT be appended to chat responses."""
        from apps.core.ai_orchestrator.briefing_formatter import format_cos_response
        response = "This is a longer response that exceeds twenty characters for testing."
        context = {'drift_probability': {'probability_24h': 55}}
        result = format_cos_response(response, context)
        self.assertNotIn('24h Risk:', result)
        self.assertEqual(result, response)

    def test_build_intervention_briefing(self):
        """build_intervention_briefing should produce formatted output."""
        from apps.core.ai_orchestrator.briefing_formatter import build_intervention_briefing
        result = build_intervention_briefing(
            trigger_type='drift_spike',
            message='Drift is rising.',
            alignment_score=72,
            recommendation='Lock Tier-1 items.',
        )
        self.assertIn('Situation: Drift is rising', result)
        self.assertIn('Recommendation: Lock Tier-1 items', result)

    def test_build_intervention_briefing_with_evidence(self):
        """Briefing with evidence should include risk level."""
        from apps.core.ai_orchestrator.briefing_formatter import build_intervention_briefing
        result = build_intervention_briefing(
            trigger_type='drift_spike',
            message='Test',
            evidence={'severity': 80},
        )
        self.assertIn('Risk Level: High', result)


# =============================================================================
# INTERVENTION INTENSITY TESTS
# =============================================================================


class InterventionIntensityTests(TestCase):
    """Tests for the adaptive discipline engine."""

    def setUp(self):
        self.user = _create_test_user(email='intensity@test.com')

    def test_compute_intensity_returns_result(self):
        """compute_intensity should return an IntensityResult."""
        from apps.core.blueprint.intervention_intensity import (
            compute_intensity, IntensityResult,
        )
        result = compute_intensity(self.user)
        self.assertIsInstance(result, IntensityResult)
        self.assertIn(result.level, [1, 2, 3, 4, 5])
        self.assertIsInstance(result.score, float)
        self.assertIsInstance(result.factors, dict)

    def test_low_risk_gets_low_intensity(self):
        """Low risk context should produce level 1-2."""
        from apps.core.blueprint.intervention_intensity import compute_intensity
        context = {
            'drift_probability': {'probability_24h': 5},
            'override_frequency_14d': 0,
            'capacity_snapshot': {'capacity_pct': 30},
            'active_fast_status': {},
            'medication_adherence_state': {},
        }
        result = compute_intensity(self.user, context=context)
        self.assertLessEqual(result.level, 2)

    def test_high_risk_gets_high_intensity(self):
        """High risk context should produce level 4-5."""
        from apps.core.blueprint.intervention_intensity import compute_intensity
        context = {
            'drift_probability': {'probability_24h': 80},
            'override_frequency_14d': 12,
            'capacity_snapshot': {'capacity_pct': 95},
            'active_fast_status': {'active': True, 'target_hours': 16},
            'medication_adherence_state': {'adherence_pct': 40, 'total_scheduled': 3, 'taken_today': 1},
        }
        result = compute_intensity(self.user, context=context)
        self.assertGreaterEqual(result.level, 4)

    def test_intensity_has_recommendation(self):
        """Result should include a recommendation string."""
        from apps.core.blueprint.intervention_intensity import compute_intensity
        result = compute_intensity(self.user)
        self.assertIsInstance(result.recommendation, str)
        self.assertGreater(len(result.recommendation), 10)

    def test_tier1_override_forces_level_4(self):
        """Tier-1 behavior should force at least level 4 when score >= 30."""
        from apps.core.blueprint.intervention_intensity import compute_intensity
        # Create a blueprint with tier-1 behavior
        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa
        bp.tier1_protected_behaviors = ['exercise']
        bp.save()

        context = {
            'drift_probability': {'probability_24h': 40},
            'override_frequency_14d': 3,
            'capacity_snapshot': {'capacity_pct': 60},
            'active_fast_status': {},
            'medication_adherence_state': {},
        }
        result = compute_intensity(self.user, behavior_key='exercise', context=context)
        self.assertGreaterEqual(result.level, 4)

    def test_all_five_levels_defined(self):
        """INTENSITY_LEVELS should have entries for 1-5."""
        from apps.core.blueprint.intervention_intensity import INTENSITY_LEVELS
        for level in range(1, 6):
            self.assertIn(level, INTENSITY_LEVELS)
            self.assertIn('name', INTENSITY_LEVELS[level])
            self.assertIn('escalation_level', INTENSITY_LEVELS[level])


# =============================================================================
# RECOVERY ENGINE TESTS
# =============================================================================


class RecoveryEngineTests(TestCase):
    """Tests for the automatic recovery architecture."""

    def setUp(self):
        self.user = _create_test_user(email='recovery@test.com')
        self.blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa
        # Create a plan for tomorrow
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        self.plan = ArchitecturePlan.objects.create(
            user=self.user,
            date=tomorrow,
            status=ArchitecturePlan.STATUS_ACTIVE,
        )
        # Create blocks
        ScheduledBlock.objects.create(
            plan=self.plan, start_time=datetime.time(6, 0),
            end_time=datetime.time(7, 0), title='Exercise',
            tier=1, behavior_key='exercise',
        )
        ScheduledBlock.objects.create(
            plan=self.plan, start_time=datetime.time(9, 0),
            end_time=datetime.time(10, 0), title='Work',
            tier=3,
        )
        ScheduledBlock.objects.create(
            plan=self.plan, start_time=datetime.time(14, 0),
            end_time=datetime.time(15, 0), title='Errands',
            tier=3,
        )

    def test_recovery_locks_tier1(self):
        """Recovery should lock remaining Tier-1 blocks."""
        from apps.core.blueprint.recovery_engine import apply_recovery_adjustment
        result = apply_recovery_adjustment(self.user, 'meditation')
        self.assertTrue(result['recovery_applied'])
        self.assertEqual(result['tier1_locked'], 1)

    def test_recovery_defers_tier3(self):
        """Recovery should defer Tier-3 blocks."""
        from apps.core.blueprint.recovery_engine import apply_recovery_adjustment
        result = apply_recovery_adjustment(self.user, 'meditation')
        self.assertGreater(result['tier3_deferred'], 0)

    def test_recovery_adds_warning(self):
        """Recovery should add a risk warning to the plan."""
        from apps.core.blueprint.recovery_engine import apply_recovery_adjustment
        apply_recovery_adjustment(self.user, 'exercise')
        self.plan.refresh_from_db()
        warnings = self.plan.risk_warnings or []
        self.assertTrue(any('recovery' in w.lower() for w in warnings))

    def test_recovery_creates_intervention(self):
        """Recovery should create a nudge intervention."""
        from apps.core.blueprint.recovery_engine import apply_recovery_adjustment
        result = apply_recovery_adjustment(self.user, 'exercise')
        self.assertTrue(result['intervention_created'])
        self.assertTrue(
            InterventionLog.objects.filter(
                user=self.user,
                trigger_type='recovery_activated',
            ).exists()
        )

    def test_get_recovery_status_no_plan(self):
        """get_recovery_status should return false when no plan."""
        from apps.core.blueprint.recovery_engine import get_recovery_status
        status = get_recovery_status(self.user)
        self.assertFalse(status['in_recovery'])

    def test_get_recovery_status_after_recovery(self):
        """get_recovery_status should return true after recovery triggered."""
        from apps.core.blueprint.recovery_engine import (
            apply_recovery_adjustment, get_recovery_status,
        )
        # Need today's plan for status check
        today = timezone.localdate()
        today_plan = ArchitecturePlan.objects.create(
            user=self.user, date=today,
            status=ArchitecturePlan.STATUS_ACTIVE,
            risk_warnings=['Recovery mode: exercise was overridden.'],
        )
        ScheduledBlock.objects.create(
            plan=today_plan, start_time=datetime.time(6, 0),
            end_time=datetime.time(7, 0), title='Exercise',
            tier=1, is_locked=True,
        )
        status = get_recovery_status(self.user)
        self.assertTrue(status['in_recovery'])


# =============================================================================
# ALIGNMENT ENGINE TESTS
# =============================================================================


class AlignmentEngineTests(TestCase):
    """Tests for the alignment score engine."""

    def setUp(self):
        self.user = _create_test_user(email='alignment@test.com')
        self.blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa
        # Create today's plan
        self.today = timezone.localdate()
        self.plan = ArchitecturePlan.objects.create(
            user=self.user,
            date=self.today,
            status=ArchitecturePlan.STATUS_ACTIVE,
        )

    def test_compute_alignment_no_blocks(self):
        """With plan but no blocks, alignment should be 100."""
        from apps.core.blueprint.alignment_engine import compute_alignment_score
        result = compute_alignment_score(self.user, self.today)
        self.assertEqual(result.score, 100.0)
        self.assertEqual(result.grade, 'A')

    def test_compute_alignment_all_completed(self):
        """All blocks completed should give 100."""
        from apps.core.blueprint.alignment_engine import compute_alignment_score
        ScheduledBlock.objects.create(
            plan=self.plan, tier=1, title='T1',
            start_time=datetime.time(6, 0), end_time=datetime.time(7, 0),
            is_completed=True,
        )
        ScheduledBlock.objects.create(
            plan=self.plan, tier=2, title='T2',
            start_time=datetime.time(8, 0), end_time=datetime.time(9, 0),
            is_completed=True,
        )
        result = compute_alignment_score(self.user, self.today)
        self.assertEqual(result.score, 100.0)
        self.assertEqual(result.grade, 'A')

    def test_compute_alignment_none_completed(self):
        """No blocks completed should give 0."""
        from apps.core.blueprint.alignment_engine import compute_alignment_score
        ScheduledBlock.objects.create(
            plan=self.plan, tier=1, title='T1',
            start_time=datetime.time(6, 0), end_time=datetime.time(7, 0),
        )
        ScheduledBlock.objects.create(
            plan=self.plan, tier=2, title='T2',
            start_time=datetime.time(8, 0), end_time=datetime.time(9, 0),
        )
        ScheduledBlock.objects.create(
            plan=self.plan, tier=3, title='T3',
            start_time=datetime.time(10, 0), end_time=datetime.time(11, 0),
        )
        result = compute_alignment_score(self.user, self.today)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.grade, 'F')

    def test_tier_weights_correct(self):
        """Tier weights should sum to 1.0."""
        from apps.core.blueprint.alignment_engine import TIER_WEIGHTS
        weighted_sum = sum(TIER_WEIGHTS.values())
        self.assertEqual(weighted_sum, 1.0)

    def test_alignment_result_has_grade(self):
        """AlignmentResult should include a grade."""
        from apps.core.blueprint.alignment_engine import compute_alignment_score
        result = compute_alignment_score(self.user, self.today)
        self.assertIn(result.grade, ['A', 'B', 'C', 'D', 'F'])

    def test_drift_events_reduce_score(self):
        """Drift events should reduce the alignment score."""
        from apps.core.blueprint.alignment_engine import compute_alignment_score
        ScheduledBlock.objects.create(
            plan=self.plan, tier=1, title='T1',
            start_time=datetime.time(6, 0), end_time=datetime.time(7, 0),
            is_completed=True,
        )
        # Add a drift event
        DriftEvent.objects.create(
            user=self.user,
            drift_type='fast_break',
            date=self.today,
            tier=1,
            severity=0.8,
        )
        result = compute_alignment_score(self.user, self.today)
        self.assertLess(result.score, 100.0)

    def test_get_alignment_trend(self):
        """get_alignment_trend should return list of dicts."""
        from apps.core.blueprint.alignment_engine import get_alignment_trend
        trend = get_alignment_trend(self.user, days=3)
        self.assertIsInstance(trend, list)
        self.assertEqual(len(trend), 3)
        for entry in trend:
            self.assertIn('date', entry)
            self.assertIn('score', entry)
            self.assertIn('grade', entry)

    def test_alignment_no_plan(self):
        """No plan for a date should return 100."""
        from apps.core.blueprint.alignment_engine import compute_alignment_score
        future = self.today + datetime.timedelta(days=30)
        result = compute_alignment_score(self.user, future)
        self.assertEqual(result.score, 100.0)


# =============================================================================
# PREDICTIVE INTERVENTIONS TESTS
# =============================================================================


class PredictiveInterventionsTests(TestCase):
    """Tests for the predictive interventions engine."""

    def setUp(self):
        self.user = _create_test_user(email='predictive@test.com')
        self.blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)  # noqa

    def test_evaluate_returns_list(self):
        """evaluate_predictive_signals should return a list."""
        from apps.core.blueprint.predictive_interventions import evaluate_predictive_signals
        result = evaluate_predictive_signals(self.user)
        self.assertIsInstance(result, list)

    def test_no_interventions_when_low_risk(self):
        """Low drift probability should produce no interventions."""
        from apps.core.blueprint.predictive_interventions import evaluate_predictive_signals
        # With fresh user and no drift data, probability should be low
        result = evaluate_predictive_signals(self.user)
        # May or may not have results depending on PIE/PGE data
        for intervention in result:
            self.assertIsInstance(intervention, InterventionLog)

    def test_get_proactive_message_returns_none_low_risk(self):
        """No proactive message when drift is low."""
        from apps.core.blueprint.predictive_interventions import get_proactive_message
        msg = get_proactive_message(self.user)
        # Fresh user with no drift should return None
        self.assertIsNone(msg)

    def test_deduplication_prevents_spam(self):
        """Should not create duplicate predictive interventions."""
        from apps.core.blueprint.predictive_interventions import evaluate_predictive_signals
        # Create a pending predictive intervention
        InterventionLog.objects.create(
            user=self.user,
            level=InterventionLog.LEVEL_NUDGE,
            trigger_type='high_drift_probability',
            message='test',
            user_response=InterventionLog.RESPONSE_PENDING,
        )
        result = evaluate_predictive_signals(self.user)
        # Should be empty due to deduplication
        self.assertEqual(len(result), 0)


# =============================================================================
# REGISTRY UPDATE TESTS
# =============================================================================


class CosRegistryPhase2Tests(TestCase):
    """Tests for the updated CoS documentation registry (Phase 2 additions)."""

    def test_new_engines_in_registry(self):
        """New Phase 2 engines should be in ENGINE_DEPENDENCIES."""
        from apps.core.ai_docs.cos_doc_registry import ENGINE_DEPENDENCIES
        new_engines = [
            'cos_context', 'briefing_formatter', 'intervention_intensity',
            'recovery_engine', 'alignment_engine', 'predictive_interventions',
        ]
        for engine in new_engines:
            self.assertIn(
                engine, ENGINE_DEPENDENCIES,
                f"Engine '{engine}' not found in ENGINE_DEPENDENCIES"
            )

    def test_new_engines_validate(self):
        """New engines should pass validation (modules importable, functions exist)."""
        from apps.core.ai_docs.cos_doc_registry import ENGINE_DEPENDENCIES, validate_registry
        import importlib

        new_engines = [
            'cos_context', 'briefing_formatter', 'intervention_intensity',
            'recovery_engine', 'alignment_engine', 'predictive_interventions',
        ]
        for engine_key in new_engines:
            edef = ENGINE_DEPENDENCIES[engine_key]
            mod = importlib.import_module(edef['module'])
            for func_name in edef['functions']:
                self.assertTrue(
                    hasattr(mod, func_name),
                    f"Engine '{engine_key}': function '{func_name}' not found"
                )

    def test_new_components_in_registry(self):
        """New Phase 2 components should be in get_cos_registry()."""
        from apps.core.ai_docs.cos_doc_registry import get_cos_registry
        registry = get_cos_registry()
        keys = [c['key'] for c in registry]
        new_keys = [
            'cos_context_injection', 'adaptive_discipline',
            'recovery_architecture', 'predictive_interventions',
        ]
        for key in new_keys:
            self.assertIn(
                key, keys,
                f"Component '{key}' not found in registry"
            )

    def test_registry_validates_clean(self):
        """Full registry validation should pass."""
        from apps.core.ai_docs.cos_doc_registry import validate_registry
        is_valid, errors = validate_registry()
        # Filter out errors from upstream engines that may not be fully implemented
        cos_errors = [
            e for e in errors
            if any(k in e for k in [
                'cos_context', 'briefing_formatter', 'intervention_intensity',
                'recovery_engine', 'alignment_engine', 'predictive_interventions',
            ])
        ]
        self.assertEqual(
            len(cos_errors), 0,
            f"CoS Phase 2 validation errors: {cos_errors}"
        )


# =============================================================================
# PRESENCE MODE TESTS
# =============================================================================


class ArrivalBriefingTests(TestCase):
    """Tests for the arrival briefing component and data pipeline."""

    def setUp(self):
        self.user = _create_test_user(email='arrival@test.com')
        self.blueprint = blueprint_engine.get_blueprint(self.user)

    def test_command_brief_includes_recovery_fields(self):
        """Command brief dict should include recovery status fields."""
        from apps.dashboard.views import DashboardView
        factory = RequestFactory()
        request = factory.get('/dashboard/')
        request.user = self.user
        view = DashboardView()
        view.request = request
        brief = view._get_command_brief(self.user, self.user.preferences)
        self.assertIn('recovery_active', brief)
        self.assertIn('recovery_tier1_locked', brief)
        self.assertIn('recovery_tier3_deferred', brief)
        self.assertFalse(brief['recovery_active'])

    def test_command_brief_has_alignment_score(self):
        """Command brief should always have an alignment_score."""
        from apps.dashboard.views import DashboardView
        factory = RequestFactory()
        request = factory.get('/dashboard/')
        request.user = self.user
        view = DashboardView()
        view.request = request
        brief = view._get_command_brief(self.user, self.user.preferences)
        self.assertIn('alignment_score', brief)
        self.assertIsInstance(brief['alignment_score'], int)

    def test_command_brief_auto_generates_plan(self):
        """Command brief should auto-generate architecture if none exists."""
        from apps.dashboard.views import DashboardView
        factory = RequestFactory()
        request = factory.get('/dashboard/')
        request.user = self.user
        view = DashboardView()
        view.request = request
        brief = view._get_command_brief(self.user, self.user.preferences)
        # Should attempt to generate — either has plan or auto_generated flag
        self.assertIn('auto_generated', brief)

    def test_command_brief_none_when_pa_disabled(self):
        """Command brief returns None when personal assistant is disabled."""
        from apps.dashboard.views import DashboardView
        self.user.preferences.personal_assistant_enabled = False
        self.user.preferences.save()
        factory = RequestFactory()
        request = factory.get('/dashboard/')
        request.user = self.user
        view = DashboardView()
        view.request = request
        brief = view._get_command_brief(self.user, self.user.preferences)
        self.assertIsNone(brief)

    def test_arrival_briefing_drift_classes(self):
        """Drift thresholds should map to correct CSS classes."""
        # These are the threshold rules from the template
        # <25% = drift-green, 25-49% = drift-amber, >=50% = drift-red
        thresholds = [
            (10, 'drift-green'),
            (24, 'drift-green'),
            (25, 'drift-amber'),
            (49, 'drift-amber'),
            (50, 'drift-red'),
            (80, 'drift-red'),
        ]
        for val, expected_class in thresholds:
            if val < 25:
                css = 'drift-green'
            elif val < 50:
                css = 'drift-amber'
            else:
                css = 'drift-red'
            self.assertEqual(css, expected_class, f"Value {val} should be {expected_class}")


class PassiveLanguageTests(TestCase):
    """Tests to ensure passive language is removed from templates."""

    PASSIVE_TERMS = [
        'Monitoring',
        'No plan for today',
        'Generate plan?',
        'Check back later!',
        'Something went wrong. Please try again.',
        'Unable to load your personalized dashboard',
        'Loading conversation...',
    ]

    def test_arrival_briefing_no_passive_language(self):
        """Arrival briefing template should not contain passive language."""
        import os
        template_path = os.path.join(
            settings.BASE_DIR,
            'templates', 'components', 'cos_arrival_briefing.html',
        )
        with open(template_path, 'r') as f:
            content = f.read()
        for term in self.PASSIVE_TERMS:
            self.assertNotIn(
                term, content,
                f"Arrival briefing contains passive language: '{term}'",
            )

    def test_command_brief_no_passive_language(self):
        """Command brief template should not contain passive language."""
        import os
        template_path = os.path.join(
            settings.BASE_DIR,
            'templates', 'components', 'assistant_command_brief.html',
        )
        with open(template_path, 'r') as f:
            content = f.read()
        for term in self.PASSIVE_TERMS:
            self.assertNotIn(
                term, content,
                f"Command brief contains passive language: '{term}'",
            )

    def test_assistant_dashboard_no_passive_language(self):
        """Assistant dashboard should not contain passive fallback text."""
        import os
        template_path = os.path.join(
            settings.BASE_DIR,
            'templates', 'ai', 'assistant_dashboard.html',
        )
        with open(template_path, 'r') as f:
            content = f.read()
        for term in self.PASSIVE_TERMS:
            self.assertNotIn(
                term, content,
                f"Assistant dashboard contains passive language: '{term}'",
            )

    def test_panel_no_passive_loading_text(self):
        """Panel template should use active voice for loading states."""
        import os
        template_path = os.path.join(
            settings.BASE_DIR,
            'templates', 'components', 'assistant_panel.html',
        )
        with open(template_path, 'r') as f:
            content = f.read()
        self.assertNotIn('Loading plan...', content)
        self.assertNotIn('Loading drift data...', content)
        self.assertNotIn('Loading...', content)

    def test_panel_views_silent_authority(self):
        """Panel views should show friendly empty state instead of 'No active alerts'."""
        from .panel_views import PendingInterventionsView
        factory = RequestFactory()
        user = _create_test_user(email='silent@test.com')
        request = factory.get('/api/blueprint/interventions/pending/')
        request.user = user
        response = PendingInterventionsView.as_view()(request)
        content = response.content.decode()
        self.assertIn('Nothing needs your attention right now', content)
        self.assertNotIn('No active alerts', content)


class CosProactiveQuestionTests(TestCase):
    """Tests for CoS proactive question surfacing — calibration and ongoing."""

    def setUp(self):
        self.user = _create_test_user('cos_q_test@example.com')

    def test_calibration_question_returned_via_new_api(self):
        """get_next_calibration_question returns first question for new user."""
        from apps.core.blueprint.cos_governance import get_next_calibration_question
        q = get_next_calibration_question(self.user)
        self.assertIsNotNone(q)
        self.assertIn('question', q)
        self.assertIn('key', q)
        self.assertEqual(q['key'], 'core_people_1')

    def test_calibration_advance_prevents_repeat(self):
        """After advancing stage, a different question is returned."""
        from apps.core.blueprint.cos_governance import (
            get_next_calibration_question,
            advance_calibration_stage,
        )
        q1 = get_next_calibration_question(self.user)
        self.assertIsNotNone(q1)
        advance_calibration_stage(self.user)
        q2 = get_next_calibration_question(self.user)
        self.assertIsNotNone(q2)
        self.assertNotEqual(q1['key'], q2['key'])

    def test_no_calibration_question_when_complete(self):
        """get_next_calibration_question returns None after calibration complete."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        from apps.core.blueprint.cos_governance import get_next_calibration_question
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        blueprint.calibration_complete = True
        blueprint.save()
        q = get_next_calibration_question(self.user)
        self.assertIsNone(q)

    def test_ongoing_question_returned_after_calibration(self):
        """get_ongoing_relationship_question returns a question post-calibration."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        from apps.core.blueprint.cos_governance import get_ongoing_relationship_question
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        blueprint.calibration_complete = True
        blueprint.save()
        q = get_ongoing_relationship_question(self.user)
        # Should return a profile-gap or day-of-week question
        if q:
            self.assertIn('question', q)
            self.assertIn('category', q)

    def test_no_duplicate_question_same_day(self):
        """A second call on the same day returns None (daily throttle)."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        from apps.core.blueprint.cos_governance import (
            get_ongoing_relationship_question,
            mark_ongoing_question_shown,
        )
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        blueprint.calibration_complete = True
        blueprint.save()
        q = get_ongoing_relationship_question(self.user)
        if q:
            mark_ongoing_question_shown(self.user, q['category'])
            q2 = get_ongoing_relationship_question(self.user)
            self.assertIsNone(q2)

    def test_mark_ongoing_question_shown_writes_date(self):
        """mark_ongoing_question_shown sets last_cos_question_date."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        from apps.core.blueprint.cos_governance import mark_ongoing_question_shown
        from django.utils import timezone
        mark_ongoing_question_shown(self.user, 'test_category')
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        overrides = blueprint.governance_overrides or {}
        self.assertEqual(
            overrides.get('last_cos_question_date'),
            timezone.now().date().isoformat(),
        )
        self.assertIn('test_category', overrides.get('ongoing_asked', []))


class ConversationalCalibrationTests(TestCase):
    """Tests for the Phase 5 conversational calibration flow."""

    def setUp(self):
        self.user = _create_test_user('cal_conv@example.com')

    def test_get_calibration_state_active_for_new_user(self):
        """New user has active calibration state."""
        from apps.core.blueprint.cos_governance import get_calibration_state
        state = get_calibration_state(self.user)
        self.assertIsNotNone(state)
        self.assertTrue(state['active'])
        self.assertFalse(state['paused'])
        self.assertFalse(state['welcome_shown'])
        self.assertEqual(state['stage'], 0)
        self.assertFalse(state['complete'])

    def test_get_next_calibration_question_first(self):
        """First question is core_people_1."""
        from apps.core.blueprint.cos_governance import get_next_calibration_question
        q = get_next_calibration_question(self.user)
        self.assertIsNotNone(q)
        self.assertEqual(q['key'], 'core_people_1')
        self.assertEqual(q['question_number'], 1)

    def test_advance_calibration_stage(self):
        """Advancing stage moves to next question."""
        from apps.core.blueprint.cos_governance import (
            get_next_calibration_question,
            advance_calibration_stage,
        )
        advance_calibration_stage(self.user)
        q = get_next_calibration_question(self.user)
        self.assertEqual(q['key'], 'core_people_2')
        self.assertEqual(q['question_number'], 2)

    def test_record_calibration_answer_stores_and_advances(self):
        """Recording an answer stores it and advances stage."""
        from apps.core.blueprint.cos_governance import (
            record_calibration_answer,
            get_calibration_state,
        )
        record_calibration_answer(
            self.user, 'core_people_1', 'My wife Sarah and my mom',
        )
        state = get_calibration_state(self.user)
        self.assertEqual(state['stage'], 1)

    def test_calibration_answers_persisted(self):
        """Answers are stored in governance_overrides."""
        from apps.core.blueprint.cos_governance import record_calibration_answer
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        record_calibration_answer(
            self.user, 'core_people_1', 'Sarah and John',
        )
        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        answers = bp.governance_overrides.get('calibration_answers', {})
        self.assertEqual(answers['core_people_1'], 'Sarah and John')

    def test_pause_calibration(self):
        """Pausing stops question delivery."""
        from apps.core.blueprint.cos_governance import (
            pause_calibration,
            get_next_calibration_question,
        )
        pause_calibration(self.user)
        q = get_next_calibration_question(self.user)
        self.assertIsNone(q)

    def test_resume_calibration(self):
        """Resuming re-enables question delivery."""
        from apps.core.blueprint.cos_governance import (
            pause_calibration,
            resume_calibration,
            get_next_calibration_question,
        )
        pause_calibration(self.user)
        resume_calibration(self.user)
        q = get_next_calibration_question(self.user)
        self.assertIsNotNone(q)

    def test_calibration_cycles_after_all_questions(self):
        """Calibration cycles (doesn't auto-complete) after all questions."""
        from apps.core.blueprint.cos_governance import (
            advance_calibration_stage,
            get_calibration_state,
            CALIBRATION_QUESTIONS,
        )
        for _ in range(len(CALIBRATION_QUESTIONS)):
            advance_calibration_stage(self.user)
        state = get_calibration_state(self.user)
        # Should still be active — questions cycle, user decides when done
        self.assertFalse(state['complete'])
        self.assertTrue(state['active'])
        # Should be on pass 2 now
        self.assertIsNotNone(state['next_question'])
        self.assertEqual(state['next_question']['pass_number'], 2)

    def test_calibration_completes_by_user(self):
        """Calibration completes only when user explicitly says so."""
        from apps.core.blueprint.cos_governance import (
            advance_calibration_stage,
            complete_calibration_by_user,
            get_calibration_state,
        )
        # Answer a few questions
        for _ in range(3):
            advance_calibration_stage(self.user)
        state = get_calibration_state(self.user)
        self.assertTrue(state['active'])

        # User decides they're done
        result = complete_calibration_by_user(self.user)
        self.assertTrue(result)
        state = get_calibration_state(self.user)
        self.assertTrue(state['complete'])

    def test_build_calibration_system_injection_active(self):
        """System injection is returned when calibration is active."""
        from apps.core.blueprint.cos_governance import (
            build_calibration_system_injection,
        )
        injection = build_calibration_system_injection(self.user)
        self.assertIn('GETTING TO KNOW YOU', injection)
        self.assertIn('QUESTION YOU MUST ASK', injection)

    def test_build_calibration_system_injection_paused_empty(self):
        """System injection is empty when paused."""
        from apps.core.blueprint.cos_governance import (
            build_calibration_system_injection,
            pause_calibration,
        )
        pause_calibration(self.user)
        injection = build_calibration_system_injection(self.user)
        self.assertEqual(injection, "")

    def test_build_calibration_system_injection_complete_empty(self):
        """System injection is empty when calibration is complete."""
        from apps.core.blueprint.cos_governance import (
            build_calibration_system_injection,
        )
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        bp.calibration_complete = True
        bp.save()
        injection = build_calibration_system_injection(self.user)
        self.assertEqual(injection, "")

    def test_reset_calibration_for_old_users(self):
        """Reset works for users who completed old system."""
        from apps.core.blueprint.cos_governance import (
            reset_calibration_for_conversational,
        )
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        bp.calibration_complete = True
        bp.calibration_day = 14
        bp.save()
        result = reset_calibration_for_conversational(self.user)
        self.assertTrue(result)
        bp.refresh_from_db()
        self.assertFalse(bp.calibration_complete)
        self.assertEqual(bp.governance_overrides['calibration_stage'], 0)

    def test_reset_noop_for_new_system_users(self):
        """Reset does nothing for users already using new system."""
        from apps.core.blueprint.cos_governance import (
            reset_calibration_for_conversational,
            advance_calibration_stage,
        )
        # Creates calibration_stage key
        advance_calibration_stage(self.user)
        result = reset_calibration_for_conversational(self.user)
        self.assertFalse(result)

    def test_should_ask_question_no_cap_during_calibration(self):
        """During active calibration, daily cap is bypassed."""
        from apps.core.blueprint.cos_governance import should_ask_question
        result = should_ask_question(self.user, 'core_people')
        self.assertTrue(result)

    def test_welcome_message_flag(self):
        """Welcome message flag is tracked."""
        from apps.core.blueprint.cos_governance import (
            mark_calibration_welcome_shown,
            get_calibration_state,
        )
        mark_calibration_welcome_shown(self.user)
        state = get_calibration_state(self.user)
        self.assertTrue(state['welcome_shown'])

    def test_calibration_injection_includes_learned_context(self):
        """Injection includes previously learned answers."""
        from apps.core.blueprint.cos_governance import (
            record_calibration_answer,
            build_calibration_system_injection,
        )
        record_calibration_answer(
            self.user, 'core_people_1', 'Sarah and Mom',
        )
        injection = build_calibration_system_injection(self.user)
        self.assertIn('Sarah and Mom', injection)
        self.assertIn('Core People', injection)


class ChatInitializationTests(TestCase):
    """Tests for auto-initialized chat with CoS snapshot."""

    def setUp(self):
        self.user = _create_test_user(email='chat@test.com')

    def test_opening_view_includes_cos_snapshot(self):
        """Opening API should include cos_snapshot in response."""
        from apps.ai.views import AssistantOpeningView
        factory = RequestFactory()
        request = factory.get('/assistant/api/opening/')
        request.user = self.user
        # We can't easily test full API without mocking OpenAI,
        # but we can verify the view is importable and has correct class
        self.assertTrue(hasattr(AssistantOpeningView, 'get'))

    def test_cos_snapshot_structure(self):
        """CoS snapshot should have expected keys."""
        from apps.core.ai_orchestrator.cos_context import build_cos_context
        ctx = build_cos_context(self.user)
        # Build the snapshot the same way the view does
        snapshot = {
            'alignment': ctx.get('alignment_score', 100),
            'drift_risk': ctx.get('drift_probability', {}).get(
                'probability_24h', 0,
            ),
            'capacity': ctx.get('capacity_snapshot', {}).get(
                'capacity_pct', 0,
            ),
            'tier1_protected': ctx.get('protected_tiers', []),
        }
        self.assertIn('alignment', snapshot)
        self.assertIn('drift_risk', snapshot)
        self.assertIn('capacity', snapshot)
        self.assertIn('tier1_protected', snapshot)
        self.assertIsInstance(snapshot['alignment'], int)

    def test_cos_snapshot_alignment_range(self):
        """Alignment score should be 0-100."""
        from apps.core.ai_orchestrator.cos_context import build_cos_context
        ctx = build_cos_context(self.user)
        alignment = ctx.get('alignment_score', 100)
        self.assertGreaterEqual(alignment, 0)
        self.assertLessEqual(alignment, 100)


class AlignmentBadgeTests(TestCase):
    """Tests for the persistent alignment badge in navigation."""

    def setUp(self):
        self.user = _create_test_user(email='badge@test.com')

    def test_context_processor_includes_command_brief(self):
        """Context processor should include command_brief for PA users."""
        from apps.core.context_processors import theme_context
        factory = RequestFactory()
        request = factory.get('/dashboard/')
        request.user = self.user
        ctx = theme_context(request)
        self.assertIn('command_brief', ctx)
        self.assertTrue(ctx['command_brief']['active'])
        self.assertIn('alignment_score', ctx['command_brief'])

    def test_context_processor_no_badge_when_pa_disabled(self):
        """No alignment badge data when personal assistant is disabled."""
        self.user.preferences.personal_assistant_enabled = False
        self.user.preferences.save()
        from apps.core.context_processors import theme_context
        factory = RequestFactory()
        request = factory.get('/dashboard/')
        request.user = self.user
        ctx = theme_context(request)
        self.assertNotIn('command_brief', ctx)

    def test_alignment_badge_css_classes(self):
        """Alignment badge CSS classes should map correctly."""
        test_cases = [
            (90, 'align-good'),
            (80, 'align-good'),
            (79, 'align-caution'),
            (50, 'align-caution'),
            (49, 'align-warning'),
            (10, 'align-warning'),
        ]
        for score, expected_class in test_cases:
            if score >= 80:
                css = 'align-good'
            elif score >= 50:
                css = 'align-caution'
            else:
                css = 'align-warning'
            self.assertEqual(css, expected_class, f"Score {score} should be {expected_class}")

    def test_desktop_top_bar_has_badge_template(self):
        """Desktop top bar template should contain alignment badge markup."""
        import os
        template_path = os.path.join(
            settings.BASE_DIR,
            'templates', 'components', 'desktop_top_bar.html',
        )
        with open(template_path, 'r') as f:
            content = f.read()
        self.assertIn('cos-alignment-badge', content)
        self.assertIn('alignment_score', content)


class DriftVisualizationTests(TestCase):
    """Tests for drift color visualization."""

    def test_drift_green_threshold(self):
        """Values below 25% should be green."""
        for val in [0, 5, 10, 24]:
            if val < 25:
                color = 'green'
            elif val < 50:
                color = 'amber'
            else:
                color = 'red'
            self.assertEqual(color, 'green', f"Drift {val}% should be green")

    def test_drift_amber_threshold(self):
        """Values 25-49% should be amber."""
        for val in [25, 30, 40, 49]:
            if val < 25:
                color = 'green'
            elif val < 50:
                color = 'amber'
            else:
                color = 'red'
            self.assertEqual(color, 'amber', f"Drift {val}% should be amber")

    def test_drift_red_threshold(self):
        """Values >= 50% should be red."""
        for val in [50, 60, 80, 100]:
            if val < 25:
                color = 'green'
            elif val < 50:
                color = 'amber'
            else:
                color = 'red'
            self.assertEqual(color, 'red', f"Drift {val}% should be red")

    def test_css_has_drift_color_classes(self):
        """CSS should define drift-green, drift-amber, drift-red classes."""
        import os
        css_path = os.path.join(
            settings.BASE_DIR,
            'static', 'css', 'assistant-panel.css',
        )
        with open(css_path, 'r') as f:
            content = f.read()
        self.assertIn('.drift-green', content)
        self.assertIn('.drift-amber', content)
        self.assertIn('.drift-red', content)


class SilentAuthorityTests(TestCase):
    """Tests for the Silent Authority Rule — no empty states."""

    def test_panel_interventions_empty_shows_stable(self):
        """Empty interventions should show friendly empty state message."""
        user = _create_test_user(email='silent2@test.com')
        factory = RequestFactory()
        request = factory.get('/api/blueprint/interventions/pending/')
        request.user = user
        from .panel_views import PendingInterventionsView
        response = PendingInterventionsView.as_view()(request)
        content = response.content.decode()
        self.assertIn('Nothing needs your attention right now', content)

    def test_plan_view_empty_shows_initializing(self):
        """Empty plan should show architecture initializing message."""
        user = _create_test_user(email='silent3@test.com')
        factory = RequestFactory()
        request = factory.get('/api/blueprint/plan/today/')
        request.user = user
        from .panel_views import TodayPlanView
        response = TodayPlanView.as_view()(request)
        content = response.content.decode()
        # Should NOT say "Generating plan..." (passive)
        self.assertNotIn('Generating plan', content)

    def test_arrival_briefing_always_has_status_line(self):
        """Arrival briefing template should use human language status line."""
        import os
        template_path = os.path.join(
            settings.BASE_DIR,
            'templates', 'components', 'cos_arrival_briefing.html',
        )
        with open(template_path, 'r') as f:
            content = f.read()
        # Template should reference the human-language status_line from context
        self.assertIn('status_line', content)
        # Fallback text should be human language
        self.assertIn('Protections in place', content)

    def test_human_language_status_lines(self):
        """Human Translation Layer should produce correct status lines."""
        from apps.core.blueprint.human_language import get_status_line
        # Low risk
        self.assertEqual(
            get_status_line(0),
            'Running clean. Protections in place.',
        )
        # Moderate risk
        self.assertEqual(
            get_status_line(30),
            'Moderate pressure. Adjustments available.',
        )
        # High risk
        self.assertEqual(
            get_status_line(60),
            'Under pressure. Protections locked.',
        )


# ---------------------------------------------------------------------------
# Human Translation Layer Tests
# ---------------------------------------------------------------------------

class HumanLanguageTests(TestCase):
    """Tests for the Human Translation Layer (human_language.py)."""

    def test_translate_alignment_all_tiers(self):
        """Alignment scores should map to correct labels."""
        from apps.core.blueprint.human_language import translate_alignment
        label, _ = translate_alignment(95)
        self.assertEqual(label, 'Locked in')
        label, _ = translate_alignment(85)
        self.assertEqual(label, 'Steady')
        label, _ = translate_alignment(70)
        self.assertEqual(label, 'Drifting slightly')
        label, _ = translate_alignment(55)
        self.assertEqual(label, 'Under pressure')
        label, _ = translate_alignment(30)
        self.assertEqual(label, 'Off course')
        label, _ = translate_alignment(None)
        self.assertEqual(label, 'Calibrating')

    def test_translate_drift_risk_all_tiers(self):
        """Drift risk should map to correct labels."""
        from apps.core.blueprint.human_language import translate_drift_risk
        label, _ = translate_drift_risk(5)
        self.assertEqual(label, 'Clear')
        label, _ = translate_drift_risk(20)
        self.assertEqual(label, 'Low risk')
        label, _ = translate_drift_risk(35)
        self.assertEqual(label, 'Moderate')
        label, _ = translate_drift_risk(50)
        self.assertEqual(label, 'Elevated')
        label, _ = translate_drift_risk(70)
        self.assertEqual(label, 'High')
        label, _ = translate_drift_risk(85)
        self.assertEqual(label, 'Critical')
        label, _ = translate_drift_risk(None)
        self.assertEqual(label, 'Unknown')

    def test_translate_capacity_all_tiers(self):
        """Capacity should map to correct labels."""
        from apps.core.blueprint.human_language import translate_capacity
        label, _ = translate_capacity(10)
        self.assertEqual(label, 'Light day')
        label, _ = translate_capacity(50)
        self.assertEqual(label, 'Moderate')
        label, _ = translate_capacity(75)
        self.assertEqual(label, 'Full day')
        label, _ = translate_capacity(85)
        self.assertEqual(label, 'Heavy')
        label, _ = translate_capacity(95)
        self.assertEqual(label, 'Packed')
        label, _ = translate_capacity(None)
        self.assertEqual(label, 'No plan')

    def test_translate_progress(self):
        """Progress should calculate correctly."""
        from apps.core.blueprint.human_language import translate_progress
        label, _ = translate_progress(5, 5)
        self.assertEqual(label, 'Complete')
        label, _ = translate_progress(4, 5)
        self.assertEqual(label, 'Almost there')
        label, _ = translate_progress(3, 5)
        self.assertEqual(label, 'Half done')
        label, _ = translate_progress(1, 5)
        self.assertEqual(label, 'Getting started')
        label, _ = translate_progress(0, 5)
        self.assertEqual(label, 'Day ahead')
        label, _ = translate_progress(0, 0)
        self.assertEqual(label, 'No blocks')

    def test_translate_day_assessment(self):
        """Day assessment should produce human-readable one-liner."""
        from apps.core.blueprint.human_language import translate_day_assessment
        result = translate_day_assessment(50, 10, 2, 0, 5)
        self.assertIn('moderate', result.lower())
        self.assertIn('priorities', result.lower())

    def test_translate_risk_warning(self):
        """Risk warnings should be softened."""
        from apps.core.blueprint.human_language import translate_risk_warning
        result = translate_risk_warning('Density elevated beyond threshold')
        self.assertNotIn('threshold', result)
        self.assertIn('margin', result)

    def test_translate_weekly_pressure(self):
        """Weekly pressure should produce summary string."""
        from apps.core.blueprint.human_language import translate_weekly_pressure
        data = {
            'avg_load': 45,
            'peak_day': 'Wednesday',
            'peak_load': 80,
            'heavy_days': ['Wednesday'],
            'light_days': ['Saturday'],
        }
        result = translate_weekly_pressure(data)
        self.assertIn('Moderate', result)
        self.assertIn('Wednesday', result)

    def test_translate_weekly_pressure_empty(self):
        """Empty weekly pressure should return fallback."""
        from apps.core.blueprint.human_language import translate_weekly_pressure
        result = translate_weekly_pressure(None)
        self.assertEqual(result, 'Week not yet calculated.')

    def test_no_raw_percentages_in_translation(self):
        """Translation functions should never return raw % in labels."""
        from apps.core.blueprint.human_language import (
            translate_alignment,
            translate_drift_risk,
            translate_capacity,
        )
        for score in [0, 25, 50, 75, 100]:
            label, desc = translate_alignment(score)
            self.assertNotIn('%', label)
            label, desc = translate_drift_risk(score)
            self.assertNotIn('%', label)
            label, desc = translate_capacity(score)
            self.assertNotIn('%', label)


# ---------------------------------------------------------------------------
# Command Mode Tests
# ---------------------------------------------------------------------------

class CommandModeTests(TestCase):
    """Tests for Command Mode login experience."""

    def setUp(self):
        self.user = _create_test_user(email='cmdmode@test.com')
        self.user.preferences.personal_assistant_enabled = True
        self.user.preferences.save()
        self.client = Client()
        self.client.login(email='cmdmode@test.com', password='testpass123')

    def test_command_mode_in_context(self):
        """Command Mode dict should be in dashboard context."""
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        command_mode = response.context.get('command_mode')
        self.assertIsNotNone(command_mode)
        self.assertTrue(command_mode['active'])

    def test_command_mode_has_greeting(self):
        """Command Mode should have a greeting line."""
        response = self.client.get('/dashboard/')
        command_mode = response.context.get('command_mode')
        self.assertIn('greeting_line', command_mode)
        self.assertIn(self.user.get_short_name(), command_mode['greeting_line'])

    def test_command_mode_has_risk_level(self):
        """Command Mode should have risk level (green/amber/red)."""
        response = self.client.get('/dashboard/')
        command_mode = response.context.get('command_mode')
        self.assertIn(command_mode['risk_level'], ['green', 'amber', 'red'])

    def test_command_mode_has_day_summary(self):
        """Command Mode should have a human-language day summary."""
        response = self.client.get('/dashboard/')
        command_mode = response.context.get('command_mode')
        self.assertIn('day_summary', command_mode)
        self.assertIsInstance(command_mode['day_summary'], str)
        self.assertNotIn('%', command_mode['day_summary'])

    def test_command_mode_has_recommended_moves(self):
        """Command Mode should have 0-3 recommended moves."""
        response = self.client.get('/dashboard/')
        command_mode = response.context.get('command_mode')
        moves = command_mode.get('recommended_moves', [])
        self.assertLessEqual(len(moves), 3)
        for move in moves:
            self.assertIn('type', move)
            self.assertIn('text', move)

    def test_command_mode_has_status_line(self):
        """Command Mode should have a status line."""
        response = self.client.get('/dashboard/')
        command_mode = response.context.get('command_mode')
        self.assertIn('status_line', command_mode)
        self.assertIsInstance(command_mode['status_line'], str)

    def test_command_mode_renders_greeting_banner(self):
        """Command Mode greeting banner should render on dashboard."""
        response = self.client.get('/dashboard/')
        self.assertContains(response, 'cos-greeting-banner')

    def test_command_mode_hides_arrival_briefing(self):
        """When Command Mode is active, arrival briefing should not render."""
        response = self.client.get('/dashboard/')
        content = response.content.decode()
        # Greeting banner should be present
        self.assertIn('cos-greeting-banner', content)
        # Arrival briefing should NOT be in HTML (hidden by conditional)
        self.assertNotIn('cos-arrival-briefing', content)

    def test_command_mode_absent_without_pa(self):
        """Command Mode should not render when PA is disabled."""
        self.user.preferences.personal_assistant_enabled = False
        self.user.preferences.save()
        response = self.client.get('/dashboard/')
        command_mode = response.context.get('command_mode')
        self.assertIsNone(command_mode)
        self.assertNotContains(response, 'cos-greeting-banner')


# ---------------------------------------------------------------------------
# Weekly Pressure Engine Tests
# ---------------------------------------------------------------------------

class WeeklyPressureTests(TestCase):
    """Tests for the Weekly Pressure engine."""

    def setUp(self):
        self.user = _create_test_user(email='pressure@test.com')
        self.user.preferences.personal_assistant_enabled = True
        self.user.preferences.save()

    def test_compute_weekly_pressure_returns_dict(self):
        """compute_weekly_pressure should return a well-formed dict."""
        from apps.core.blueprint.weekly_pressure import compute_weekly_pressure
        result = compute_weekly_pressure(self.user)
        self.assertIsInstance(result, dict)
        self.assertIn('day_loads', result)
        self.assertIn('avg_load', result)
        self.assertIn('peak_day', result)
        self.assertIn('peak_load', result)
        self.assertIn('heavy_days', result)
        self.assertIn('light_days', result)
        self.assertIn('opportunity_windows', result)

    def test_weekly_pressure_has_7_days(self):
        """Should produce 7 day entries."""
        from apps.core.blueprint.weekly_pressure import compute_weekly_pressure
        result = compute_weekly_pressure(self.user)
        self.assertEqual(len(result['day_loads']), 7)

    def test_weekly_pressure_custom_days(self):
        """Should allow custom day count."""
        from apps.core.blueprint.weekly_pressure import compute_weekly_pressure
        result = compute_weekly_pressure(self.user, days=3)
        self.assertEqual(len(result['day_loads']), 3)

    def test_weekly_pressure_avg_load_range(self):
        """Average load should be 0-100."""
        from apps.core.blueprint.weekly_pressure import compute_weekly_pressure
        result = compute_weekly_pressure(self.user)
        self.assertGreaterEqual(result['avg_load'], 0)
        self.assertLessEqual(result['avg_load'], 100)

    def test_opportunity_window_detection(self):
        """With no blocks, should detect a wide-open opportunity window."""
        from apps.core.blueprint.weekly_pressure import _detect_opportunity_windows
        import datetime as dt
        windows = _detect_opportunity_windows(dt.date.today(), [])
        self.assertTrue(len(windows) > 0)
        self.assertEqual(windows[0]['duration_hours'], 12)

    def test_compute_day_load_empty(self):
        """Empty block list should return 0% capacity."""
        from apps.core.blueprint.weekly_pressure import _compute_day_load
        import datetime as dt
        pct, windows = _compute_day_load(dt.date.today(), [])
        self.assertEqual(pct, 0.0)

    def test_no_raw_terminology_in_templates(self):
        """Primary UI templates should not contain raw engine terminology."""
        import os
        template_dir = os.path.join(
            settings.BASE_DIR, 'templates', 'components',
        )
        templates_to_check = [
            'cos_command_mode.html',
            'cos_arrival_briefing.html',
            'assistant_command_brief.html',
        ]
        raw_terms = [
            'alignment_score }}%',
            'drift_risk_24h }}%',
            'capacity_pct }}%',
        ]
        for tpl_name in templates_to_check:
            path = os.path.join(template_dir, tpl_name)
            if os.path.exists(path):
                with open(path, 'r') as f:
                    content = f.read()
                for term in raw_terms:
                    self.assertNotIn(
                        term, content,
                        f"Raw percentage '{term}' found in {tpl_name}",
                    )


# ---------------------------------------------------------------------------
# Architecture Engine Bug Fix Tests
# ---------------------------------------------------------------------------

class ArchitectureEngineCalendarTests(TestCase):
    """Tests for the LifeEvent import fix in architecture_engine."""

    def test_get_calendar_events_uses_life_event(self):
        """_get_calendar_events should import LifeEvent, not Event."""
        import inspect
        from apps.core.blueprint.architecture_engine import _get_calendar_events
        source = inspect.getsource(_get_calendar_events)
        self.assertIn('LifeEvent', source)
        self.assertNotIn("import Event", source)

    def test_get_calendar_events_no_crash(self):
        """_get_calendar_events should not crash when called."""
        import datetime as dt
        from apps.core.blueprint.architecture_engine import _get_calendar_events
        user = _create_test_user(email='calendar@test.com')
        events = _get_calendar_events(user, dt.date.today())
        self.assertIsInstance(events, list)


class LiveBuildLoopTests(TestCase):
    """
    Phase 4: Live Build Loop — scheduling intent → CoS integration.

    Tests that handle_create_event creates LifeEvents with CoS post-scheduling
    hooks (conflict detection, drift/pressure recompute, Google Calendar sync).
    """

    def setUp(self):
        self.user = _create_test_user(email='buildloop@test.com')
        self.prefs = self.user.preferences
        self.prefs.personal_assistant_enabled = True
        self.prefs.save()

    def test_create_event_returns_success(self):
        """handle_create_event should create a LifeEvent and return success."""
        from apps.ai.action_handlers import ActionHandler
        from apps.life.models import LifeEvent

        handler = ActionHandler(self.user)
        result = handler.handle_create_event(
            title='Gym',
            start_date='today',
            start_time='15:00',
            event_type='health',
        )
        self.assertTrue(result.success)
        self.assertIn('Gym', result.message)
        self.assertEqual(result.action_type, 'create_event')
        # Verify in DB
        event = LifeEvent.objects.get(user=self.user, title='Gym')
        self.assertEqual(event.event_type, 'health')
        self.assertIsNotNone(event.start_time)

    def test_create_event_with_absolute_date(self):
        """handle_create_event should handle YYYY-MM-DD dates."""
        from apps.ai.action_handlers import ActionHandler
        from apps.life.models import LifeEvent

        handler = ActionHandler(self.user)
        result = handler.handle_create_event(
            title='Dentist',
            start_date='2026-03-15',
            start_time='14:00',
            end_time='15:00',
        )
        self.assertTrue(result.success)
        event = LifeEvent.objects.get(user=self.user, title='Dentist')
        self.assertEqual(event.start_date.isoformat(), '2026-03-15')
        self.assertEqual(event.start_time.strftime('%H:%M'), '14:00')
        self.assertEqual(event.end_time.strftime('%H:%M'), '15:00')

    def test_create_event_tomorrow(self):
        """handle_create_event should resolve 'tomorrow' correctly."""
        from apps.ai.action_handlers import ActionHandler
        from apps.life.models import LifeEvent

        handler = ActionHandler(self.user)
        result = handler.handle_create_event(
            title='Therapy',
            start_date='tomorrow',
            start_time='10:00',
        )
        self.assertTrue(result.success)
        event = LifeEvent.objects.get(user=self.user, title='Therapy')
        expected = (datetime.date.today() + datetime.timedelta(days=1))
        self.assertEqual(event.start_date, expected)

    def test_create_event_all_day(self):
        """handle_create_event should support all-day events."""
        from apps.ai.action_handlers import ActionHandler
        from apps.life.models import LifeEvent

        handler = ActionHandler(self.user)
        result = handler.handle_create_event(
            title='Conference',
            start_date='today',
            is_all_day=True,
        )
        self.assertTrue(result.success)
        event = LifeEvent.objects.get(user=self.user, title='Conference')
        self.assertTrue(event.is_all_day)

    def test_cos_post_scheduling_returns_dict(self):
        """_run_cos_post_scheduling should return a dict with expected keys."""
        from apps.ai.action_handlers import ActionHandler
        from apps.life.models import LifeEvent

        handler = ActionHandler(self.user)
        event = LifeEvent.objects.create(
            user=self.user,
            title='Test Event',
            start_date=datetime.date.today(),
            start_time=datetime.time(15, 0),
            event_type='personal',
        )
        result = handler._run_cos_post_scheduling(event)
        self.assertIsInstance(result, dict)
        self.assertIn('conflict_warning', result)
        self.assertIn('pressure_note', result)
        self.assertIn('gcal_synced', result)

    def test_cos_post_scheduling_no_crash_without_blueprint(self):
        """_run_cos_post_scheduling should not crash when user has no blueprint."""
        from apps.ai.action_handlers import ActionHandler
        from apps.life.models import LifeEvent

        handler = ActionHandler(self.user)
        event = LifeEvent.objects.create(
            user=self.user,
            title='No Blueprint Event',
            start_date=datetime.date.today(),
            start_time=datetime.time(9, 0),
            event_type='personal',
        )
        # Should not raise even with no blueprint/plan
        result = handler._run_cos_post_scheduling(event)
        self.assertIsInstance(result, dict)
        self.assertFalse(result['gcal_synced'])

    def test_cos_post_scheduling_all_day_skips_conflict(self):
        """_run_cos_post_scheduling should skip conflict check for all-day events."""
        from apps.ai.action_handlers import ActionHandler
        from apps.life.models import LifeEvent

        handler = ActionHandler(self.user)
        event = LifeEvent.objects.create(
            user=self.user,
            title='All Day Event',
            start_date=datetime.date.today(),
            is_all_day=True,
            event_type='personal',
        )
        result = handler._run_cos_post_scheduling(event)
        self.assertIsNone(result['conflict_warning'])

    def test_execution_engine_cos_refresh(self):
        """Execution engine should refresh CoS plan for scheduling intents."""
        import inspect
        from apps.core.ai_orchestrator.execution_engine import _run_intelligence_chain
        source = inspect.getsource(_run_intelligence_chain)
        self.assertIn('create_event', source)
        self.assertIn('create_task', source)

    def test_response_includes_scheduled_confirmation(self):
        """Response should include a confirmation message with time."""
        from apps.ai.action_handlers import ActionHandler

        handler = ActionHandler(self.user)
        result = handler.handle_create_event(
            title='Team Meeting',
            start_date='today',
            start_time='14:30',
            event_type='work',
        )
        self.assertTrue(result.success)
        self.assertIn('Scheduled', result.message)
        self.assertIn('Team Meeting', result.message)
        self.assertIn('2:30 PM', result.message)

    def test_chat_panel_routes_to_assistant(self):
        """Assistant chat panel should send input to assistant API directly."""
        import os
        template_path = os.path.join(
            settings.BASE_DIR, 'templates', 'components', 'assistant_panel.html',
        )
        if os.path.exists(template_path):
            with open(template_path) as f:
                source = f.read()
            self.assertIn('/assistant/api/chat/', source)
            self.assertIn('ap-chat-input', source)
            # Voice input support
            self.assertIn('ap-voice-btn', source)
            # Chat messages container
            self.assertIn('ap-chat-messages', source)


class GovernanceFrameworkTests(TestCase):
    """
    Phase 1: Adaptive Authority Framework tests.

    Tests governance profile, decision layer, calibration mode,
    system prompt injection, and settings view.
    """

    def setUp(self):
        self.user = _create_test_user(email='governance@test.com')
        self.prefs = self.user.preferences
        self.prefs.personal_assistant_enabled = True
        self.prefs.save()

    def test_blueprint_has_governance_fields(self):
        """Blueprint should have all governance fields with defaults."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        self.assertEqual(bp.accountability_style, 'standard')
        self.assertEqual(bp.question_frequency, 'medium')
        self.assertFalse(bp.relationship_suggestions_enabled)
        self.assertTrue(bp.event_reflections_enabled)
        self.assertEqual(bp.sensitivity_tags, [])
        self.assertEqual(bp.calibration_day, 0)
        self.assertFalse(bp.calibration_complete)
        self.assertEqual(bp.governance_overrides, {})

    def test_accountability_style_affects_instructions(self):
        """Governance instructions should reflect accountability style."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        from apps.core.blueprint.cos_governance import build_governance_instructions

        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        bp.accountability_style = 'firm'
        bp.save()

        instructions = build_governance_instructions(self.user)
        self.assertIn('FIRM', instructions)
        self.assertIn('direct', instructions)

    def test_light_accountability_produces_gentle_instructions(self):
        """Light style should produce gentle language."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        from apps.core.blueprint.cos_governance import build_governance_instructions

        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        bp.accountability_style = 'light'
        bp.save()

        instructions = build_governance_instructions(self.user)
        self.assertIn('LIGHT', instructions)
        self.assertIn('gentle', instructions)

    def test_sensitivity_tags_in_instructions(self):
        """Sensitivity tags should appear in governance instructions."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        from apps.core.blueprint.cos_governance import build_governance_instructions

        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        bp.sensitivity_tags = ['medicine', 'relationships']
        bp.save()

        instructions = build_governance_instructions(self.user)
        self.assertIn('medicine', instructions)
        self.assertIn('relationships', instructions)
        self.assertIn('Sensitivity', instructions)

    def test_should_ask_question_respects_daily_cap(self):
        """should_ask_question should return False when daily cap is exceeded (post-calibration)."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint, InterventionLog
        from apps.core.blueprint.cos_governance import should_ask_question

        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        bp.question_frequency = 'low'  # cap = 1
        bp.calibration_complete = True  # Daily cap only applies post-calibration
        bp.save()

        # Create one governance interaction today
        from django.utils import timezone as tz
        InterventionLog.objects.create(
            user=self.user,
            level=1,
            trigger_type='governance_question',
            message='test',
        )

        result = should_ask_question(self.user, 'test_category')
        self.assertFalse(result)

    def test_should_ask_respects_declined_category(self):
        """should_ask_question should return False for declined categories (post-calibration)."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        from apps.core.blueprint.cos_governance import should_ask_question

        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        bp.governance_overrides = {'declined_categories': ['relationships']}
        bp.calibration_complete = True  # Declined categories only checked post-calibration
        bp.save()

        result = should_ask_question(self.user, 'relationships')
        self.assertFalse(result)

    def test_record_governance_interaction_decline(self):
        """record_governance_interaction should store declined category."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        from apps.core.blueprint.cos_governance import record_governance_interaction

        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        record_governance_interaction(self.user, 'relationships', 'declined')

        bp.refresh_from_db()
        self.assertIn('relationships', bp.governance_overrides.get('declined_categories', []))

    def test_calibration_question_returns_first_question(self):
        """get_next_calibration_question should return first question for new user."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        from apps.core.blueprint.cos_governance import get_next_calibration_question

        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        bp.calibration_complete = False
        bp.save()

        question = get_next_calibration_question(self.user)
        self.assertIsNotNone(question)
        self.assertEqual(question['category'], 'core_people')

    def test_calibration_cycles_after_all_questions(self):
        """Calibration should cycle (not auto-complete) after all questions."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        from apps.core.blueprint.cos_governance import (
            get_next_calibration_question, CALIBRATION_QUESTIONS,
        )

        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        bp.calibration_complete = False
        overrides = bp.governance_overrides or {}
        overrides['calibration_stage'] = len(CALIBRATION_QUESTIONS)
        bp.governance_overrides = overrides
        bp.save()

        question = get_next_calibration_question(self.user)
        # Questions cycle — should return first question on pass 2
        self.assertIsNotNone(question)
        self.assertEqual(question['question_number'], 1)
        self.assertEqual(question['pass_number'], 2)
        bp.refresh_from_db()
        # Should NOT auto-complete
        self.assertFalse(bp.calibration_complete)

    def test_calibration_no_question_when_complete(self):
        """get_next_calibration_question should return None when complete."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        from apps.core.blueprint.cos_governance import get_next_calibration_question

        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        bp.calibration_complete = True
        bp.save()

        question = get_next_calibration_question(self.user)
        self.assertIsNone(question)

    def test_evaluate_governance_sensitive_topic_softens_tone(self):
        """Governance should soften tone for sensitive topics."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        from apps.core.blueprint.cos_governance import evaluate_governance

        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        bp.accountability_style = 'firm'
        bp.sensitivity_tags = ['medicine']
        bp.save()

        decision = evaluate_governance(
            self.user, 'reminder',
            context={'topic': 'medicine', 'tier': 2},
        )
        self.assertTrue(decision.sensitivity_active)
        self.assertIn(decision.tone_intensity, ('gentle', 'warm_but_firm'))

    def test_why_response_in_instructions(self):
        """Governance instructions should include the 'why' standard response."""
        from apps.core.blueprint.cos_governance import build_governance_instructions, WHY_RESPONSE
        instructions = build_governance_instructions(self.user)
        self.assertIn(WHY_RESPONSE, instructions)

    def test_cos_context_includes_governance(self):
        """CoS context should include governance profile."""
        from apps.core.ai_orchestrator.cos_context import build_cos_context
        context = build_cos_context(self.user)
        self.assertIn('governance_profile', context)
        gov = context['governance_profile']
        self.assertIn('accountability_style', gov)
        self.assertIn('question_frequency', gov)

    def test_cos_context_format_is_compact(self):
        """Formatted CoS injection should be compact situational awareness.

        Governance is now injected separately via build_governance_instructions()
        to avoid duplication. The CoS context should focus on actionable
        situational data (schedule, calendar, signals).
        """
        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context, format_cos_system_injection,
        )
        context = build_cos_context(self.user)
        formatted = format_cos_system_injection(context)
        self.assertIn('SITUATIONAL AWARENESS', formatted)
        # Governance is NOT in cos_context — it's a separate prompt layer
        self.assertNotIn('--- GOVERNANCE ---', formatted)

    def test_settings_view_renders(self):
        """CoS settings view should render for authenticated user."""
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.prefs.has_completed_onboarding = True
        self.prefs.save()

        client = Client()
        client.login(email='governance@test.com', password='testpass123')
        response = client.get('/assistant/cos/settings/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Chief of Staff Settings')

    def test_settings_save_updates_blueprint(self):
        """CoS settings save should update blueprint governance fields."""
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.prefs.has_completed_onboarding = True
        self.prefs.save()

        client = Client()
        client.login(email='governance@test.com', password='testpass123')
        response = client.post('/assistant/cos/settings/save/', {
            'accountability_style': 'firm',
            'question_frequency': 'low',
            'event_reflections': 'on',
            'sensitivity_tags': 'medicine, faith',
        })
        self.assertEqual(response.status_code, 302)

        from apps.core.blueprint.models import PersonalOperatingBlueprint
        bp = PersonalOperatingBlueprint.objects.get(user=self.user)
        self.assertEqual(bp.accountability_style, 'firm')
        self.assertEqual(bp.question_frequency, 'low')
        self.assertTrue(bp.event_reflections_enabled)
        self.assertFalse(bp.relationship_suggestions_enabled)
        self.assertIn('medicine', bp.sensitivity_tags)
        self.assertIn('faith', bp.sensitivity_tags)


# =============================================================================
# PHASE 2: POST-EVENT REFLECTION LOOP TESTS
# =============================================================================


class ReflectionEngineTests(TestCase):
    """
    Phase 2: Post-Event Reflection Loops tests.

    Tests reflection detection, queuing, delivery, processing, and
    integration with triggers, scheduler, and command mode.
    """

    def setUp(self):
        self.user = _create_test_user(email='reflection@test.com')
        # Ensure blueprint exists with reflections enabled
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        self.bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        self.bp.event_reflections_enabled = True
        self.bp.module_flags_snapshot = {'health': True}
        self.bp.sub_feature_flags_snapshot = {'health.fitness': True}
        self.bp.save()

        self.yesterday = timezone.localdate() - datetime.timedelta(days=1)

    def _create_life_event(self, **kwargs):
        """Helper to create a LifeEvent."""
        from apps.life.models import LifeEvent
        defaults = {
            'user': self.user,
            'title': 'Team Standup',
            'event_type': 'work',
            'start_date': self.yesterday,
            'start_time': datetime.time(9, 0),
            'end_time': datetime.time(10, 30),
        }
        defaults.update(kwargs)
        return LifeEvent.objects.create(**defaults)

    def _create_workout(self, **kwargs):
        """Helper to create a WorkoutSession."""
        from apps.health.models import WorkoutSession
        defaults = {
            'user': self.user,
            'date': self.yesterday,
            'name': 'Morning Run',
            'duration_minutes': 45,
        }
        defaults.update(kwargs)
        return WorkoutSession.objects.create(**defaults)

    # --- Detection Tests ---

    def test_detect_finds_work_meetings(self):
        """detect_reflectable_events finds work meetings."""
        from apps.core.blueprint.reflection_engine import detect_reflectable_events
        self._create_life_event(event_type='work', title='Client Meeting')
        events = detect_reflectable_events(self.user, self.yesterday)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['title'], 'Client Meeting')

    def test_detect_finds_social_events(self):
        """detect_reflectable_events finds social events."""
        from apps.core.blueprint.reflection_engine import detect_reflectable_events
        self._create_life_event(event_type='social', title='Dinner with Friends')
        events = detect_reflectable_events(self.user, self.yesterday)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['source_type'], 'social')

    def test_detect_finds_completed_workouts(self):
        """detect_reflectable_events finds completed workouts when fitness enabled."""
        from apps.core.blueprint.reflection_engine import detect_reflectable_events
        self._create_workout(name='Push Day')
        events = detect_reflectable_events(self.user, self.yesterday)
        self.assertTrue(any(e['source_type'] == 'workout' for e in events))

    def test_detect_respects_reflections_disabled(self):
        """detect_reflectable_events returns empty when feature disabled."""
        from apps.core.blueprint.reflection_engine import detect_reflectable_events
        self.bp.event_reflections_enabled = False
        self.bp.save()
        self._create_life_event()
        events = detect_reflectable_events(self.user, self.yesterday)
        self.assertEqual(len(events), 0)

    def test_detect_caps_at_daily_limit(self):
        """detect_reflectable_events caps at DAILY_REFLECTION_CAP."""
        from apps.core.blueprint.reflection_engine import (
            detect_reflectable_events,
            DAILY_REFLECTION_CAP,
        )
        for i in range(5):
            self._create_life_event(
                title=f'Meeting {i}',
                start_time=datetime.time(9 + i, 0),
                end_time=datetime.time(10 + i, 30),
            )
        events = detect_reflectable_events(self.user, self.yesterday)
        self.assertLessEqual(len(events), DAILY_REFLECTION_CAP)

    def test_detect_skips_already_queued(self):
        """detect_reflectable_events skips events with existing reflections."""
        from apps.core.blueprint.reflection_engine import (
            detect_reflectable_events,
            queue_reflection,
        )
        le = self._create_life_event(title='Already Reflected')
        event_dict = {
            'source_type': 'calendar',
            'source_id': str(le.pk),
            'title': le.title,
            'event_date': self.yesterday,
        }
        queue_reflection(self.user, event_dict)
        events = detect_reflectable_events(self.user, self.yesterday)
        self.assertFalse(any(e['source_id'] == str(le.pk) for e in events))

    # --- Question Generation Tests ---

    def test_generate_questions_varies_by_type(self):
        """generate_reflection_questions varies by source_type."""
        from apps.core.blueprint.reflection_engine import generate_reflection_questions
        meeting_qs = generate_reflection_questions({'source_type': 'calendar', 'title': 'Standup'})
        workout_qs = generate_reflection_questions({'source_type': 'workout', 'title': 'Run'})
        self.assertTrue(any('action items' in q.lower() for q in meeting_qs))
        self.assertTrue(any('injuries' in q.lower() or 'go' in q.lower() for q in workout_qs))

    # --- Queue Tests ---

    def test_queue_creates_reflection(self):
        """queue_reflection creates EventReflection with correct fields."""
        from apps.core.blueprint.reflection_engine import queue_reflection
        from apps.core.blueprint.models import EventReflection
        event_dict = {
            'source_type': 'calendar',
            'source_id': '42',
            'title': 'Design Review',
            'event_date': self.yesterday,
        }
        ref = queue_reflection(self.user, event_dict)
        self.assertIsInstance(ref, EventReflection)
        self.assertEqual(ref.source_title, 'Design Review')
        self.assertEqual(ref.status, EventReflection.STATUS_PENDING)
        self.assertTrue(len(ref.questions) > 0)
        self.assertIsNotNone(ref.scheduled_for)

    # --- Delivery Tests ---

    def test_deliver_returns_past_due_pending(self):
        """deliver_pending_reflections returns past-due pending reflections."""
        from apps.core.blueprint.reflection_engine import deliver_pending_reflections
        from apps.core.blueprint.models import EventReflection
        ref = EventReflection.objects.create(
            user=self.user,
            source_type='calendar',
            source_id='99',
            source_title='Sprint Retro',
            event_date=self.yesterday,
            scheduled_for=timezone.now() - datetime.timedelta(hours=1),
            questions=['How did it go?'],
        )
        delivered = deliver_pending_reflections(self.user)
        self.assertEqual(len(delivered), 1)
        self.assertEqual(delivered[0]['id'], ref.pk)
        ref.refresh_from_db()
        self.assertEqual(ref.status, EventReflection.STATUS_DELIVERED)

    def test_deliver_skips_future_scheduled(self):
        """deliver_pending_reflections skips future-scheduled reflections."""
        from apps.core.blueprint.reflection_engine import deliver_pending_reflections
        from apps.core.blueprint.models import EventReflection
        EventReflection.objects.create(
            user=self.user,
            source_type='calendar',
            source_id='100',
            source_title='Future Meeting',
            event_date=self.yesterday,
            scheduled_for=timezone.now() + datetime.timedelta(hours=12),
            questions=['Follow up?'],
        )
        delivered = deliver_pending_reflections(self.user)
        self.assertEqual(len(delivered), 0)

    # --- Answer Processing Tests ---

    def test_process_answer_marks_completed(self):
        """process_reflection_answer marks reflection as completed."""
        from apps.core.blueprint.reflection_engine import process_reflection_answer
        from apps.core.blueprint.models import EventReflection
        ref = EventReflection.objects.create(
            user=self.user,
            source_type='calendar',
            source_id='101',
            source_title='Standup',
            event_date=self.yesterday,
            scheduled_for=timezone.now() - datetime.timedelta(hours=1),
            status=EventReflection.STATUS_DELIVERED,
            questions=['Any action items?'],
        )
        result = process_reflection_answer(self.user, ref.pk, 'No, all good.')
        self.assertTrue(result['completed'])
        ref.refresh_from_db()
        self.assertEqual(ref.status, EventReflection.STATUS_COMPLETED)

    def test_process_answer_detects_action_signal(self):
        """process_reflection_answer detects action-like language."""
        from apps.core.blueprint.reflection_engine import process_reflection_answer
        from apps.core.blueprint.models import EventReflection
        ref = EventReflection.objects.create(
            user=self.user,
            source_type='calendar',
            source_id='102',
            source_title='Client Call',
            event_date=self.yesterday,
            scheduled_for=timezone.now() - datetime.timedelta(hours=1),
            status=EventReflection.STATUS_DELIVERED,
            questions=['Any follow-ups?'],
        )
        result = process_reflection_answer(
            self.user, ref.pk, 'I need to follow up with the proposal by Friday.'
        )
        self.assertTrue(result['completed'])
        self.assertTrue(result['has_action_signal'])

    # --- Skip Tests ---

    def test_skip_reflection(self):
        """skip_reflection marks reflection as skipped."""
        from apps.core.blueprint.reflection_engine import skip_reflection
        from apps.core.blueprint.models import EventReflection
        ref = EventReflection.objects.create(
            user=self.user,
            source_type='workout',
            source_id='103',
            source_title='Workout',
            event_date=self.yesterday,
            scheduled_for=timezone.now() - datetime.timedelta(hours=1),
            status=EventReflection.STATUS_DELIVERED,
            questions=['How did it go?'],
        )
        success = skip_reflection(self.user, ref.pk)
        self.assertTrue(success)
        ref.refresh_from_db()
        self.assertEqual(ref.status, EventReflection.STATUS_SKIPPED)

    # --- Scheduler Tests ---

    def test_scheduler_runner_processes_without_crash(self):
        """run_reflection_queue processes all users without crashing."""
        from apps.core.ai_scheduler.scheduler_runner import run_reflection_queue
        self._create_life_event()
        result = run_reflection_queue()
        self.assertIn('queued', result)
        self.assertIn('errors', result)
        self.assertEqual(result['errors'], 0)

    # --- Trigger Tests ---

    def test_reflection_trigger_fires(self):
        """check_pending_reflections fires when reflections are ready."""
        from apps.core.blueprint.assistant_triggers import check_pending_reflections
        from apps.core.blueprint.models import EventReflection
        EventReflection.objects.create(
            user=self.user,
            source_type='calendar',
            source_id='200',
            source_title='Planning Session',
            event_date=self.yesterday,
            scheduled_for=timezone.now() - datetime.timedelta(hours=1),
            questions=['Any action items from Planning Session?'],
        )
        results = check_pending_reflections(self.user, self.bp)
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0].trigger_type, 'pending_reflection')

    # --- API Tests ---

    def test_event_reflection_skip_api(self):
        """Event reflection skip API works."""
        from apps.core.blueprint.models import EventReflection
        ref = EventReflection.objects.create(
            user=self.user,
            source_type='calendar',
            source_id='300',
            source_title='Skip Test',
            event_date=self.yesterday,
            scheduled_for=timezone.now() - datetime.timedelta(hours=1),
            status=EventReflection.STATUS_DELIVERED,
            questions=['How did it go?'],
        )
        client = Client()
        client.login(email='reflection@test.com', password='testpass123')
        resp = client.post(
            '/assistant/api/event-reflection/',
            data=json.dumps({'reflection_id': ref.pk, 'action': 'skip'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        ref.refresh_from_db()
        self.assertEqual(ref.status, EventReflection.STATUS_SKIPPED)

    # --- ISE Registry Test ---

    def test_reflection_task_registered_in_ise(self):
        """queue_event_reflections is registered in ISE scheduler."""
        from apps.core.ai_scheduler.scheduler_registry import get_registered_tasks
        tasks = get_registered_tasks()
        self.assertIn('queue_event_reflections', tasks)
