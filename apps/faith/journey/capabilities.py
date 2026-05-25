"""
Journey domain capability registration.

Additive only. Registered separately from the existing `apps.faith.capabilities`
entry so it does not modify or shadow existing faith capability metadata.

Auto-discovered by `apps.core.domain_registry.registry.autodiscover()` at
Django startup (it scans `<app>.capabilities` for every installed app).

IMPORTANT — Phase 1 boundaries (locked):
    - NO new consumers, NO new behavior, NO PIE/PRIE automation, NO proactive rules
    - This is future-safe discoverability infrastructure only
    - `intent_types` is empty — no CoS intents in Phase 1 (Beth is silent
      on the journey surface)
    - `proactive_signals` is empty — journey does NOT initiate proactive
      surfacing; signals are emitted purely for internal observability
"""

from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability


registry.register(DomainCapability(
    name='faith.journey',
    display_name='Walking With God Through Scripture',
    description=(
        'Guided Bible understanding journey. Isolated submodule under faith. '
        'Reuses the four annotation models from faith (BibleHighlight, '
        'BibleBookmark, BibleStudyNote, SavedVerse); does not couple to the '
        'existing reading-plan models.'
    ),
    intent_types=[],
    primary_models=[
        'JourneyPath',
        'JourneyArc',
        'JourneyDay',
        'UserJourney',
        'UserJourneyDayProgress',
    ],
    context_builders=['build_journey_context_block'],
    proactive_signals=[],
    expected_signal_types=[
        'journey.started',
        'journey.day.completed',
        'journey.arc.completed',
        'journey.application.committed',
        'journey.confusion.flagged',
        'journey.resumed',
    ],
    related_domains=['faith'],
    feature_flag=None,
    url_namespace='journey',
))
