"""
Whole Life Journey - Relationship Intelligence Services

Project: Whole Life Journey
Path: apps/relationships/services.py
Purpose: Analytics, mention parsing, and interaction recording services

Description:
    Platform services for relational intelligence:
    - RelationshipAnalyticsService: Interaction metrics and summaries
    - MentionParserService: @mention detection and record creation

Public API:
    - RelationshipAnalyticsService.record_interaction(person, user, context_type, source_obj)
    - RelationshipAnalyticsService.get_summary(person)
    - RelationshipAnalyticsService.last_interaction(person)
    - RelationshipAnalyticsService.interaction_count(person, timeframe=None)
    - RelationshipAnalyticsService.days_since_last_interaction(person)
    - RelationshipAnalyticsService.context_breakdown(person)
    - RelationshipAnalyticsService.top_interacted(user, limit=10)
    - MentionParserService.parse_and_link(user, text, source_obj)

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import datetime
import logging
import re

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# RELATIONSHIP ANALYTICS SERVICE
# =============================================================================


class RelationshipAnalyticsService:
    """Interaction metrics and structured summaries for Person records."""

    @staticmethod
    def record_interaction(person, user, context_type_label, source_obj=None):
        """
        Record an interaction with a person.

        Creates a RelationshipInteraction and updates denormalized counters
        on the Person record.

        Args:
            person: Person instance
            user: User instance
            context_type_label: str — one of CONTEXT_TYPE_CHOICES values
            source_obj: Optional Django model instance (GenericFK target)

        Returns:
            RelationshipInteraction instance
        """
        from .models import RelationshipInteraction

        today = timezone.localdate()
        kwargs = {
            'person': person,
            'user': user,
            'context_type_label': context_type_label,
            'interaction_date': today,
        }

        if source_obj is not None:
            ct = ContentType.objects.get_for_model(source_obj)
            # Deduplicate: don't record same person + same source object twice
            existing = RelationshipInteraction.objects.filter(
                person=person,
                user=user,
                content_type=ct,
                object_id=source_obj.pk,
            ).exists()
            if existing:
                return None

            kwargs['content_type'] = ct
            kwargs['object_id'] = source_obj.pk

        interaction = RelationshipInteraction.objects.create(**kwargs)

        # Update denormalized counters on Person
        person.last_interaction_date = today
        person.interaction_count = RelationshipInteraction.objects.filter(
            person=person,
        ).count()
        person.save(update_fields=['last_interaction_date', 'interaction_count', 'updated_at'])

        # Also update legacy ai_relationships if it exists
        try:
            from apps.core.ai_relationships.models import Relationship
            Relationship.objects.filter(
                user=user,
                person__display_name=person.display_name,
            ).update(last_interaction=today)
        except Exception:
            pass  # Legacy model may not exist

        return interaction

    @staticmethod
    def last_interaction(person):
        """Return the date of the most recent interaction, or None."""
        return person.last_interaction_date

    @staticmethod
    def interaction_count(person, timeframe=None):
        """
        Count interactions with a person.

        Args:
            person: Person instance
            timeframe: Optional timedelta to limit window

        Returns:
            int
        """
        from .models import RelationshipInteraction

        qs = RelationshipInteraction.objects.filter(person=person)
        if timeframe:
            cutoff = timezone.localdate() - timeframe
            qs = qs.filter(interaction_date__gte=cutoff)
        return qs.count()

    @staticmethod
    def days_since_last_interaction(person):
        """Return days since last interaction, or None if never."""
        if not person.last_interaction_date:
            return None
        return (timezone.localdate() - person.last_interaction_date).days

    @staticmethod
    def context_breakdown(person):
        """
        Break down interactions by context type.

        Returns:
            dict of context_type_label → count
        """
        from .models import RelationshipInteraction

        counts = (
            RelationshipInteraction.objects
            .filter(person=person)
            .values('context_type_label')
            .annotate(count=Count('id'))
        )
        return {row['context_type_label']: row['count'] for row in counts}

    @staticmethod
    def get_summary(person):
        """
        Return a structured interaction summary for a person.

        Returns:
            dict with total_interactions, last_interaction_date,
            and per-context counts
        """
        breakdown = RelationshipAnalyticsService.context_breakdown(person)
        return {
            'total_interactions': person.interaction_count,
            'last_interaction_date': person.last_interaction_date,
            'journal_mentions': breakdown.get('journal', 0),
            'task_mentions': breakdown.get('task', 0),
            'meal_associations': breakdown.get('meal', 0),
            'prayer_mentions': breakdown.get('prayer', 0),
            'event_invitations': breakdown.get('event', 0),
        }

    @staticmethod
    def top_interacted(user, limit=10):
        """
        Return the top N most-interacted-with people for a user.

        Returns:
            QuerySet of Person instances ordered by interaction_count desc
        """
        from .models import Person

        return (
            Person.objects
            .filter(owner=user)
            .order_by('-interaction_count', '-last_interaction_date')
            [:limit]
        )


# =============================================================================
# RELATIONAL HEALTH SERVICE (Phase R2)
# =============================================================================


class RelationalHealthService:
    """
    Computes relational health score and insight metrics.

    Deterministic scoring model (base 100):
    - Subtract 2 per person >45 days no interaction (cap -20)
    - Subtract 1 per severe context imbalance (>70% in one context)
    - Subtract 5 if no event interactions in 30 days
    - Add 1 per consistent weekly interaction pattern (cap +10)

    Caches result for 5 minutes per user.
    """

    # Cache TTL in seconds
    CACHE_TTL = 300

    @classmethod
    def compute_health(cls, user):
        """
        Compute full relational health metrics for a user.

        Returns:
            dict with keys: score, total_contacts, active_7d, stale_30d,
            avg_days_between, top_interacted, longest_no_contact,
            imbalance_flags, insight_lines, stale_relationships_count,
            top_anchor_persons
        """
        from django.core.cache import cache

        cache_key = f'relational_health:{user.pk}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        result = cls._compute(user)
        cache.set(cache_key, result, cls.CACHE_TTL)
        return result

    @classmethod
    def _compute(cls, user):
        from .models import Person, RelationshipInteraction

        today = timezone.localdate()
        seven_days_ago = today - datetime.timedelta(days=7)
        thirty_days_ago = today - datetime.timedelta(days=30)
        forty_five_days_ago = today - datetime.timedelta(days=45)

        contacts = Person.objects.filter(owner=user)
        total_contacts = contacts.count()

        if total_contacts == 0:
            return cls._empty_result()

        # Contacts interacted with in last 7 days
        active_7d_ids = set(
            RelationshipInteraction.objects
            .filter(user=user, interaction_date__gte=seven_days_ago)
            .values_list('person_id', flat=True)
            .distinct()
        )
        active_7d = len(active_7d_ids)

        # Contacts not interacted with in 30+ days
        stale_contacts = contacts.filter(
            Q(last_interaction_date__lt=thirty_days_ago) |
            Q(last_interaction_date__isnull=True)
        )
        stale_30d = stale_contacts.count()

        # Average days between interactions (for contacts with interactions)
        contacts_with_interactions = contacts.filter(
            last_interaction_date__isnull=False,
        )
        if contacts_with_interactions.exists():
            total_days = sum(
                (today - p.last_interaction_date).days
                for p in contacts_with_interactions
            )
            avg_days_between = round(total_days / contacts_with_interactions.count(), 1)
        else:
            avg_days_between = None

        # Top 5 most interacted
        top_interacted = list(
            contacts.filter(interaction_count__gt=0)
            .order_by('-interaction_count')[:5]
            .values('id', 'first_name', 'last_name', 'interaction_count',
                    'last_interaction_date', 'relationship_type')
        )
        for p in top_interacted:
            p['display_name'] = f"{p['first_name']} {p['last_name']}".strip()

        # Top 5 longest no-contact
        longest_no_contact = list(
            contacts.filter(
                Q(last_interaction_date__isnull=False) |
                Q(interaction_count=0)
            )
            .order_by('last_interaction_date')[:5]
            .values('id', 'first_name', 'last_name', 'last_interaction_date',
                    'relationship_type')
        )
        for p in longest_no_contact:
            p['display_name'] = f"{p['first_name']} {p['last_name']}".strip()
            if p['last_interaction_date']:
                p['days_since'] = (today - p['last_interaction_date']).days
            else:
                p['days_since'] = None

        # Context distribution + imbalance detection for top 10
        top_10 = contacts.filter(interaction_count__gt=0).order_by('-interaction_count')[:10]
        context_distributions = []
        imbalance_flags = []

        for person in top_10:
            breakdown = RelationshipAnalyticsService.context_breakdown(person)
            total = sum(breakdown.values())
            if total == 0:
                continue

            pct_breakdown = {k: round(v / total * 100) for k, v in breakdown.items()}
            dist = {
                'person_id': person.pk,
                'display_name': person.get_display_name(),
                'breakdown': breakdown,
                'pct_breakdown': pct_breakdown,
                'total': total,
            }
            context_distributions.append(dist)

            # Flag imbalance: >70% in one context
            for ctx, pct in pct_breakdown.items():
                if pct > 70 and total >= 3:
                    imbalance_flags.append({
                        'person_id': person.pk,
                        'display_name': person.get_display_name(),
                        'dominant_context': ctx,
                        'percentage': pct,
                    })

        # Check for event interactions in last 30 days
        has_recent_events = RelationshipInteraction.objects.filter(
            user=user,
            context_type_label='event',
            interaction_date__gte=thirty_days_ago,
        ).exists()

        # Consistent weekly patterns: contacts interacted with 3+ of last 4 weeks
        weekly_consistent_count = 0
        for person in contacts.filter(interaction_count__gt=0):
            weeks_with_interaction = 0
            for week_offset in range(4):
                week_start = today - datetime.timedelta(days=7 * (week_offset + 1))
                week_end = today - datetime.timedelta(days=7 * week_offset)
                has_week = RelationshipInteraction.objects.filter(
                    person=person,
                    user=user,
                    interaction_date__gte=week_start,
                    interaction_date__lt=week_end,
                ).exists()
                if has_week:
                    weeks_with_interaction += 1
            if weeks_with_interaction >= 3:
                weekly_consistent_count += 1

        # --- SCORING ---
        score = 100

        # Subtract: 2 per person >45 days stale (cap -20)
        very_stale = contacts.filter(
            Q(last_interaction_date__lt=forty_five_days_ago) |
            Q(last_interaction_date__isnull=True, interaction_count=0)
        ).count()
        score -= min(very_stale * 2, 20)

        # Subtract: 1 per imbalance flag
        score -= len(imbalance_flags)

        # Subtract: 5 if no event interactions in 30 days
        if not has_recent_events:
            score -= 5

        # Add: 1 per consistent weekly pattern (cap +10)
        score += min(weekly_consistent_count, 10)

        score = max(0, min(100, score))

        # --- INSIGHT LINES ---
        insight_lines = cls._generate_insights(
            stale_30d, imbalance_flags, top_interacted,
            weekly_consistent_count, active_7d,
        )

        # Top anchor persons (highest consistent positive interaction)
        top_anchors = [
            p['display_name'] for p in top_interacted[:3]
        ]

        return {
            'score': score,
            'total_contacts': total_contacts,
            'active_7d': active_7d,
            'stale_30d': stale_30d,
            'avg_days_between': avg_days_between,
            'top_interacted': top_interacted,
            'longest_no_contact': longest_no_contact,
            'context_distributions': context_distributions,
            'imbalance_flags': imbalance_flags,
            'has_recent_events': has_recent_events,
            'weekly_consistent_count': weekly_consistent_count,
            'insight_lines': insight_lines,
            'stale_relationships_count': stale_30d,
            'top_anchor_persons': top_anchors,
        }

    @classmethod
    def _empty_result(cls):
        return {
            'score': None,
            'total_contacts': 0,
            'active_7d': 0,
            'stale_30d': 0,
            'avg_days_between': None,
            'top_interacted': [],
            'longest_no_contact': [],
            'context_distributions': [],
            'imbalance_flags': [],
            'has_recent_events': False,
            'weekly_consistent_count': 0,
            'insight_lines': ['Add contacts to start tracking relational health.'],
            'stale_relationships_count': 0,
            'top_anchor_persons': [],
        }

    @classmethod
    def _generate_insights(cls, stale_30d, imbalance_flags, top_interacted,
                           weekly_consistent_count, active_7d):
        lines = []

        if stale_30d > 0:
            lines.append(
                f"You haven't interacted with {stale_30d} "
                f"contact{'s' if stale_30d != 1 else ''} in over 30 days."
            )

        if imbalance_flags:
            flag = imbalance_flags[0]
            lines.append(
                f"Most interactions with {flag['display_name']} "
                f"are {flag['dominant_context']}-related."
            )

        if weekly_consistent_count >= 3:
            lines.append("Strong weekly engagement patterns.")

        if active_7d >= 5:
            lines.append(f"Active connections: {active_7d} people this week.")

        if not lines:
            if top_interacted:
                lines.append(
                    f"Top connection: {top_interacted[0]['display_name']} "
                    f"({top_interacted[0]['interaction_count']} interactions)."
                )
            else:
                lines.append("Start adding interactions to build insights.")

        return lines[:3]  # Cap at 3 insight lines


# =============================================================================
# MENTION PARSER SERVICE
# =============================================================================


class MentionParserService:
    """
    Detects @Name patterns in text and creates Mention + Interaction records.

    Matching strategy:
    1. Exact match on display_name (case-insensitive)
    2. Exact match on first_name (case-insensitive)
    3. Fuzzy prefix match on first_name (for partial names)
    """

    # Pattern: @ followed by one or two capitalized words, or quoted name
    # e.g., @John, @John Smith, @"John Smith Jr"
    MENTION_PATTERN = re.compile(
        r'@"([^"]+)"|@([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
    )

    @classmethod
    def parse_and_link(cls, user, text, source_obj, context_type_label=None):
        """
        Parse text for @mentions and create Mention + Interaction records.

        Also detects bare name references (without @) for known contacts.

        Args:
            user: User instance
            text: Text to scan
            source_obj: Django model instance being saved
            context_type_label: Override context type (auto-detected if None)

        Returns:
            list of created Mention instances
        """
        from .models import Mention, Person

        if not text or not text.strip():
            return []

        people = Person.objects.filter(owner=user)
        if not people.exists():
            return []

        ct = ContentType.objects.get_for_model(source_obj)

        if context_type_label is None:
            context_type_label = cls._detect_context_type(source_obj)

        mentions_created = []
        text_lower = text.lower()
        matched_person_ids = set()

        # Phase 1: @mention pattern matching
        for match in cls.MENTION_PATTERN.finditer(text):
            name = match.group(1) or match.group(2)
            person = cls._find_person(people, name)
            if person and person.pk not in matched_person_ids:
                matched_person_ids.add(person.pk)
                mention = cls._create_mention(person, ct, source_obj.pk)
                if mention:
                    mentions_created.append(mention)
                    RelationshipAnalyticsService.record_interaction(
                        person=person,
                        user=user,
                        context_type_label=context_type_label,
                        source_obj=source_obj,
                    )

        # Phase 2: Bare name matching (without @) against known contacts
        for person in people:
            if person.pk in matched_person_ids:
                continue
            # Match display_name or first_name with word boundaries
            names_to_check = [person.display_name.lower()]
            if person.first_name:
                names_to_check.append(person.first_name.lower())

            for name in names_to_check:
                if len(name) < 2:
                    continue
                pattern = r'\b' + re.escape(name) + r'\b'
                if re.search(pattern, text_lower):
                    matched_person_ids.add(person.pk)
                    mention = cls._create_mention(person, ct, source_obj.pk)
                    if mention:
                        mentions_created.append(mention)
                        RelationshipAnalyticsService.record_interaction(
                            person=person,
                            user=user,
                            context_type_label=context_type_label,
                            source_obj=source_obj,
                        )
                    break

        if mentions_created:
            logger.info(
                "MentionParser: %d mentions created for %s in %s #%s",
                len(mentions_created),
                user.email,
                ct.model,
                source_obj.pk,
            )

        return mentions_created

    @classmethod
    def _find_person(cls, people_qs, name):
        """Find a person by name (case-insensitive)."""
        name_lower = name.strip().lower()

        # Exact display_name match
        for person in people_qs:
            if person.display_name.lower() == name_lower:
                return person

        # Exact first_name match
        for person in people_qs:
            if person.first_name.lower() == name_lower:
                return person

        # First name prefix match (fuzzy)
        for person in people_qs:
            if person.first_name.lower().startswith(name_lower) and len(name_lower) >= 3:
                return person

        return None

    @classmethod
    def _create_mention(cls, person, content_type, object_id):
        """Create a Mention record, deduplicating."""
        from .models import Mention

        mention, created = Mention.objects.get_or_create(
            person=person,
            content_type=content_type,
            object_id=object_id,
        )
        return mention if created else None

    @classmethod
    def _detect_context_type(cls, source_obj):
        """Auto-detect context type from the source object's model."""
        model_name = source_obj.__class__.__name__.lower()
        mapping = {
            'journalentry': 'journal',
            'task': 'task',
            'mealplan': 'meal',
            'prayerrequest': 'prayer',
            'lifeevent': 'event',
        }
        return mapping.get(model_name, 'other')
