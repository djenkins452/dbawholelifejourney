"""
Assistant Views for WLJ Personal Data Query System.

This module provides the main entry point for processing assistant messages,
integrating intent detection, date parsing, data querying, and context building.

It also integrates gap detection to automatically create improvement tasks
when the assistant encounters knowledge gaps.
"""

import logging
from typing import Any, Dict, Optional

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
    }

    # Step 1: Detect if this is a personal data query
    intent = detect_personal_data_intent(message)

    result['is_personal_query'] = intent['is_personal_query']
    result['data_types'] = intent['data_types']

    # If not a personal query, check for gap and return
    if not intent['is_personal_query']:
        # Check if this might still be a gap (user asked about something personal)
        gap_result = detect_knowledge_gap(message, intent, None)
        if gap_result['gap_detected']:
            _handle_gap_detection(message, intent, None, gap_result, result)
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
            _handle_gap_detection(message, intent, None, gap_result, result)
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
        # Data query returned empty - check for knowledge gap
        gap_result = detect_knowledge_gap(message, intent, data_results)
        if gap_result['gap_detected']:
            _handle_gap_detection(message, intent, data_results, gap_result, result)

    return result


def _handle_gap_detection(
    message: str,
    intent: Dict[str, Any],
    data_results: Optional[Dict[str, Any]],
    gap_result: Dict[str, Any],
    result: Dict[str, Any],
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

        task_info = TaskInfo(
            task_id=str(task_model.id),
            title=task_model.title,
            description=task_model.suggested_fix,
            severity=severity.value,
        )

        # Generate approval URL (will be implemented in admin views)
        approval_url = f"/assistant/admin/tasks/{task_model.id}/"

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
