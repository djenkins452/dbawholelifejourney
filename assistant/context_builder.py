"""
Context Builder for WLJ Personal Data Query System.

This module converts query results from PersonalDataService into
natural language context suitable for AI prompts.
"""

from datetime import date, datetime
from typing import Any, Dict, Optional


def build_personal_context(data_results: Optional[Dict[str, Any]]) -> str:
    """
    Convert query results into natural language context for AI prompts.

    Takes the output from PersonalDataService.query_by_intent() and formats
    it into a human-readable string that can be injected into AI prompts.

    Args:
        data_results: Dict from PersonalDataService.query_by_intent() containing
                     data type keys mapped to their query results.
                     Can be None or empty dict.

    Returns:
        Empty string if data_results is None or empty.
        Otherwise, a formatted string with natural language summaries
        of the user's data, ready for AI context injection.

    Example:
        >>> results = {
        ...     'weight': {'type': 'weight', 'count': 15, 'average': 175.5, ...},
        ...     'journal': {'type': 'journal', 'count': 10, ...}
        ... }
        >>> context = build_personal_context(results)
        >>> print(context)
        Here is the user's personal data:

        Weight Data:
        - Total entries: 15
        - Average: 175.5 lb
        - Most recent: 174.0 lb on 2024-12-18
        ...
    """
    # Return empty string if no data
    if not data_results:
        return ''

    sections = []

    # Format weight data if present
    if 'weight' in data_results:
        weight_section = _format_weight_data(data_results['weight'])
        if weight_section:
            sections.append(weight_section)

    # Format journal data if present
    if 'journal' in data_results:
        journal_section = _format_journal_data(data_results['journal'])
        if journal_section:
            sections.append(journal_section)

    # Format medication data if present
    if 'medication' in data_results:
        medication_section = _format_medication_data(data_results['medication'])
        if medication_section:
            sections.append(medication_section)

    # Format food data if present
    if 'food' in data_results:
        food_section = _format_food_data(data_results['food'])
        if food_section:
            sections.append(food_section)

    # Format mood data if present
    if 'mood' in data_results:
        mood_section = _format_mood_data(data_results['mood'])
        if mood_section:
            sections.append(mood_section)

    # Format glucose data if present
    if 'glucose' in data_results:
        glucose_section = _format_glucose_data(data_results['glucose'])
        if glucose_section:
            sections.append(glucose_section)

    # Format faith data if present
    if 'faith' in data_results:
        faith_section = _format_faith_data(data_results['faith'])
        if faith_section:
            sections.append(faith_section)

    # Format goals data if present
    if 'goals' in data_results:
        goals_section = _format_goals_data(data_results['goals'])
        if goals_section:
            sections.append(goals_section)

    # Format heart rate data if present
    if 'heart_rate' in data_results:
        heart_rate_section = _format_heart_rate_data(data_results['heart_rate'])
        if heart_rate_section:
            sections.append(heart_rate_section)

    # Format blood pressure data if present
    if 'blood_pressure' in data_results:
        bp_section = _format_blood_pressure_data(data_results['blood_pressure'])
        if bp_section:
            sections.append(bp_section)

    # Format blood oxygen data if present
    if 'blood_oxygen' in data_results:
        oxygen_section = _format_blood_oxygen_data(data_results['blood_oxygen'])
        if oxygen_section:
            sections.append(oxygen_section)

    # Format workout data if present
    if 'workout' in data_results:
        workout_section = _format_workout_data(data_results['workout'])
        if workout_section:
            sections.append(workout_section)

    # Format fasting data if present
    if 'fasting' in data_results:
        fasting_section = _format_fasting_data(data_results['fasting'])
        if fasting_section:
            sections.append(fasting_section)

    # Format task data if present
    if 'task' in data_results:
        task_section = _format_task_data(data_results['task'])
        if task_section:
            sections.append(task_section)

    # Format user data if present
    if 'user' in data_results:
        user_section = _format_user_data(data_results['user'])
        if user_section:
            sections.append(user_section)

    # Return empty string if no sections were formatted
    if not sections:
        return ''

    # Build the full context
    header = "Here is the user's personal data:\n"
    body = '\n\n'.join(sections)
    footer = "\n\nPlease use this data to provide personalized, helpful responses."

    return header + '\n' + body + footer


def _format_weight_data(weight_data: Dict[str, Any]) -> str:
    """Format weight data into natural language."""
    if not weight_data:
        return ''

    lines = ['Weight Data:']

    # Total entries
    count = weight_data.get('count', 0)
    lines.append(f'- Total entries: {count}')

    # Average weight
    average = weight_data.get('average')
    unit = weight_data.get('unit', 'lb')
    if average is not None:
        lines.append(f'- Average: {average} {unit}')

    # Most recent entry
    latest = weight_data.get('latest')
    latest_date = weight_data.get('latest_date')
    if latest is not None and latest_date is not None:
        date_str = _format_date(latest_date)
        lines.append(f'- Most recent: {latest} {unit} on {date_str}')

    return '\n'.join(lines)


def _format_journal_data(journal_data: Dict[str, Any]) -> str:
    """Format journal data into natural language."""
    if not journal_data:
        return ''

    lines = ['Journal Data:']

    # Total entries
    count = journal_data.get('count', 0)
    lines.append(f'- Total entries: {count}')

    # Latest entry date
    latest_date = journal_data.get('latest_date')
    if latest_date is not None:
        date_str = _format_date(latest_date)
        lines.append(f'- Most recent entry: {date_str}')

    return '\n'.join(lines)


def _format_medication_data(medication_data: Dict[str, Any]) -> str:
    """Format medication data into natural language."""
    if not medication_data:
        return ''

    lines = ['Medication Data:']

    # Total logs
    total_logs = medication_data.get('total_logs', 0)
    lines.append(f'- Total medication logs: {total_logs}')

    # Days logged
    days_logged = medication_data.get('days_logged', 0)
    total_days = medication_data.get('total_days', 0)
    if days_logged and total_days:
        lines.append(f'- Days with logs: {days_logged} out of {total_days} days')

    # Consistency percentage
    consistency = medication_data.get('consistency_percent')
    if consistency is not None:
        lines.append(f'- Consistency: {consistency}%')

    return '\n'.join(lines)


def _format_food_data(food_data: Dict[str, Any]) -> str:
    """Format food data into natural language."""
    if not food_data:
        return ''

    lines = ['Food Data:']

    # Total entries
    total_entries = food_data.get('total_entries', 0)
    lines.append(f'- Total entries: {total_entries}')

    # Total calories
    total_calories = food_data.get('total_calories')
    if total_calories is not None:
        lines.append(f'- Total calories: {total_calories}')

    # Average daily calories
    avg_calories = food_data.get('average_daily_calories')
    if avg_calories is not None:
        lines.append(f'- Average daily calories: {avg_calories}')

    # Latest entry date
    latest_date = food_data.get('latest_date')
    if latest_date is not None:
        date_str = _format_date(latest_date)
        lines.append(f'- Most recent entry: {date_str}')

    return '\n'.join(lines)


def _format_mood_data(mood_data: Dict[str, Any]) -> str:
    """Format mood data into natural language."""
    if not mood_data:
        return ''

    lines = ['Mood Data:']

    # Count of mood entries
    count = mood_data.get('count', 0)
    lines.append(f'- Total mood entries: {count}')

    # Most common mood
    most_common = mood_data.get('most_common')
    if most_common:
        lines.append(f'- Most common mood: {most_common}')

    # Mood distribution
    distribution = mood_data.get('mood_distribution')
    if distribution:
        dist_parts = [f'{mood}: {cnt}' for mood, cnt in distribution.items()]
        lines.append(f'- Mood breakdown: {", ".join(dist_parts)}')

    # Latest mood
    latest_mood = mood_data.get('latest_mood')
    latest_date = mood_data.get('latest_date')
    if latest_mood and latest_date:
        date_str = _format_date(latest_date)
        lines.append(f'- Most recent: {latest_mood} on {date_str}')

    return '\n'.join(lines)


def _format_glucose_data(glucose_data: Dict[str, Any]) -> str:
    """Format glucose data into natural language."""
    if not glucose_data:
        return ''

    lines = ['Glucose Data:']

    # Total entries
    count = glucose_data.get('count', 0)
    lines.append(f'- Total entries: {count}')

    # Average glucose
    average = glucose_data.get('average')
    unit = glucose_data.get('unit', 'mg/dL')
    if average is not None:
        lines.append(f'- Average: {average} {unit}')

    # Most recent entry
    latest = glucose_data.get('latest')
    latest_date = glucose_data.get('latest_date')
    if latest is not None and latest_date is not None:
        date_str = _format_date(latest_date)
        lines.append(f'- Most recent: {latest} {unit} on {date_str}')

    return '\n'.join(lines)


def _format_goals_data(goals_data: Dict[str, Any]) -> str:
    """Format goals data into natural language."""
    if not goals_data:
        return ''

    lines = ['Goals Data:']

    # Total goals
    total = goals_data.get('total', 0)
    lines.append(f'- Total goals: {total}')

    # Status breakdown
    by_status = goals_data.get('by_status', {})
    if by_status:
        active = by_status.get('active', 0)
        paused = by_status.get('paused', 0)
        completed = by_status.get('completed', 0)
        released = by_status.get('released', 0)
        lines.append(f'- By status: {active} active, {paused} paused, {completed} completed, {released} released')

    # Completion rate
    completion_rate = goals_data.get('completion_rate')
    if completion_rate is not None:
        lines.append(f'- Completion rate: {completion_rate}%')

    # Timeframe breakdown
    by_timeframe = goals_data.get('by_timeframe', {})
    if by_timeframe:
        timeframe_parts = []
        if by_timeframe.get('year_1'):
            timeframe_parts.append(f"{by_timeframe['year_1']} within 1 year")
        if by_timeframe.get('year_2'):
            timeframe_parts.append(f"{by_timeframe['year_2']} in 1-2 years")
        if by_timeframe.get('year_3'):
            timeframe_parts.append(f"{by_timeframe['year_3']} in 2-3 years")
        if by_timeframe.get('ongoing'):
            timeframe_parts.append(f"{by_timeframe['ongoing']} ongoing")
        if timeframe_parts:
            lines.append(f'- Timeframes: {", ".join(timeframe_parts)}')

    # Domains
    domains = goals_data.get('domains', [])
    if domains:
        domain_parts = [f"{d['name']}: {d['count']}" for d in domains]
        lines.append(f'- Life domains: {", ".join(domain_parts)}')

    # Recent completions
    recent_completed = goals_data.get('recent_completed', [])
    if recent_completed:
        lines.append('- Recently completed:')
        for goal in recent_completed[:3]:  # Limit to 3 for brevity
            date_str = _format_date(goal['completed_date'])
            lines.append(f'  - {goal["title"]} ({date_str})')

    return '\n'.join(lines)


def _format_faith_data(faith_data: Dict[str, Any]) -> str:
    """Format faith data into natural language."""
    if not faith_data:
        return ''

    lines = ['Faith Data:']

    # Prayer requests
    prayer_data = faith_data.get('prayer_requests')
    if prayer_data:
        total = prayer_data.get('total', 0)
        active = prayer_data.get('active', 0)
        answered = prayer_data.get('answered', 0)
        lines.append(f'- Prayer requests: {total} total ({active} active, {answered} answered)')
        latest_date = prayer_data.get('latest_date')
        if latest_date:
            date_str = _format_date(latest_date)
            lines.append(f'- Most recent prayer: {date_str}')

    # Saved verses
    saved_verses = faith_data.get('saved_verses', 0)
    if saved_verses > 0:
        lines.append(f'- Saved Scripture verses: {saved_verses}')

    # Faith milestones
    milestones = faith_data.get('milestones', 0)
    if milestones > 0:
        lines.append(f'- Faith milestones: {milestones}')

    # Reading plans
    reading_plans = faith_data.get('reading_plans')
    if reading_plans:
        active = reading_plans.get('active', 0)
        completed = reading_plans.get('completed', 0)
        if active > 0 or completed > 0:
            lines.append(f'- Reading plans: {active} active, {completed} completed')

    return '\n'.join(lines)


def _format_heart_rate_data(heart_rate_data: Dict[str, Any]) -> str:
    """Format heart rate data into natural language."""
    if not heart_rate_data:
        return ''

    lines = ['Heart Rate Data:']

    count = heart_rate_data.get('count', 0)
    lines.append(f'- Total entries: {count}')

    average = heart_rate_data.get('average')
    if average is not None:
        lines.append(f'- Average: {average} bpm')

    latest = heart_rate_data.get('latest')
    latest_date = heart_rate_data.get('latest_date')
    context = heart_rate_data.get('context', '')
    if latest is not None and latest_date is not None:
        date_str = _format_date(latest_date)
        context_str = f' ({context})' if context else ''
        lines.append(f'- Most recent: {latest} bpm{context_str} on {date_str}')

    return '\n'.join(lines)


def _format_blood_pressure_data(bp_data: Dict[str, Any]) -> str:
    """Format blood pressure data into natural language."""
    if not bp_data:
        return ''

    lines = ['Blood Pressure Data:']

    count = bp_data.get('count', 0)
    lines.append(f'- Total entries: {count}')

    avg_sys = bp_data.get('avg_systolic')
    avg_dia = bp_data.get('avg_diastolic')
    if avg_sys is not None and avg_dia is not None:
        lines.append(f'- Average: {avg_sys}/{avg_dia} mmHg')

    latest_sys = bp_data.get('latest_systolic')
    latest_dia = bp_data.get('latest_diastolic')
    latest_date = bp_data.get('latest_date')
    if latest_sys is not None and latest_dia is not None and latest_date is not None:
        date_str = _format_date(latest_date)
        lines.append(f'- Most recent: {latest_sys}/{latest_dia} mmHg on {date_str}')

    return '\n'.join(lines)


def _format_blood_oxygen_data(oxygen_data: Dict[str, Any]) -> str:
    """Format blood oxygen (SpO2) data into natural language."""
    if not oxygen_data:
        return ''

    lines = ['Blood Oxygen Data:']

    count = oxygen_data.get('count', 0)
    lines.append(f'- Total entries: {count}')

    average = oxygen_data.get('average')
    if average is not None:
        lines.append(f'- Average SpO2: {average}%')

    latest = oxygen_data.get('latest')
    latest_date = oxygen_data.get('latest_date')
    if latest is not None and latest_date is not None:
        date_str = _format_date(latest_date)
        lines.append(f'- Most recent: {latest}% on {date_str}')

    return '\n'.join(lines)


def _format_workout_data(workout_data: Dict[str, Any]) -> str:
    """Format workout data into natural language."""
    if not workout_data:
        return ''

    lines = ['Workout Data:']

    count = workout_data.get('count', 0)
    lines.append(f'- Total workout sessions: {count}')

    total_minutes = workout_data.get('total_minutes', 0)
    if total_minutes > 0:
        hours = total_minutes // 60
        mins = total_minutes % 60
        if hours > 0:
            lines.append(f'- Total workout time: {hours}h {mins}m')
        else:
            lines.append(f'- Total workout time: {mins} minutes')

    avg_duration = workout_data.get('avg_duration')
    if avg_duration is not None:
        lines.append(f'- Average session: {avg_duration} minutes')

    latest_date = workout_data.get('latest_date')
    if latest_date is not None:
        date_str = _format_date(latest_date)
        lines.append(f'- Most recent workout: {date_str}')

    return '\n'.join(lines)


def _format_fasting_data(fasting_data: Dict[str, Any]) -> str:
    """Format fasting data into natural language."""
    if not fasting_data:
        return ''

    lines = ['Fasting Data:']

    # Active fast
    active_fast = fasting_data.get('active_fast')
    if active_fast:
        hours = active_fast.get('hours_elapsed', 0)
        fast_type = active_fast.get('fasting_type', '')
        type_str = f' ({fast_type})' if fast_type else ''
        lines.append(f'- CURRENTLY FASTING: {hours} hours elapsed{type_str}')

    total_fasts = fasting_data.get('total_fasts', 0)
    lines.append(f'- Completed fasts: {total_fasts}')

    avg_duration = fasting_data.get('avg_duration_hours')
    if avg_duration is not None and avg_duration > 0:
        lines.append(f'- Average fast duration: {avg_duration} hours')

    longest = fasting_data.get('longest_fast_hours')
    if longest is not None and longest > 0:
        lines.append(f'- Longest fast: {longest} hours')

    return '\n'.join(lines)


def _format_task_data(task_data: Dict[str, Any]) -> str:
    """Format task data into natural language."""
    if not task_data:
        return ''

    lines = ['Task Data:']

    total = task_data.get('total', 0)
    completed = task_data.get('completed', 0)
    pending = task_data.get('pending', 0)
    lines.append(f'- Total tasks: {total} ({completed} completed, {pending} pending)')

    overdue = task_data.get('overdue', 0)
    if overdue > 0:
        lines.append(f'- Overdue tasks: {overdue}')

    due_today = task_data.get('due_today', 0)
    if due_today > 0:
        lines.append(f'- Due today: {due_today}')

    completion_rate = task_data.get('completion_rate')
    if completion_rate is not None:
        lines.append(f'- Completion rate: {completion_rate}%')

    return '\n'.join(lines)


def _format_user_data(user_data: Dict[str, Any]) -> str:
    """Format user profile data into natural language."""
    if not user_data:
        return ''

    lines = ['User Profile:']

    name = user_data.get('name')
    if name:
        lines.append(f'- Name: {name}')

    first_name = user_data.get('first_name')
    if first_name:
        lines.append(f'- Preferred name: {first_name}')

    city = user_data.get('location_city')
    country = user_data.get('location_country')
    if city or country:
        location_parts = [p for p in [city, country] if p]
        lines.append(f'- Location: {", ".join(location_parts)}')

    timezone = user_data.get('timezone')
    if timezone and timezone != 'UTC':
        lines.append(f'- Timezone: {timezone}')

    return '\n'.join(lines)


def _format_date(dt: Any) -> str:
    """Format a date or datetime object to YYYY-MM-DD string."""
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d')
    elif isinstance(dt, date):
        return dt.strftime('%Y-%m-%d')
    else:
        return str(dt)
