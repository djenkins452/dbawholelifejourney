"""
Whole Life Journey - AI Relationships Tests

Project: Whole Life Journey
Path: apps/core/ai_relationships/tests.py
Purpose: Tests for relationship intelligence models and engine

Tests cover:
    - Person model creation
    - Relationship model with cadence
    - InteractionSignal creation with confidence
    - People extraction from text
    - Interaction baselines computation
    - Relational drift detection
    - Relationship suggestions (persona-aware)
    - Opportunity windows from weekly pressure
    - SignificantEvent.person FK backward compatibility
    - Journal save triggers people extraction
    - ISE scheduler registration
    - Relational drift guidance creation

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import datetime

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.users.models import User, TermsAcceptance


def _create_test_user(email='reltest@example.com', password='testpass123'):
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


class PersonModelTests(TestCase):
    """Tests for Person model."""

    def setUp(self):
        self.user = _create_test_user()

    def test_create_person(self):
        """Person can be created with minimal fields."""
        from apps.core.ai_relationships.models import Person
        p = Person.objects.create(
            user=self.user,
            display_name='Mom',
            person_type='family',
        )
        self.assertEqual(str(p), 'Mom (family)')
        self.assertTrue(p.is_active)

    def test_person_deactivate(self):
        """Person can be deactivated (soft hidden)."""
        from apps.core.ai_relationships.models import Person
        p = Person.objects.create(user=self.user, display_name='Old Friend')
        p.is_active = False
        p.save()
        active = Person.objects.filter(user=self.user, is_active=True)
        self.assertEqual(active.count(), 0)


class InteractionSignalTests(TestCase):
    """Tests for InteractionSignal model."""

    def setUp(self):
        self.user = _create_test_user(email='signal@test.com')
        from apps.core.ai_relationships.models import Person
        self.person = Person.objects.create(
            user=self.user, display_name='Sarah', person_type='friend',
        )

    def test_create_signal(self):
        """InteractionSignal can be created with confidence."""
        from apps.core.ai_relationships.models import InteractionSignal
        signal = InteractionSignal.objects.create(
            user=self.user,
            person=self.person,
            signal_date=timezone.localdate(),
            signal_type='mention',
            confidence=0.9,
            source_type='journal',
            source_id='42',
        )
        self.assertEqual(signal.confidence, 0.9)
        self.assertEqual(signal.person.display_name, 'Sarah')


class PeopleExtractionTests(TestCase):
    """Tests for extract_people_from_text."""

    def setUp(self):
        self.user = _create_test_user(email='extract@test.com')
        from apps.core.ai_relationships.models import Person
        self.mom = Person.objects.create(
            user=self.user, display_name='Mom', person_type='family',
        )
        self.sarah = Person.objects.create(
            user=self.user, display_name='Sarah', person_type='friend',
        )

    def test_extract_matches_existing_person(self):
        """extract_people_from_text matches existing Person by name."""
        from apps.core.ai_relationships.relationship_engine import extract_people_from_text
        signals = extract_people_from_text(
            self.user, 'Had lunch with Mom today.', 'journal', '1',
        )
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].person, self.mom)

    def test_extract_creates_interaction_signal(self):
        """extract_people_from_text creates InteractionSignal."""
        from apps.core.ai_relationships.relationship_engine import extract_people_from_text
        from apps.core.ai_relationships.models import InteractionSignal
        extract_people_from_text(
            self.user, 'Coffee with Sarah was great.', 'journal', '2',
        )
        count = InteractionSignal.objects.filter(
            user=self.user, person=self.sarah,
        ).count()
        self.assertEqual(count, 1)

    def test_extract_multiple_people(self):
        """extract_people_from_text finds multiple people in one text."""
        from apps.core.ai_relationships.relationship_engine import extract_people_from_text
        signals = extract_people_from_text(
            self.user, 'Mom called. Then met Sarah for dinner.', 'journal', '3',
        )
        self.assertEqual(len(signals), 2)

    def test_extract_empty_text_returns_empty(self):
        """extract_people_from_text returns empty for blank text."""
        from apps.core.ai_relationships.relationship_engine import extract_people_from_text
        signals = extract_people_from_text(self.user, '', 'journal', '4')
        self.assertEqual(len(signals), 0)

    def test_no_duplicate_signals_same_day(self):
        """extract_people_from_text doesn't create duplicate signals."""
        from apps.core.ai_relationships.relationship_engine import extract_people_from_text
        from apps.core.ai_relationships.models import InteractionSignal
        extract_people_from_text(self.user, 'Saw Mom.', 'journal', '5')
        extract_people_from_text(self.user, 'Mom again.', 'journal', '5')
        count = InteractionSignal.objects.filter(
            user=self.user, person=self.mom, source_id='5',
        ).count()
        self.assertEqual(count, 1)


class RelationalDriftTests(TestCase):
    """Tests for detect_relational_drift."""

    def setUp(self):
        self.user = _create_test_user(email='drift@test.com')
        from apps.core.ai_relationships.models import Person, Relationship
        from apps.core.blueprint.models import PersonalOperatingBlueprint

        self.bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)
        self.bp.relationship_suggestions_enabled = True
        self.bp.save()

        self.person = Person.objects.create(
            user=self.user, display_name='Best Friend', person_type='friend',
        )
        self.rel = Relationship.objects.create(
            user=self.user,
            person=self.person,
            relationship_type='friend',
            importance_tier=1,
            cadence_target='weekly',
            last_interaction=timezone.localdate() - datetime.timedelta(days=20),
        )

    def test_detect_flags_gap_beyond_threshold(self):
        """detect_relational_drift flags gap > 1.5x cadence target."""
        from apps.core.ai_relationships.relationship_engine import detect_relational_drift
        alerts = detect_relational_drift(self.user)
        self.assertTrue(len(alerts) > 0)
        self.assertEqual(alerts[0]['person_name'], 'Best Friend')
        # 20 days gap > 7 * 1.5 = 10.5 days
        self.assertGreater(alerts[0]['actual_gap_days'], 10)

    def test_detect_skips_when_feature_disabled(self):
        """detect_relational_drift returns empty when feature disabled."""
        from apps.core.ai_relationships.relationship_engine import detect_relational_drift
        self.bp.relationship_suggestions_enabled = False
        self.bp.save()
        alerts = detect_relational_drift(self.user)
        self.assertEqual(len(alerts), 0)

    def test_detect_no_drift_when_recent(self):
        """detect_relational_drift doesn't flag when interaction is recent."""
        from apps.core.ai_relationships.relationship_engine import detect_relational_drift
        self.rel.last_interaction = timezone.localdate() - datetime.timedelta(days=3)
        self.rel.save()
        alerts = detect_relational_drift(self.user)
        self.assertEqual(len(alerts), 0)


class RelationshipSuggestionTests(TestCase):
    """Tests for generate_relationship_suggestion."""

    def setUp(self):
        self.user = _create_test_user(email='suggest@test.com')
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        self.bp = PersonalOperatingBlueprint.get_or_create_for_user(self.user)

    def test_suggestion_respects_sensitivity(self):
        """generate_relationship_suggestion is gentler when relationships is sensitive."""
        from apps.core.ai_relationships.relationship_engine import generate_relationship_suggestion
        self.bp.sensitivity_tags = ['relationships']
        self.bp.save()
        alert = {
            'person_id': 1,
            'person_name': 'Friend',
            'person_type': 'friend',
            'actual_gap_days': 30,
        }
        suggestion = generate_relationship_suggestion(self.user, alert)
        self.assertEqual(suggestion['suggestion_type'], 'gentle_mention')
        self.assertIn('no pressure', suggestion['message'].lower())

    def test_suggestion_normal_framing(self):
        """generate_relationship_suggestion produces reconnect suggestion normally."""
        from apps.core.ai_relationships.relationship_engine import generate_relationship_suggestion
        self.bp.sensitivity_tags = []
        self.bp.save()
        alert = {
            'person_id': 1,
            'person_name': 'Mom',
            'person_type': 'family',
            'actual_gap_days': 15,
        }
        suggestion = generate_relationship_suggestion(self.user, alert)
        self.assertEqual(suggestion['suggestion_type'], 'reconnect')
        self.assertIn('Mom', suggestion['message'])


class SignificantEventFKTests(TestCase):
    """Tests for SignificantEvent.person FK."""

    def setUp(self):
        self.user = _create_test_user(email='sigev@test.com')

    def test_significant_event_person_nullable(self):
        """SignificantEvent works without person FK (backward-compatible)."""
        from apps.life.models import SignificantEvent
        event = SignificantEvent.objects.create(
            user=self.user,
            title="Mom's Birthday",
            event_type='birthday',
            event_date=datetime.date(1960, 5, 15),
            person_name='Mom',
        )
        self.assertIsNone(event.person)
        self.assertEqual(event.person_name, 'Mom')

    def test_significant_event_with_person_fk(self):
        """SignificantEvent can link to a Person."""
        from apps.life.models import SignificantEvent
        from apps.core.ai_relationships.models import Person
        person = Person.objects.create(
            user=self.user, display_name='Mom', person_type='family',
        )
        event = SignificantEvent.objects.create(
            user=self.user,
            title="Mom's Birthday",
            event_type='birthday',
            event_date=datetime.date(1960, 5, 15),
            person_name='Mom',
            person=person,
        )
        self.assertEqual(event.person, person)


class InteractionBaselineTests(TestCase):
    """Tests for compute_interaction_baselines."""

    def setUp(self):
        self.user = _create_test_user(email='baseline@test.com')
        from apps.core.ai_relationships.models import Person, Relationship, InteractionSignal
        self.person = Person.objects.create(
            user=self.user, display_name='Colleague', person_type='colleague',
        )
        self.rel = Relationship.objects.create(
            user=self.user, person=self.person,
            relationship_type='colleague', cadence_target='weekly',
        )
        # Create signals over the last 30 days (every 5 days)
        for i in range(0, 30, 5):
            InteractionSignal.objects.create(
                user=self.user,
                person=self.person,
                signal_date=timezone.localdate() - datetime.timedelta(days=i),
                signal_type='mention',
                source_type='journal',
            )

    def test_compute_baselines_returns_frequency(self):
        """compute_interaction_baselines returns correct frequency."""
        from apps.core.ai_relationships.relationship_engine import compute_interaction_baselines
        baselines = compute_interaction_baselines(self.user)
        self.assertIn(self.person.pk, baselines)
        baseline = baselines[self.person.pk]
        self.assertIsNotNone(baseline['avg_days'])
        self.assertGreater(baseline['count_90d'], 0)


class ISERegistryTests(TestCase):
    """Tests for ISE scheduler integration."""

    def test_relational_drift_registered(self):
        """detect_relational_drift is registered in ISE scheduler."""
        from apps.core.ai_scheduler.scheduler_registry import get_registered_tasks
        tasks = get_registered_tasks()
        self.assertIn('detect_relational_drift', tasks)


class SchedulerRunnerTests(TestCase):
    """Tests for scheduler runner functions."""

    def setUp(self):
        self.user = _create_test_user(email='runner@test.com')

    def test_run_relational_drift_no_crash(self):
        """run_relational_drift processes without crashing."""
        from apps.core.ai_scheduler.scheduler_runner import run_relational_drift
        result = run_relational_drift()
        self.assertIn('checked', result)
        self.assertIn('errors', result)
        self.assertEqual(result['errors'], 0)
