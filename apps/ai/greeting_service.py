"""
Greeting & Opening Message Mixin — Extracted from PersonalAssistant.

Contains opening message, greeting, reflection-offer, and nudge logic:
- get_opening_message() — main dashboard check-in card entry point
- _get_greeting() — time-aware greeting
- _should_offer_reflection() — whether to offer reflection prompt
- _build_nudges() — action items from state
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class GreetingMixin:
    """Greeting and opening message methods for PersonalAssistant.

    Expects the host class to provide:
    - self.user, self.prefs, self.coaching_style
    - self._get_time_context()
    - self.get_or_create_conversation()
    - self.assess_current_state()
    - self.generate_daily_priorities()
    - self.generate_reflection_prompt()
    """

    def get_opening_message(self, is_first_visit: bool = None) -> Dict[str, Any]:
        """
        Generate the opening message when user opens the app.

        The dashboard check-in card (left side) ALWAYS shows the full coaching review:
        - State summary with AI assessment
        - Today's priorities
        - Nudges for items needing attention

        The is_first_visit flag is tracked for informational purposes but doesn't
        affect what's shown in the check-in card. The coaching review should always
        be visible when viewing the assistant dashboard.

        Note: The CHAT (right side) is separate and should be interactive/responsive,
        not proactively showing task summaries.

        Args:
            is_first_visit: Override for first visit detection (used by views).
                           If None, will be determined automatically.
        """
        from apps.core.utils import get_user_today

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

        # Always show full coaching check-in on the dashboard card
        # This is the "Good morning, Danny" section with your coach reviewing your status
        state = self.assess_current_state()
        priorities = self.generate_daily_priorities()

        result = {
            'greeting': self._get_greeting(),
            'time_context': time_context,
            'state_summary': state.get('ai_assessment', ''),
            'priorities': list(priorities),
            'celebrations': [],
            'nudges': self._build_nudges(state),
            'reflection_prompt': None,
            'coaching_style': self.coaching_style,
            'is_first_visit': is_first_visit,
        }

        # Add reflection prompt if appropriate
        if self._should_offer_reflection():
            result['reflection_prompt'] = self.generate_reflection_prompt('morning')

        return result

    def _get_greeting(self) -> str:
        """Get time-appropriate greeting with urgency when needed."""
        from apps.core.utils import get_user_now

        user_now = get_user_now(self.user)
        hour = user_now.hour

        name = self.user.first_name or self.user.get_short_name()

        # Base greeting varies by time of day
        if hour < 12:
            greeting = f"Good morning, {name}"
        elif hour < 17:
            greeting = f"Good afternoon, {name}"
        else:
            greeting = f"Good evening, {name}"

        # Add time context for later in the day based on coaching style
        if hour >= 18:  # Evening - add urgency
            time_context = self._get_time_context()
            if time_context['hours_remaining'] <= 4:
                if self.coaching_style == 'direct':
                    greeting += f". {time_context['hours_remaining']} hours left today."
                elif self.coaching_style == 'gentle':
                    greeting += ". The evening is here."
                else:  # supportive
                    greeting += ". Let's make the most of the evening."

        return greeting

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

    def _build_nudges(self, state: Dict) -> List[Dict]:
        """Build action items from state - things that REMAIN and need attention."""
        nudges = []
        time_context = self._get_time_context()
        hours_left = time_context['hours_remaining']

        # Overdue tasks - highest priority with time urgency
        tasks = state.get('tasks', {})
        if tasks.get('overdue', 0) > 0:
            overdue = tasks['overdue']
            if self.coaching_style == 'direct':
                msg = f"{overdue} overdue. Handle them now."
            elif hours_left <= 3:
                msg = f"{overdue} overdue tasks. Only {hours_left} hours left today."
            else:
                msg = f"{overdue} overdue tasks need attention."
            nudges.append({
                'type': 'tasks',
                'message': msg,
                'action_url': '/life/tasks/',
                'action_text': 'View Tasks',
                'urgency': 'high'
            })

        # Tasks due today with time awareness
        if tasks.get('due_today', 0) > 0:
            due_today = tasks['due_today']
            if hours_left <= 2:
                msg = f"{due_today} tasks STILL due today. {hours_left} hours to go."
            elif hours_left <= 4:
                msg = f"{due_today} tasks remaining today. Time is running out."
            else:
                msg = f"{due_today} tasks still due today."
            nudges.append({
                'type': 'tasks',
                'message': msg,
                'action_url': '/life/tasks/',
                'action_text': 'View Tasks',
                'urgency': 'medium' if hours_left > 4 else 'high'
            })

        # Journal gap
        journal = state.get('journal', {})
        if journal.get('streak', 0) == 0:
            from apps.journal.models import JournalEntry
            last = JournalEntry.objects.filter(user=self.user).order_by('-entry_date').first()
            if last:
                from apps.core.utils import get_user_today
                days = (get_user_today(self.user) - last.entry_date).days
                if days >= 3:
                    nudges.append({
                        'type': 'journal',
                        'message': f"No journal entries in {days} days.",
                        'action_url': '/journal/new/',
                        'action_text': 'Write Now',
                        'urgency': 'medium'
                    })

        # Medicine adherence gap
        health = state.get('health', {})
        adherence = health.get('medicine_adherence')
        if adherence is not None and adherence < 80:
            nudges.append({
                'type': 'health',
                'message': f"Medicine adherence at {adherence}%.",
                'action_url': '/health/medicine/',
                'action_text': 'Check Medicine',
                'urgency': 'medium'
            })

        return nudges[:3]  # Max 3 action items
