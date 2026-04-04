"""
Priority & Reflection Generator Mixin — Extracted from PersonalAssistant.

Contains all priority generation and reflection prompt logic:
- generate_daily_priorities() — main daily priority entry point
- _generate_*_priority() — domain-specific priority generators
- generate_reflection_prompt() — reflection prompt entry point
- _*_prompts() — context-specific prompt generators
"""

import logging
from typing import Optional, Dict, List

from django.db import transaction

from .models import DailyPriority, ReflectionPromptQueue

logger = logging.getLogger(__name__)


class PriorityGeneratorMixin:
    """Priority and reflection generation methods for PersonalAssistant.

    Expects the host class to provide:
    - self.user, self.prefs, self.faith_enabled, self.coaching_style
    - self.assess_current_state()
    """

    def generate_daily_priorities(self, force_refresh: bool = False) -> List[Dict]:
        """
        Generate AI-suggested daily priorities.

        Follows the prioritization order:
        1. Faith and spiritual alignment
        2. Stated Purpose and core values
        3. Long-term goals
        4. Commitments already made
        5. Maintenance tasks
        6. Optional or low-impact items
        """
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)

        # Check for existing priorities
        existing = DailyPriority.objects.filter(
            user=self.user,
            priority_date=today,
            user_dismissed=False
        )

        if existing.exists() and not force_refresh:
            return list(existing.values())

        # On refresh: preserve completed priorities, only regenerate non-completed ones
        completed_count = 0
        completed_titles = set()
        if force_refresh:
            # Keep completed priorities - they represent accomplished work!
            completed_existing = existing.filter(is_completed=True)
            completed_count = completed_existing.count()
            # Track titles of completed priorities to avoid duplicates
            completed_titles = set(completed_existing.values_list('title', flat=True))

            # Only delete non-completed, non-dismissed priorities
            existing.filter(is_completed=False).delete()

        # Calculate how many new priorities we need (max 5 total)
        max_new_priorities = 5 - completed_count

        # If all 5 are already completed, just return what we have
        if max_new_priorities <= 0:
            return DailyPriority.objects.filter(
                user=self.user,
                priority_date=today,
                user_dismissed=False
            ).values()

        # Gather context for priority generation
        state = self.assess_current_state()
        context = self._build_priority_context(state)

        priorities = []
        sort_order = completed_count  # Start after completed priorities

        # 1. Faith priority (if enabled and has gaps)
        if self.faith_enabled and len(priorities) < max_new_priorities:
            faith_priority = self._generate_faith_priority(state, context)
            if faith_priority and faith_priority['title'] not in completed_titles:
                faith_priority['sort_order'] = sort_order
                priorities.append(faith_priority)
                sort_order += 1

        # 2. Purpose/Goal priorities
        purpose_priorities = self._generate_purpose_priorities(state, context)
        for p in purpose_priorities[:2]:  # Max 2 goal priorities
            if len(priorities) >= max_new_priorities:
                break
            if p['title'] not in completed_titles:
                p['sort_order'] = sort_order
                priorities.append(p)
                sort_order += 1

        # 3. Commitment priorities (overdue/due today tasks)
        commitment_priorities = self._generate_commitment_priorities(state)
        for p in commitment_priorities[:2]:  # Max 2 commitment priorities
            if len(priorities) >= max_new_priorities:
                break
            if p['title'] not in completed_titles:
                p['sort_order'] = sort_order
                priorities.append(p)
                sort_order += 1

        # Limit to remaining slots
        priorities = priorities[:max_new_priorities]

        # Save to database
        with transaction.atomic():
            for p in priorities:
                DailyPriority.objects.create(
                    user=self.user,
                    priority_date=today,
                    priority_type=p.get('priority_type', 'personal'),
                    title=p['title'],
                    description=p.get('description', ''),
                    why_important=p.get('why_important', ''),
                    linked_task_id=p.get('linked_task_id'),
                    linked_goal_id=p.get('linked_goal_id'),
                    linked_intention_id=p.get('linked_intention_id'),
                    sort_order=p['sort_order'],
                    generation_context=str(context)[:500],
                )

        return DailyPriority.objects.filter(
            user=self.user,
            priority_date=today,
            user_dismissed=False
        ).values()

    def _build_priority_context(self, state: Dict) -> Dict:
        """Build context for priority generation."""
        return {
            'overdue_tasks': state.get('tasks', {}).get('overdue', 0),
            'due_today': state.get('tasks', {}).get('due_today', 0),
            'active_goals': state.get('goals', {}).get('active', 0),
            'active_prayers': state.get('faith', {}).get('active_prayers', 0),
            'journal_streak': state.get('journal', {}).get('streak', 0),
            'workout_streak': state.get('health', {}).get('workout_streak', 0),
            'alignment_gaps': state.get('alignment_gaps', []),
        }

    def _generate_faith_priority(self, state: Dict, context: Dict) -> Optional[Dict]:
        """Generate faith-related priority if appropriate."""
        # Check if user has been spiritually quiet
        state.get('journal', {})
        faith_data = state.get('faith', {})

        # Suggest Bible study if no recent spiritual activity
        if faith_data.get('active_prayers', 0) == 0:
            return {
                'priority_type': 'faith',
                'title': 'Start your day with prayer',
                'description': 'Take a moment to connect with God and set your intentions for the day.',
                'why_important': 'Faith alignment is your foundation for living purposefully.',
            }

        # Suggest Scripture if haven't journaled with faith context
        return {
            'priority_type': 'faith',
            'title': 'Spend time in Scripture',
            'description': 'Read and reflect on God\'s Word to anchor your day.',
            'why_important': 'Staying grounded in faith helps you make aligned decisions.',
        }

    def _generate_purpose_priorities(self, state: Dict, context: Dict) -> List[Dict]:
        """
        Generate priorities based on goals, milestones, and intentions.

        Uses smart rotation to ensure all goals get attention:
        1. Goals with overdue milestones are highest priority
        2. Goals that haven't been shown recently are prioritized
        3. Goals shown but not completed (user not making progress) are prioritized
        4. Goals recently shown AND completed are deprioritized (already being worked on)
        """
        from apps.purpose.models import LifeGoal, ChangeIntention, GoalMilestone
        from apps.core.utils import get_user_today
        from datetime import timedelta

        priorities = []
        today = get_user_today(self.user)
        lookback_days = 7  # Consider last 7 days of priorities

        # Get all active goals with their milestones
        all_goals = list(LifeGoal.objects.filter(
            user=self.user,
            status='active'
        ).prefetch_related('milestones'))

        if not all_goals:
            # No goals - fall through to intentions
            pass
        else:
            # First, check for overdue milestones (highest priority)
            overdue_milestones = GoalMilestone.objects.filter(
                goal__user=self.user,
                goal__status='active',
                completed=False,
                target_date__lt=today
            ).select_related('goal').order_by('target_date')[:2]

            for milestone in overdue_milestones:
                days_overdue = (today - milestone.target_date).days
                priorities.append({
                    'priority_type': 'milestone_overdue',
                    'title': f'Overdue milestone: {milestone.title[:40]}',
                    'description': f'Goal: {milestone.goal.title}',
                    'why_important': f'This milestone is {days_overdue} day{"s" if days_overdue != 1 else ""} overdue. Consider completing it or adjusting the date.',
                    'linked_goal_id': milestone.goal.id,
                    'linked_milestone_id': milestone.id,
                })

            # Get recent priorities linked to goals (last 7 days)
            recent_goal_priorities = DailyPriority.objects.filter(
                user=self.user,
                priority_date__gte=today - timedelta(days=lookback_days),
                linked_goal_id__isnull=False
            ).values('linked_goal_id', 'is_completed', 'priority_date')

            # Build a map: goal_id -> {shown_count, completed_count, last_shown}
            goal_activity = {}
            for p in recent_goal_priorities:
                gid = p['linked_goal_id']
                if gid not in goal_activity:
                    goal_activity[gid] = {'shown': 0, 'completed': 0, 'last_shown': None}
                goal_activity[gid]['shown'] += 1
                if p['is_completed']:
                    goal_activity[gid]['completed'] += 1
                if goal_activity[gid]['last_shown'] is None or p['priority_date'] > goal_activity[gid]['last_shown']:
                    goal_activity[gid]['last_shown'] = p['priority_date']

            # Score each goal - lower score = higher priority
            def goal_priority_score(goal):
                # Check for overdue milestones
                if goal.overdue_milestones:
                    return (-1, goal.sort_order)

                activity = goal_activity.get(goal.id, {'shown': 0, 'completed': 0, 'last_shown': None})
                shown = activity['shown']
                completed = activity['completed']

                if shown == 0:
                    return (0, goal.sort_order)
                elif completed == 0:
                    return (1, goal.sort_order)
                elif completed < shown:
                    return (2, goal.sort_order)
                else:
                    return (3, goal.sort_order)

            # Sort goals by priority score
            sorted_goals = sorted(all_goals, key=goal_priority_score)

            # Track goals already mentioned in overdue priorities
            overdue_goal_ids = {p.get('linked_goal_id') for p in priorities}

            # Take top 3 goals based on need (excluding those with overdue milestones already shown)
            for goal in sorted_goals[:5]:
                if len(priorities) >= 4:  # Leave room for intentions
                    break
                if goal.id in overdue_goal_ids:
                    continue

                # Build priority with milestone context
                next_milestone = goal.next_milestone
                if next_milestone:
                    title = f'{goal.title[:30]}: {next_milestone.title[:30]}'
                    description = f'{goal.completed_milestone_count}/{goal.milestone_count} milestones done'
                    if next_milestone.target_date:
                        days_until = (next_milestone.target_date - today).days
                        if days_until == 0:
                            description += ' - milestone due today!'
                        elif days_until == 1:
                            description += ' - milestone due tomorrow'
                        elif 0 < days_until <= 7:
                            description += f' - milestone due in {days_until} days'
                else:
                    title = f'Progress on: {goal.title[:50]}'
                    description = goal.description[:200] if goal.description else ''

                priorities.append({
                    'priority_type': 'purpose',
                    'title': title,
                    'description': description,
                    'why_important': goal.why_it_matters[:200] if goal.why_it_matters else 'This is one of your stated life goals.',
                    'linked_goal_id': goal.id,
                })

        # If few goals, add intention-based priority
        if len(priorities) < 2:
            intentions = ChangeIntention.objects.filter(
                user=self.user,
                status='active'
            )[:2]

            for intention in intentions:
                priorities.append({
                    'priority_type': 'personal',
                    'title': f'Embody: {intention.intention[:50]}',
                    'description': intention.description[:200] if intention.description else '',
                    'why_important': intention.motivation[:200] if intention.motivation else 'This is a change you said you want to make.',
                    'linked_intention_id': intention.id,
                })

        return priorities

    def _generate_commitment_priorities(self, state: Dict) -> List[Dict]:
        """Generate priorities for existing commitments (tasks).

        Uses priority-based grouping matching the Organize page.
        """
        from apps.life.models import Task
        from apps.core.utils import get_user_today
        from apps.life.services.task_queries import refresh_stale_priorities

        today = get_user_today(self.user)
        refresh_stale_priorities(self.user)
        priorities = []

        # "Now" bucket tasks, overdue first (due_date < today)
        now_tasks = Task.objects.filter(
            user=self.user,
            completion_status='pending',
            priority='now',
        ).order_by('due_date')[:4]

        for task in now_tasks:
            if len(priorities) >= 2:
                break
            is_overdue = task.due_date and task.due_date < today
            priorities.append({
                'priority_type': 'commitment',
                'title': f'{"Overdue: " if is_overdue else ""}{task.title[:50]}',
                'description': (
                    f'Due {task.due_date.strftime("%b %d")}' if task.due_date
                    else 'No due date'
                ),
                'why_important': (
                    'Completing overdue commitments reduces stress and builds trust with yourself.'
                    if is_overdue else
                    'Meeting your commitments on time builds momentum.'
                ),
                'linked_task_id': task.id,
            })

        return priorities

    # =========================================================================
    # REFLECTION PROMPTS
    # =========================================================================

    def generate_reflection_prompt(self, context: str = 'general') -> Optional[str]:
        """
        Generate a personalized reflection prompt based on user's current state.

        Args:
            context: Type of prompt ('morning', 'evening', 'weekly', 'goal_related', etc.)
        """
        state = self.assess_current_state()

        # Check for existing unused prompt
        existing = ReflectionPromptQueue.objects.filter(
            user=self.user,
            prompt_context=context,
            is_used=False,
            is_shown=False
        ).first()

        if existing:
            existing.mark_shown()
            return existing.prompt_text

        # Generate new prompt
        prompt = self._generate_prompt_for_context(context, state)

        if prompt:
            # Save to queue
            ReflectionPromptQueue.objects.create(
                user=self.user,
                prompt_text=prompt['text'],
                prompt_context=context,
                relevance_reason=prompt.get('reason', ''),
                linked_goal_id=prompt.get('linked_goal_id'),
                linked_intention_id=prompt.get('linked_intention_id'),
            )

        return prompt['text'] if prompt else None

    def _generate_prompt_for_context(self, context: str, state: Dict) -> Optional[Dict]:
        """Generate a prompt appropriate for the given context."""
        prompts = {
            'morning': self._morning_prompts(state),
            'evening': self._evening_prompts(state),
            'weekly': self._weekly_prompts(state),
            'goal_related': self._goal_prompts(state),
            'intention_check': self._intention_prompts(state),
            'gratitude': self._gratitude_prompts(state),
            'faith': self._faith_prompts(state),
            'general': self._general_prompts(state),
        }

        prompt_list = prompts.get(context, prompts['general'])

        if prompt_list:
            import random
            return random.choice(prompt_list)

        return None

    def _morning_prompts(self, state: Dict) -> List[Dict]:
        """Morning reflection prompts."""
        prompts = [
            {'text': 'What would make today meaningful? Not busy—meaningful.'},
            {'text': 'What is the one thing you must accomplish today that aligns with who you want to become?'},
            {'text': 'How do you want to feel at the end of today? What will help you get there?'},
        ]

        # Add goal-connected prompt if they have goals
        goals = state.get('goals', {})
        if goals.get('active', 0) > 0:
            prompts.append({
                'text': 'Which of your life goals can you move forward today, even slightly?',
                'reason': 'Connected to active goals'
            })

        return prompts

    def _evening_prompts(self, state: Dict) -> List[Dict]:
        """Evening reflection prompts."""
        prompts = [
            {'text': 'What happened today that you want to remember? What can you release?'},
            {'text': 'Where did you show up as the person you want to be today?'},
            {'text': 'What did you learn about yourself today?'},
        ]

        tasks = state.get('tasks', {})
        if tasks.get('completed_today', 0) > 0:
            prompts.append({
                'text': f"You completed {tasks['completed_today']} tasks today. What feels most significant about what you accomplished?",
                'reason': 'Based on today\'s productivity'
            })

        return prompts

    def _weekly_prompts(self, state: Dict) -> List[Dict]:
        """Weekly review prompts."""
        return [
            {'text': 'Looking at your week: where did your time actually go versus where you intended it to go?'},
            {'text': 'What patterns do you notice in how you spent your energy this week?'},
            {'text': 'What do you want to carry forward into next week? What do you want to leave behind?'},
        ]

    def _goal_prompts(self, state: Dict) -> List[Dict]:
        """Goal-related prompts."""
        from apps.purpose.models import LifeGoal

        prompts = []
        goals = LifeGoal.objects.filter(user=self.user, status='active')[:3]

        for goal in goals:
            prompts.append({
                'text': f'Thinking about your goal "{goal.title}": What small step could you take today that your future self would thank you for?',
                'reason': f'Connected to goal: {goal.title}',
                'linked_goal_id': goal.id,
            })

        if not prompts:
            prompts.append({
                'text': 'What is one thing you\'ve been wanting to accomplish but haven\'t started? What\'s really holding you back?',
            })

        return prompts

    def _intention_prompts(self, state: Dict) -> List[Dict]:
        """Intention-check prompts."""
        from apps.purpose.models import ChangeIntention

        prompts = []
        intentions = ChangeIntention.objects.filter(user=self.user, status='active')[:3]

        for intention in intentions:
            prompts.append({
                'text': f'You said you want to "{intention.intention}". When did you live that out recently? When was it hard?',
                'reason': f'Connected to intention: {intention.intention}',
                'linked_intention_id': intention.id,
            })

        if not prompts:
            prompts.append({
                'text': 'Who do you want to become? What is one small way you could step into that identity today?',
            })

        return prompts

    def _gratitude_prompts(self, state: Dict) -> List[Dict]:
        """Gratitude prompts."""
        return [
            {'text': 'What are three things from today that you\'re genuinely grateful for? Look for the small ones.'},
            {'text': 'Who in your life are you grateful for right now? What specifically about them?'},
            {'text': 'What challenge this week are you grateful for in hindsight?'},
        ]

    def _faith_prompts(self, state: Dict) -> List[Dict]:
        """Faith-related prompts (only if faith enabled)."""
        if not self.faith_enabled:
            return []

        prompts = [
            {'text': 'Where did you see God at work in your life this week?'},
            {'text': 'What is God teaching you in this season? What might He be inviting you into?'},
            {'text': 'Is there anything you need to surrender to God today? What would it look like to let go?'},
        ]

        prayers = state.get('faith', {}).get('active_prayers', 0)
        if prayers > 0:
            prompts.append({
                'text': f'You have {prayers} active prayer requests. How has your perspective on any of them shifted recently?',
                'reason': 'Connected to prayer life'
            })

        return prompts

    def _general_prompts(self, state: Dict) -> List[Dict]:
        """General reflection prompts."""
        return [
            {'text': 'What\'s on your mind right now that you haven\'t given yourself space to process?'},
            {'text': 'If you could tell yourself one thing this morning, what would it be?'},
            {'text': 'What are you avoiding? What would happen if you faced it?'},
        ]
