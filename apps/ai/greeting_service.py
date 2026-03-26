"""
Greeting & Opening Message Mixin — Extracted from PersonalAssistant.

Uses the unified CoS pipeline (build_cos_structured_output) as the single
source of truth for day state. NO LLM calls — all output is deterministic.

Contains:
- get_opening_message() — main dashboard check-in card entry point
- _should_offer_reflection() — whether to offer reflection prompt
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class GreetingMixin:
    """Greeting and opening message methods for PersonalAssistant.

    Expects the host class to provide:
    - self.user, self.prefs, self.coaching_style
    - self._get_time_context()
    - self.get_or_create_conversation()
    - self.generate_reflection_prompt()
    """

    def get_opening_message(self, is_first_visit: bool = None) -> Dict[str, Any]:
        """
        Generate the opening message using unified CoS pipeline.

        Uses build_cos_structured_output() as the single source of truth.
        NO LLM calls — all state assessment is deterministic.

        Args:
            is_first_visit: Override for first visit detection (used by views).
                           If None, will be determined automatically.
        """
        from apps.core.utils import get_user_today
        from apps.ai.beth_checkin_renderer import build_cos_structured_output

        today = get_user_today(self.user)
        time_context = self._get_time_context()

        # Track first visit of the day for informational purposes
        if is_first_visit is None:
            conversation = self.get_or_create_conversation()
            metadata = conversation.metadata or {}
            last_opening_date = metadata.get('last_opening_shown_date')
            is_first_visit = last_opening_date != str(today)

            # Update the last opening shown date
            if is_first_visit:
                metadata['last_opening_shown_date'] = str(today)
                conversation.metadata = metadata
                conversation.save(update_fields=['metadata'])

        # Unified CoS pipeline — deterministic, no LLM
        structured = build_cos_structured_output(self.user)

        # Build state summary from deterministic components
        state_parts = []
        if structured.get('day_narrative'):
            state_parts.append(structured['day_narrative'])
        if structured.get('state_text'):
            state_parts.append(structured['state_text'])
        state_summary = ' '.join(state_parts)

        # Map do_now to priority dicts for backward compatibility
        priorities = [
            {
                'priority_type': 'commitment',
                'title': item['name'],
                'description': f"Estimated {item['duration_est']} minutes",
                'why_important': '',
            }
            for item in structured.get('do_now', [])
        ]

        # Map move_later to nudge dicts
        nudges = [
            {
                'type': 'adjustment',
                'message': f"{item['name']} — {item['reason']}.",
                'action_url': '/life/tasks/',
                'action_text': 'Reschedule',
                'urgency': 'medium',
            }
            for item in structured.get('move_later', [])[:3]
        ]

        result = {
            'greeting': structured.get('greeting', ''),
            'time_context': time_context,
            'state_summary': state_summary,
            'priorities': priorities,
            'celebrations': [],
            'nudges': nudges,
            'reflection_prompt': None,
            'coaching_style': self.coaching_style,
            'is_first_visit': is_first_visit,
            'cos_structured': structured,
        }

        # Add reflection prompt if appropriate
        if self._should_offer_reflection():
            result['reflection_prompt'] = self.generate_reflection_prompt('morning')

        return result

    def _should_offer_reflection(self) -> bool:
        """Determine if we should offer a reflection prompt."""
        from apps.journal.models import JournalEntry
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)

        # Check if already journaled today
        journaled_today = JournalEntry.objects.filter(
            user=self.user,
            entry_date=today
        ).exists()

        return not journaled_today
