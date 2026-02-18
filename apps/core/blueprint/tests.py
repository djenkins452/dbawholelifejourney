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
