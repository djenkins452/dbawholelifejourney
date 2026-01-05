"""
Assistant Views for WLJ Personal Data Query System.

This module provides the main entry point for processing assistant messages,
integrating intent detection, date parsing, data querying, and context building.
"""

from typing import Any, Dict, Optional

from .context_builder import build_personal_context
from .data_service import PersonalDataService
from .date_parser import extract_date_from_message
from .intent_detector import detect_personal_data_intent


def process_assistant_message(
    user,
    message: str,
    base_system_prompt: str = "",
) -> Dict[str, Any]:
    """
    Process a user message and prepare context for AI response.

    This is the main entry point for the personal data query system.
    It analyzes the user's message, queries relevant personal data,
    and builds an enhanced system prompt with personal context.

    Args:
        user: The Django User object whose data may be queried.
        message: The user's message string to process.
        base_system_prompt: Optional base system prompt to enhance.
                           Personal context will be appended if relevant.

    Returns:
        A dictionary containing:
            - system_prompt (str): The final system prompt, possibly enhanced
              with personal data context.
            - is_personal_query (bool): Whether the message was identified as
              a personal data query.
            - data_types (list): List of detected data types.
            - has_data (bool): Whether any personal data was found.

    Example:
        >>> result = process_assistant_message(
        ...     user=request.user,
        ...     message="What was my average weight last week?",
        ...     base_system_prompt="You are a helpful assistant."
        ... )
        >>> print(result['system_prompt'])
        You are a helpful assistant.

        Here is the user's personal data:

        Weight Data:
        - Total entries: 15
        ...

        >>> print(result['is_personal_query'])
        True
    """
    # Initialize result
    result = {
        'system_prompt': base_system_prompt,
        'is_personal_query': False,
        'data_types': [],
        'has_data': False,
    }

    # Step 1: Detect if this is a personal data query
    intent = detect_personal_data_intent(message)

    result['is_personal_query'] = intent['is_personal_query']
    result['data_types'] = intent['data_types']

    # If not a personal query, return early with base prompt
    if not intent['is_personal_query']:
        return result

    # Step 2: Extract date from message if there's date context
    since_date = None
    if intent['has_date_context']:
        since_date = extract_date_from_message(message)

    # Step 3: Query personal data based on detected intent
    # Filter data_types to only those we have query methods for
    supported_types = ['weight', 'journal', 'medication', 'food', 'mood']
    queryable_types = [dt for dt in intent['data_types'] if dt in supported_types]

    if not queryable_types:
        # No queryable data types detected
        return result

    # Create service and query data
    service = PersonalDataService(user)
    data_results = service.query_by_intent(
        data_types=queryable_types,
        since_date=since_date,
    )

    # Step 4: Build personal context if data exists
    if data_results:
        result['has_data'] = True
        personal_context = build_personal_context(data_results)

        # Append personal context to system prompt
        if personal_context:
            if base_system_prompt:
                result['system_prompt'] = base_system_prompt + '\n\n' + personal_context
            else:
                result['system_prompt'] = personal_context

    return result
