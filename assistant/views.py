"""
Assistant Views for WLJ Personal Data Query System.

This module provides the main entry point for processing assistant messages,
integrating intent detection, date parsing, data querying, and context building.

It also integrates gap detection to automatically create improvement tasks
when the assistant encounters knowledge gaps.
"""

import logging
from typing import Any, Dict, Optional

from django.conf import settings

from .context_builder import build_personal_context
from .data_service import PersonalDataService
from .date_parser import extract_date_from_message
from .gap_detector import detect_knowledge_gap, categorize_gap_severity, GapSeverity
from .intent_detector import detect_personal_data_intent
from .task_generator import generate_improvement_task

# Lazy imports to avoid circular import during Django app loading
# These are imported inside functions that use them:
# - AutonomousExecutor from .executor
# - ImprovementTaskModel from .models
# - AdminNotificationService, TaskInfo from .notifications


# Configure logging
logger = logging.getLogger(__name__)


# User-facing message when a gap is detected
GAP_DETECTED_MESSAGE = (
    "I do not have that information yet, but I have noted this for improvement."
)

# User-facing message when no data is found but user might have logged it
DATA_NOT_FOUND_CLARIFYING_MESSAGE = (
    "I'm not seeing any {data_type} data in my records. "
    "Can you see your most recent {data_type} entries in the app? "
    "If you can see them there but I can't, please let me know and I'll investigate."
)

# User-facing message when user confirms data exists but assistant can't see it
DATA_VISIBILITY_ISSUE_MESSAGE = (
    "Thank you for confirming. I've notified the admin about this data visibility issue. "
    "They will investigate why I can't see your {data_type} data. "
    "In the meantime, you can view your data directly in the Health section of the app."
)


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

    When a knowledge gap is detected (query cannot be answered), this function
    automatically creates an improvement task and routes it appropriately:
    - LOW severity: Queued for autonomous execution
    - MEDIUM/HIGH severity: Sent to admin for approval

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
            - gap_detected (bool): Whether a knowledge gap was detected.
            - gap_message (str or None): User-facing message about the gap.

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
        'gap_detected': False,
        'gap_message': None,
        'needs_clarification': False,  # True when asking user to verify data exists
        'clarifying_question': None,   # The question to ask the user
        'awaiting_data_type': None,    # Which data type we're asking about
    }

    # Step 1: Detect if this is a personal data query
    intent = detect_personal_data_intent(message)

    result['is_personal_query'] = intent['is_personal_query']
    result['data_types'] = intent['data_types']

    # Check for ambiguous keywords that need clarification FIRST
    if intent.get('has_ambiguous_keyword'):
        from .intent_detector import get_clarifying_question

        ambiguous_keyword = intent.get('ambiguous_keyword')
        ambiguous_info = intent.get('ambiguous_info', {})

        # Get user's preferred coaching style
        coaching_style = 'supportive'  # default
        if user and hasattr(user, 'preferences'):
            coaching_style = getattr(user.preferences, 'ai_coaching_style', 'supportive')

        result['needs_clarification'] = True
        result['clarifying_question'] = get_clarifying_question(ambiguous_keyword, coaching_style)
        result['awaiting_data_type'] = 'ambiguous'
        result['ambiguous_keyword'] = ambiguous_keyword
        result['possible_data_types'] = ambiguous_info.get('possible_types', [])

        logger.info(
            f"Ambiguous keyword '{ambiguous_keyword}' detected (style: {coaching_style}), "
            f"asking for clarification: '{message[:50]}...'"
        )
        return result

    # If not a personal query, check for gap and return
    if not intent['is_personal_query']:
        # Check if this might still be a gap (user asked about something personal)
        gap_result = detect_knowledge_gap(message, intent, None)
        if gap_result['gap_detected']:
            _handle_gap_detection(message, intent, None, gap_result, result, user)
        return result

    # Step 2: Extract date from message if there's date context
    since_date = None
    if intent['has_date_context']:
        since_date = extract_date_from_message(message)

    # Step 3: Query personal data based on detected intent
    # Filter data_types to only those we have query methods for
    supported_types = ['weight', 'journal', 'medication', 'food', 'mood', 'glucose', 'faith', 'goals']
    queryable_types = [dt for dt in intent['data_types'] if dt in supported_types]

    if not queryable_types:
        # No queryable data types detected - this is a potential gap
        gap_result = detect_knowledge_gap(message, intent, None)
        if gap_result['gap_detected']:
            _handle_gap_detection(message, intent, None, gap_result, result, user)
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
    else:
        # Data query returned empty - this could be:
        # 1. User hasn't logged any data (normal case)
        # 2. Data exists but we can't see it (bug/cache issue)
        #
        # Instead of treating as a gap, ask user to clarify
        primary_data_type = queryable_types[0] if queryable_types else 'data'
        friendly_name = _get_friendly_data_type_name(primary_data_type)

        result['needs_clarification'] = True
        result['clarifying_question'] = DATA_NOT_FOUND_CLARIFYING_MESSAGE.format(
            data_type=friendly_name
        )
        result['awaiting_data_type'] = primary_data_type

        logger.info(
            f"No data found for {primary_data_type} query, asking user to verify: "
            f"'{message[:50]}...'"
        )

    return result


def _get_friendly_data_type_name(data_type: str) -> str:
    """Convert internal data type name to user-friendly display name."""
    friendly_names = {
        'glucose': 'blood glucose',
        'weight': 'weight',
        'journal': 'journal',
        'medication': 'medication',
        'food': 'food',
        'mood': 'mood',
        'faith': 'faith',
        'goals': 'goals',
    }
    return friendly_names.get(data_type, data_type)


def _handle_gap_detection(
    message: str,
    intent: Dict[str, Any],
    data_results: Optional[Dict[str, Any]],
    gap_result: Dict[str, Any],
    result: Dict[str, Any],
    user=None,
) -> None:
    """
    Handle a detected knowledge gap by creating an improvement task.

    This function:
    1. Logs the gap detection
    2. Generates an improvement task
    3. Saves the task to the database
    4. Routes based on severity:
       - LOW: Queue for AutonomousExecutor (if safe)
       - MEDIUM/HIGH: Send approval notification to admin
    5. Updates the result dict with gap info

    Args:
        message: The original user message.
        intent: The intent detection result.
        data_results: The data query results (or None).
        gap_result: The gap detection result.
        result: The result dict to update with gap info.
        user: The Django User who triggered the gap (for tracking).
    """
    # Lazy import to avoid circular import during Django app loading
    from .models import ImprovementTaskModel

    logger.info(
        f"Gap detected: type={gap_result['gap_type']}, "
        f"category={gap_result['suggested_category']}, "
        f"query='{message[:50]}...'"
    )

    # Update result with gap info
    result['gap_detected'] = True
    result['gap_message'] = GAP_DETECTED_MESSAGE

    # Generate improvement task
    improvement_task = generate_improvement_task(gap_result)
    if not improvement_task:
        logger.warning(f"Failed to generate improvement task for gap: {gap_result}")
        return

    # Save to database
    try:
        task_model = ImprovementTaskModel.create_from_improvement_task(improvement_task)
        # Set the user who triggered this gap
        if user:
            task_model.triggered_by_user = user
        task_model.save()
        logger.info(f"Created improvement task {task_model.id}: {task_model.title}")
    except Exception as e:
        logger.error(f"Failed to save improvement task: {e}")
        return

    # Route based on severity
    severity = categorize_gap_severity(gap_result['gap_type'])

    if severity == GapSeverity.LOW:
        # Check if safe for autonomous execution
        _queue_for_autonomous_execution(task_model)
    else:
        # Send approval notification to admin
        _send_approval_notification(task_model, severity)


def _queue_for_autonomous_execution(task_model) -> None:
    """
    Queue a LOW severity task for autonomous execution if safe.

    Args:
        task_model: The ImprovementTaskModel to execute.
    """
    # Lazy import to avoid circular import during Django app loading
    from .executor import AutonomousExecutor

    try:
        executor = AutonomousExecutor()
        is_safe, reason = executor.is_safe_for_autonomous(task_model)

        if is_safe:
            logger.info(f"Task {task_model.id} queued for autonomous execution")
            # Note: Actual execution will be handled by background task queue (Task #171)
            # For now, just mark as ready for autonomous execution
            task_model.requires_approval = False
            task_model.save(update_fields=['requires_approval'])
        else:
            logger.info(
                f"Task {task_model.id} not safe for autonomous execution: {reason}. "
                f"Sending to admin for approval."
            )
            _send_approval_notification(task_model, GapSeverity.LOW)
    except Exception as e:
        logger.error(f"Error checking autonomous execution safety: {e}")
        _send_approval_notification(task_model, GapSeverity.LOW)


def _send_approval_notification(
    task_model,
    severity: GapSeverity,
) -> None:
    """
    Send approval notification to admin for MEDIUM/HIGH severity tasks.

    Args:
        task_model: The ImprovementTaskModel requiring approval.
        severity: The severity level of the task.
    """
    # Lazy import to avoid circular import during Django app loading
    from .notifications import AdminNotificationService, TaskInfo

    try:
        notification_service = AdminNotificationService()

        # Get user info if available
        triggered_by_email = None
        triggered_by_name = None
        if task_model.triggered_by_user:
            triggered_by_email = task_model.triggered_by_user.email
            triggered_by_name = (
                task_model.triggered_by_user.get_full_name()
                or task_model.triggered_by_user.email
            )

        task_info = TaskInfo(
            task_id=str(task_model.id),
            title=task_model.title,
            description=task_model.suggested_fix,
            severity=severity.value,
            triggered_by_email=triggered_by_email,
            triggered_by_name=triggered_by_name,
            original_query=task_model.original_query,
        )

        # Generate approval token and create URL
        approval_token = task_model.generate_approval_token()
        site_domain = getattr(settings, 'SITE_DOMAIN', 'https://wholelifejourney.com')
        approval_url = f"{site_domain}/assistant/admin/approve/{task_model.id}/{approval_token}/"

        notification_service.notify_approval_required(
            task=task_info,
            approval_url=approval_url,
            changes_preview=task_model.code_template,
        )

        logger.info(
            f"Approval notification sent for task {task_model.id} "
            f"(severity: {severity.value})"
        )
    except Exception as e:
        logger.error(f"Failed to send approval notification: {e}")


def handle_data_visibility_confirmation(
    user,
    data_type: str,
    user_confirms_data_exists: bool,
) -> Dict[str, Any]:
    """
    Handle user's response to the clarifying question about data visibility.

    When the assistant can't find data and asks the user to verify if they can
    see it in the app, this function processes their response.

    Args:
        user: The Django User object.
        data_type: The type of data (e.g., 'glucose', 'weight').
        user_confirms_data_exists: True if user says they CAN see their data in the app.

    Returns:
        A dictionary containing:
            - response_message (str): Message to show the user.
            - action_taken (str): What action was taken ('none', 'notified_admin', 'invalidated_cache').
            - issue_resolved (bool): Whether the issue was resolved automatically.
    """
    friendly_name = _get_friendly_data_type_name(data_type)

    if not user_confirms_data_exists:
        # User doesn't have data - this is expected, no action needed
        return {
            'response_message': (
                f"No problem! When you're ready to log some {friendly_name} data, "
                f"you can do so in the Health section of the app, and I'll be able to "
                f"see it and help you track your progress."
            ),
            'action_taken': 'none',
            'issue_resolved': True,
        }

    # User confirms data exists but assistant can't see it - this is a bug!
    logger.warning(
        f"DATA VISIBILITY ISSUE: User {user.id} confirms {data_type} data exists "
        f"but assistant cannot see it. Triggering diagnostics and admin notification."
    )

    # Step 1: Try to invalidate cache (this might fix it immediately)
    from .data_service import invalidate_user_data_cache
    invalidate_user_data_cache(user.id, data_type)
    logger.info(f"Invalidated cache for user {user.id}, data_type={data_type}")

    # Step 2: Check if data is now visible after cache invalidation
    from .data_service import PersonalDataService
    service = PersonalDataService(user)

    # Try to fetch the data again
    data_method = getattr(service, f'get_{data_type}_data', None)
    data_now_visible = False
    if data_method:
        try:
            data = data_method()
            if data:
                data_now_visible = True
                logger.info(f"Cache invalidation fixed visibility for user {user.id}, {data_type}")
        except Exception as e:
            logger.error(f"Error checking data visibility after cache invalidation: {e}")

    if data_now_visible:
        # Cache invalidation fixed the issue
        return {
            'response_message': (
                f"I found the issue and fixed it! I can now see your {friendly_name} data. "
                f"Please ask me again about your {friendly_name} and I'll be able to help."
            ),
            'action_taken': 'invalidated_cache',
            'issue_resolved': True,
        }

    # Step 3: Cache invalidation didn't help - notify admin
    _send_data_visibility_alert(user, data_type)

    return {
        'response_message': DATA_VISIBILITY_ISSUE_MESSAGE.format(data_type=friendly_name),
        'action_taken': 'notified_admin',
        'issue_resolved': False,
    }


def _send_data_visibility_alert(user, data_type: str) -> None:
    """
    Send an alert to the admin about a data visibility issue.

    This is called when the user confirms they can see data in the app
    but the assistant cannot retrieve it, even after cache invalidation.

    Args:
        user: The Django User object.
        data_type: The type of data that cannot be seen.
    """
    from django.core.mail import send_mail
    from django.conf import settings

    admin_email = getattr(settings, 'ADMIN_EMAIL', 'admin@wholelifejourney.com')
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@wholelifejourney.com')

    subject = f"[WLJ Assistant] DATA VISIBILITY ISSUE: {data_type} for user {user.email}"

    message = f"""
DATA VISIBILITY ISSUE DETECTED

The AI Assistant could not retrieve {data_type} data for a user, but the user
confirmed they can see the data in the app. Cache invalidation was attempted
but did not resolve the issue.

User Details:
- Email: {user.email}
- User ID: {user.id}
- Data Type: {data_type}

Diagnostic Steps to Take:
1. Check if the user has {data_type} entries in the database
2. Verify the data_service query method is working correctly
3. Check for any timezone issues in date filtering
4. Review recent deployments for related changes
5. Check the assistant logs for errors

This requires manual investigation.

---
This alert was automatically generated by the WLJ Personal Assistant
when a user reported a data visibility discrepancy.
"""

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[admin_email],
            fail_silently=False,
        )
        logger.info(f"Data visibility alert sent to {admin_email} for user {user.id}, {data_type}")
    except Exception as e:
        logger.error(f"Failed to send data visibility alert: {e}")
