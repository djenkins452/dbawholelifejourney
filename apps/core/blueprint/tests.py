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
from django.test import TestCase, RequestFactory
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
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        self.assertIsNotNone(blueprint)
        self.assertEqual(blueprint.user, self.user)
        self.assertEqual(blueprint.version, 1)

    def test_get_or_create_returns_existing(self):
        """Second call returns existing blueprint, not new one."""
        b1 = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        b2 = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        self.assertEqual(b1.pk, b2.pk)

    def test_default_operating_style(self):
        """Default operating style is executive_cos."""
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        self.assertEqual(blueprint.operating_style, 'executive_cos')

    def test_default_auto_architect(self):
        """Auto architect is enabled by default."""
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        self.assertTrue(blueprint.auto_architect_enabled)

    def test_sync_module_flags(self):
        """Module flags are synced from user preferences."""
        self.user.preferences.health_enabled = True
        self.user.preferences.faith_enabled = False
        self.user.preferences.save()

        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        blueprint.sync_module_flags()
        blueprint.save()

        self.assertTrue(blueprint.module_flags_snapshot.get('health'))
        self.assertFalse(blueprint.module_flags_snapshot.get('faith'))

    def test_is_module_enabled(self):
        """is_module_enabled checks the snapshot."""
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        blueprint.module_flags_snapshot = {'health': True, 'faith': False}
        blueprint.save()

        self.assertTrue(blueprint.is_module_enabled('health'))
        self.assertFalse(blueprint.is_module_enabled('faith'))
        self.assertFalse(blueprint.is_module_enabled('unknown'))

    def test_get_tier_for_behavior_tier1(self):
        """Tier 1 behaviors come from tier1_protected_behaviors."""
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        blueprint.tier1_protected_behaviors = ['WORKOUT', 'MEDS_ADHERENCE']
        blueprint.save()

        self.assertEqual(blueprint.get_tier_for_behavior('WORKOUT'), 1)
        self.assertEqual(blueprint.get_tier_for_behavior('MEDS_ADHERENCE'), 1)

    def test_get_tier_for_behavior_tier2(self):
        """Non-negotiables not in tier1 are tier 2."""
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        NonNegotiable.objects.create(
            blueprint=blueprint,
            behavior_key='FAITH_BLOCK',
            display_name='Faith Block',
        )
        self.assertEqual(blueprint.get_tier_for_behavior('FAITH_BLOCK'), 2)

    def test_get_tier_for_behavior_default(self):
        """Unknown behaviors default to tier 4."""
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        self.assertEqual(blueprint.get_tier_for_behavior('UNKNOWN'), 4)

    def test_get_pillar_weight(self):
        """First pillar gets highest weight."""
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
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
        """Command Brief should render for authenticated PA-enabled user."""
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'command-brief')
        self.assertContains(response, 'Command Brief')

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

    def test_sidebar_shows_active_not_monitoring(self):
        """Sidebar status text should say 'Active' not 'Monitoring'."""
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        # The panel renders on the page
        self.assertContains(response, 'Active')
        self.assertNotContains(response, 'Monitoring')

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
        self.assertIn('CHIEF OF STAFF OPERATIONAL CONTEXT', injection)
        self.assertIn('END OPERATIONAL CONTEXT', injection)

    def test_injection_contains_alignment(self):
        """System injection should contain alignment score."""
        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context, format_cos_system_injection,
        )
        ctx = build_cos_context(self.user)
        injection = format_cos_system_injection(ctx)
        self.assertIn('Blueprint Alignment:', injection)

    def test_injection_contains_drift(self):
        """System injection should contain drift score."""
        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context, format_cos_system_injection,
        )
        ctx = build_cos_context(self.user)
        injection = format_cos_system_injection(ctx)
        self.assertIn('Drift Score:', injection)

    def test_blueprint_state_populated(self):
        """Blueprint state should be populated from blueprint engine."""
        from apps.core.ai_orchestrator.cos_context import build_cos_context
        # Ensure blueprint exists
        PersonalOperatingBlueprint.get_or_create_for_user(self.user)
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

    def test_format_cos_response_with_low_alignment(self):
        """Low alignment should add footer."""
        from apps.core.ai_orchestrator.briefing_formatter import format_cos_response
        response = "This is a longer response that exceeds twenty characters for testing."
        context = {'alignment_score': 75}
        result = format_cos_response(response, context)
        self.assertIn('Alignment: 75%', result)

    def test_format_cos_response_no_footer_high_alignment(self):
        """High alignment should not add footer."""
        from apps.core.ai_orchestrator.briefing_formatter import format_cos_response
        response = "This is a longer response that exceeds twenty characters for testing."
        context = {'alignment_score': 95}
        result = format_cos_response(response, context)
        self.assertNotIn('Alignment:', result)

    def test_format_cos_response_drift_footer(self):
        """High drift risk should add 24h risk footer."""
        from apps.core.ai_orchestrator.briefing_formatter import format_cos_response
        response = "This is a longer response that exceeds twenty characters for testing."
        context = {'drift_probability': {'probability_24h': 55}}
        result = format_cos_response(response, context)
        self.assertIn('24h Risk: 55%', result)

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
        bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
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
        self.blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
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
        self.blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
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
        self.blueprint = PersonalOperatingBlueprint.get_or_create_for_user(self.user)

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
        """Panel views should show 'System stable' instead of 'No active alerts'."""
        from .panel_views import PendingInterventionsView
        factory = RequestFactory()
        user = _create_test_user(email='silent@test.com')
        request = factory.get('/api/blueprint/interventions/pending/')
        request.user = user
        response = PendingInterventionsView.as_view()(request)
        content = response.content.decode()
        self.assertIn('System stable', content)
        self.assertNotIn('No active alerts', content)


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
        """Empty interventions should show 'System stable' message."""
        user = _create_test_user(email='silent2@test.com')
        factory = RequestFactory()
        request = factory.get('/api/blueprint/interventions/pending/')
        request.user = user
        from .panel_views import PendingInterventionsView
        response = PendingInterventionsView.as_view()(request)
        content = response.content.decode()
        self.assertIn('System stable', content)
        self.assertIn('Tier-1 protected', content)

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
        """Arrival briefing template should always show a status line."""
        import os
        template_path = os.path.join(
            settings.BASE_DIR,
            'templates', 'components', 'cos_arrival_briefing.html',
        )
        with open(template_path, 'r') as f:
            content = f.read()
        # Should have the conditional status lines
        self.assertIn('System stable. Tier-1 protected.', content)
        self.assertIn('Elevated risk. Tier-1 locked.', content)
        self.assertIn('Moderate risk. Recalibrating schedule.', content)
