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


def _format_date(dt: Any) -> str:
    """Format a date or datetime object to YYYY-MM-DD string."""
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d')
    elif isinstance(dt, date):
        return dt.strftime('%Y-%m-%d')
    else:
        return str(dt)
