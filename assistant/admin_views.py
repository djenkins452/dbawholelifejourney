"""
Admin views for approving and rejecting improvement tasks.

This module provides secure endpoints for admin approval of improvement
tasks via email links with one-time tokens, plus a dashboard for managing tasks
and analytics.
"""

from collections import Counter
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Avg, Count, F
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import ImprovementTaskModel


def approve_task(request, task_id, token):
    """
    Approve an improvement task via token-authenticated link.

    Args:
        request: The HTTP request.
        task_id: UUID of the task to approve.
        token: One-time approval token.

    Returns:
        HTML response confirming approval or error.
    """
    task = get_object_or_404(ImprovementTaskModel, id=task_id)

    # Validate token
    if not task.is_token_valid(token):
        return render(
            request,
            'assistant/admin/approval_error.html',
            {
                'task': task,
                'error': 'Invalid or expired approval token.',
                'error_type': 'token_invalid',
            },
            status=400
        )

    # Validate task status
    if task.status != ImprovementTaskModel.STATUS_PENDING_APPROVAL:
        return render(
            request,
            'assistant/admin/approval_error.html',
            {
                'task': task,
                'error': f'Task is not pending approval. Current status: {task.get_status_display()}',
                'error_type': 'wrong_status',
            },
            status=400
        )

    # Approve the task
    try:
        task.approve()
        return render(
            request,
            'assistant/admin/approval_success.html',
            {
                'task': task,
                'action': 'approved',
            }
        )
    except Exception as e:
        return render(
            request,
            'assistant/admin/approval_error.html',
            {
                'task': task,
                'error': f'Failed to approve task: {str(e)}',
                'error_type': 'approval_failed',
            },
            status=500
        )


def reject_task(request, task_id, token):
    """
    Reject an improvement task via token-authenticated link.

    Args:
        request: The HTTP request.
        task_id: UUID of the task to reject.
        token: One-time approval token.

    Returns:
        HTML response confirming rejection or error.
    """
    task = get_object_or_404(ImprovementTaskModel, id=task_id)

    # Validate token
    if not task.is_token_valid(token):
        return render(
            request,
            'assistant/admin/approval_error.html',
            {
                'task': task,
                'error': 'Invalid or expired approval token.',
                'error_type': 'token_invalid',
            },
            status=400
        )

    # Validate task status
    if task.status != ImprovementTaskModel.STATUS_PENDING_APPROVAL:
        return render(
            request,
            'assistant/admin/approval_error.html',
            {
                'task': task,
                'error': f'Task is not pending approval. Current status: {task.get_status_display()}',
                'error_type': 'wrong_status',
            },
            status=400
        )

    # Get rejection reason from query params
    reason = request.GET.get('reason', 'Rejected via admin link')

    # Reject the task
    try:
        task.reject(reason=reason)
        return render(
            request,
            'assistant/admin/approval_success.html',
            {
                'task': task,
                'action': 'rejected',
                'reason': reason,
            }
        )
    except Exception as e:
        return render(
            request,
            'assistant/admin/approval_error.html',
            {
                'task': task,
                'error': f'Failed to reject task: {str(e)}',
                'error_type': 'rejection_failed',
            },
            status=500
        )


# Status badge color mapping
STATUS_COLORS = {
    ImprovementTaskModel.STATUS_NEW: 'blue',
    ImprovementTaskModel.STATUS_PENDING_APPROVAL: 'yellow',
    ImprovementTaskModel.STATUS_APPROVED: 'green',
    ImprovementTaskModel.STATUS_IN_PROGRESS: 'indigo',
    ImprovementTaskModel.STATUS_TESTING: 'indigo',
    ImprovementTaskModel.STATUS_COMPLETED: 'green',
    ImprovementTaskModel.STATUS_ERROR: 'red',
    ImprovementTaskModel.STATUS_REJECTED: 'gray',
    ImprovementTaskModel.STATUS_ROLLED_BACK: 'orange',
}

# Severity badge color mapping
SEVERITY_COLORS = {
    ImprovementTaskModel.SEVERITY_LOW: 'gray',
    ImprovementTaskModel.SEVERITY_MEDIUM: 'yellow',
    ImprovementTaskModel.SEVERITY_HIGH: 'red',
}


@staff_member_required
def improvement_dashboard(request):
    """
    Admin dashboard for viewing and managing improvement tasks.

    Displays all tasks with filtering, status badges, and action buttons.
    Requires staff login.
    """
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    severity_filter = request.GET.get('severity', '')

    # Build queryset
    tasks = ImprovementTaskModel.objects.all().order_by('-created_at')

    if status_filter:
        tasks = tasks.filter(status=status_filter)
    if severity_filter:
        tasks = tasks.filter(severity=severity_filter)

    # Add color information to each task
    tasks_with_colors = []
    for task in tasks:
        tasks_with_colors.append({
            'task': task,
            'status_color': STATUS_COLORS.get(task.status, 'gray'),
            'severity_color': SEVERITY_COLORS.get(task.severity, 'gray'),
        })

    # Get available choices for filters
    status_choices = ImprovementTaskModel.STATUS_CHOICES
    severity_choices = ImprovementTaskModel.SEVERITY_CHOICES

    return render(
        request,
        'assistant/admin/dashboard.html',
        {
            'tasks_with_colors': tasks_with_colors,
            'status_choices': status_choices,
            'severity_choices': severity_choices,
            'current_status': status_filter,
            'current_severity': severity_filter,
        }
    )


@staff_member_required
@require_POST
def dashboard_approve_task(request, task_id):
    """
    Approve a task from the dashboard.

    Args:
        request: The HTTP request.
        task_id: UUID of the task to approve.

    Returns:
        JSON response or redirect.
    """
    task = get_object_or_404(ImprovementTaskModel, id=task_id)

    if task.status != ImprovementTaskModel.STATUS_PENDING_APPROVAL:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': f'Task is not pending approval. Current status: {task.get_status_display()}'
            }, status=400)
        return redirect('assistant:improvement_dashboard')

    try:
        task.approve()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': 'Task approved successfully',
                'new_status': task.get_status_display(),
            })
        return redirect('assistant:improvement_dashboard')
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
        return redirect('assistant:improvement_dashboard')


@staff_member_required
@require_POST
def dashboard_reject_task(request, task_id):
    """
    Reject a task from the dashboard.

    Args:
        request: The HTTP request.
        task_id: UUID of the task to reject.

    Returns:
        JSON response or redirect.
    """
    task = get_object_or_404(ImprovementTaskModel, id=task_id)

    if task.status != ImprovementTaskModel.STATUS_PENDING_APPROVAL:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': f'Task is not pending approval. Current status: {task.get_status_display()}'
            }, status=400)
        return redirect('assistant:improvement_dashboard')

    reason = request.POST.get('reason', 'Rejected via dashboard')

    try:
        task.reject(reason=reason)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': 'Task rejected successfully',
                'new_status': task.get_status_display(),
            })
        return redirect('assistant:improvement_dashboard')
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
        return redirect('assistant:improvement_dashboard')


@staff_member_required
@require_POST
def dashboard_rollback_task(request, task_id):
    """
    Rollback a completed task from the dashboard.

    Requires:
        - Task must be in COMPLETED status
        - Task must have git_commit_before set
        - Reason must be provided in POST body

    Args:
        request: The HTTP request.
        task_id: UUID of the task to rollback.

    Returns:
        JSON response or redirect.
    """
    task = get_object_or_404(ImprovementTaskModel, id=task_id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # Validate task status
    if task.status != ImprovementTaskModel.STATUS_COMPLETED:
        error_msg = f'Only completed tasks can be rolled back. Current status: {task.get_status_display()}'
        if is_ajax:
            return JsonResponse({'success': False, 'error': error_msg}, status=400)
        return redirect('assistant:improvement_dashboard')

    # Validate git_commit_before exists
    if not task.git_commit_before:
        error_msg = 'Cannot rollback: No git commit snapshot found for this task.'
        if is_ajax:
            return JsonResponse({'success': False, 'error': error_msg}, status=400)
        return redirect('assistant:improvement_dashboard')

    # Get and validate rollback reason
    reason = request.POST.get('reason', '').strip()
    if not reason:
        error_msg = 'Rollback reason is required.'
        if is_ajax:
            return JsonResponse({'success': False, 'error': error_msg}, status=400)
        return redirect('assistant:improvement_dashboard')

    try:
        # Perform git rollback
        from .git_service import GitProtectionService
        git_service = GitProtectionService()
        rollback_result = git_service.rollback_to_commit(task.git_commit_before)

        if not rollback_result.success:
            error_msg = f'Git rollback failed: {rollback_result.message}'
            if is_ajax:
                return JsonResponse({'success': False, 'error': error_msg}, status=500)
            return redirect('assistant:improvement_dashboard')

        # Update task status using the rollback method
        task.rollback(reason=reason)

        # Notify admin of rollback completion
        from .notifications import AdminNotificationService, TaskInfo
        notification_service = AdminNotificationService()
        task_info = TaskInfo(
            task_id=str(task.id),
            title=task.title,
            description=task.suggested_fix,
            severity=task.severity,
            rollback_hash=task.git_commit_before,
        )
        notification_service.notify_task_error(
            task=task_info,
            error_details=f'Task was manually rolled back. Reason: {reason}',
            rollback_successful=True,
            rollback_hash=task.git_commit_before,
        )

        if is_ajax:
            return JsonResponse({
                'success': True,
                'message': 'Task rolled back successfully',
                'new_status': task.get_status_display(),
                'rollback_commit': task.git_commit_before[:8],
            })
        return redirect('assistant:improvement_dashboard')

    except Exception as e:
        if is_ajax:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        return redirect('assistant:improvement_dashboard')


@staff_member_required
def improvement_analytics(request):
    """
    Analytics dashboard for improvement task statistics.

    Displays metrics on system learning progress including:
    - Task counts by status (pie chart)
    - Tasks over time (line chart)
    - Success rate
    - Average completion time
    - Most common gap types
    - Recent activity feed

    Requires staff login.
    """
    # Get all tasks
    all_tasks = ImprovementTaskModel.objects.all()
    total_tasks = all_tasks.count()

    # --- Task counts by status (pie chart data) ---
    status_counts = dict(
        all_tasks.values('status')
        .annotate(count=Count('id'))
        .values_list('status', 'count')
    )

    # Build pie chart data with labels
    status_labels = {
        ImprovementTaskModel.STATUS_NEW: 'New',
        ImprovementTaskModel.STATUS_PENDING_APPROVAL: 'Pending Approval',
        ImprovementTaskModel.STATUS_APPROVED: 'Approved',
        ImprovementTaskModel.STATUS_REJECTED: 'Rejected',
        ImprovementTaskModel.STATUS_IN_PROGRESS: 'In Progress',
        ImprovementTaskModel.STATUS_TESTING: 'Testing',
        ImprovementTaskModel.STATUS_COMPLETED: 'Completed',
        ImprovementTaskModel.STATUS_ERROR: 'Error',
        ImprovementTaskModel.STATUS_ROLLED_BACK: 'Rolled Back',
    }

    pie_chart_data = {
        'labels': [],
        'values': [],
        'colors': []
    }

    status_color_map = {
        ImprovementTaskModel.STATUS_NEW: '#3b82f6',
        ImprovementTaskModel.STATUS_PENDING_APPROVAL: '#eab308',
        ImprovementTaskModel.STATUS_APPROVED: '#22c55e',
        ImprovementTaskModel.STATUS_REJECTED: '#6b7280',
        ImprovementTaskModel.STATUS_IN_PROGRESS: '#6366f1',
        ImprovementTaskModel.STATUS_TESTING: '#8b5cf6',
        ImprovementTaskModel.STATUS_COMPLETED: '#10b981',
        ImprovementTaskModel.STATUS_ERROR: '#ef4444',
        ImprovementTaskModel.STATUS_ROLLED_BACK: '#f97316',
    }

    for status, label in status_labels.items():
        count = status_counts.get(status, 0)
        if count > 0:
            pie_chart_data['labels'].append(label)
            pie_chart_data['values'].append(count)
            pie_chart_data['colors'].append(status_color_map.get(status, '#9ca3af'))

    # --- Tasks over time (line chart data) ---
    # Get tasks from last 30 days
    thirty_days_ago = timezone.now() - timedelta(days=30)
    tasks_by_date = (
        all_tasks.filter(created_at__gte=thirty_days_ago)
        .annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(count=Count('id'))
        .order_by('date')
    )

    line_chart_data = {
        'labels': [],
        'values': []
    }
    for entry in tasks_by_date:
        line_chart_data['labels'].append(entry['date'].strftime('%b %d'))
        line_chart_data['values'].append(entry['count'])

    # --- Success rate ---
    completed_count = status_counts.get(ImprovementTaskModel.STATUS_COMPLETED, 0)
    attempted_statuses = [
        ImprovementTaskModel.STATUS_COMPLETED,
        ImprovementTaskModel.STATUS_ERROR,
        ImprovementTaskModel.STATUS_ROLLED_BACK,
    ]
    attempted_count = sum(status_counts.get(s, 0) for s in attempted_statuses)
    success_rate = (completed_count / attempted_count * 100) if attempted_count > 0 else 0

    # --- Average time from creation to completion ---
    completed_tasks = all_tasks.filter(
        status=ImprovementTaskModel.STATUS_COMPLETED,
        completed_at__isnull=False
    )

    avg_completion_time = None
    if completed_tasks.exists():
        # Calculate average in Python since Django ORM has issues with datetime arithmetic
        completion_times = []
        for task in completed_tasks:
            if task.completed_at and task.created_at:
                delta = task.completed_at - task.created_at
                completion_times.append(delta.total_seconds())

        if completion_times:
            avg_seconds = sum(completion_times) / len(completion_times)
            avg_completion_time = timedelta(seconds=avg_seconds)

    # Format avg_completion_time for display
    avg_completion_display = None
    if avg_completion_time:
        total_minutes = int(avg_completion_time.total_seconds() / 60)
        if total_minutes < 60:
            avg_completion_display = f"{total_minutes} minutes"
        elif total_minutes < 1440:  # Less than a day
            hours = total_minutes // 60
            mins = total_minutes % 60
            avg_completion_display = f"{hours}h {mins}m"
        else:
            days = total_minutes // 1440
            hours = (total_minutes % 1440) // 60
            avg_completion_display = f"{days}d {hours}h"

    # --- Most common gap types ---
    gap_type_counts = dict(
        all_tasks.values('gap_type')
        .annotate(count=Count('id'))
        .values_list('gap_type', 'count')
    )

    gap_type_labels = {
        ImprovementTaskModel.GAP_TYPE_UNKNOWN_DATA_TYPE: 'Unknown Data Type',
        ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS: 'Missing Keywords',
        ImprovementTaskModel.GAP_TYPE_NO_DATA_METHOD: 'No Data Method',
        ImprovementTaskModel.GAP_TYPE_UNSUPPORTED_QUERY_PATTERN: 'Unsupported Query Pattern',
    }

    gap_types_list = []
    for gap_type, label in gap_type_labels.items():
        count = gap_type_counts.get(gap_type, 0)
        if count > 0:
            gap_types_list.append({
                'type': label,
                'count': count,
                'percentage': round(count / total_tasks * 100, 1) if total_tasks > 0 else 0
            })

    gap_types_list.sort(key=lambda x: x['count'], reverse=True)

    # --- Most frequently improved files ---
    # Parse code_template to extract file paths (simplified)
    # Look for patterns like "# File: path/to/file.py" in code_template
    file_counter = Counter()
    for task in all_tasks.filter(code_template__isnull=False).exclude(code_template=''):
        code = task.code_template
        # Simple heuristic: look for lines starting with "# File:" or containing file paths
        for line in code.split('\n'):
            if line.strip().startswith('# File:'):
                file_path = line.replace('# File:', '').strip()
                if file_path:
                    file_counter[file_path] += 1
            elif 'intent_detector.py' in line:
                file_counter['assistant/intent_detector.py'] += 1
            elif 'data_service.py' in line:
                file_counter['assistant/data_service.py'] += 1
            elif 'context_builder.py' in line:
                file_counter['assistant/context_builder.py'] += 1

    # If no files found from parsing, show common files based on gap types
    if not file_counter:
        # Infer from gap types
        keywords_count = gap_type_counts.get(ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS, 0)
        data_method_count = gap_type_counts.get(ImprovementTaskModel.GAP_TYPE_NO_DATA_METHOD, 0)

        if keywords_count > 0:
            file_counter['assistant/intent_detector.py'] = keywords_count
        if data_method_count > 0:
            file_counter['assistant/data_service.py'] = data_method_count

    improved_files = [
        {'path': path, 'count': count}
        for path, count in file_counter.most_common(5)
    ]

    # --- Recent activity feed ---
    recent_tasks = all_tasks.order_by('-updated_at')[:10]
    activity_feed = []
    for task in recent_tasks:
        action = _get_task_action_description(task)
        activity_feed.append({
            'task': task,
            'action': action,
            'timestamp': task.updated_at,
            'status_color': STATUS_COLORS.get(task.status, 'gray'),
        })

    # --- Severity breakdown ---
    severity_counts = dict(
        all_tasks.values('severity')
        .annotate(count=Count('id'))
        .values_list('severity', 'count')
    )

    severity_data = []
    for severity, label in ImprovementTaskModel.SEVERITY_CHOICES:
        count = severity_counts.get(severity, 0)
        severity_data.append({
            'label': label,
            'count': count,
            'color': SEVERITY_COLORS.get(severity, 'gray'),
        })

    return render(
        request,
        'assistant/admin/analytics.html',
        {
            'total_tasks': total_tasks,
            'pie_chart_data': pie_chart_data,
            'line_chart_data': line_chart_data,
            'success_rate': round(success_rate, 1),
            'completed_count': completed_count,
            'attempted_count': attempted_count,
            'avg_completion_display': avg_completion_display,
            'gap_types_list': gap_types_list,
            'improved_files': improved_files,
            'activity_feed': activity_feed,
            'severity_data': severity_data,
        }
    )


def _get_task_action_description(task):
    """Get a human-readable description of the task's current state."""
    status_actions = {
        ImprovementTaskModel.STATUS_NEW: 'was created',
        ImprovementTaskModel.STATUS_PENDING_APPROVAL: 'is awaiting approval',
        ImprovementTaskModel.STATUS_APPROVED: 'was approved',
        ImprovementTaskModel.STATUS_REJECTED: 'was rejected',
        ImprovementTaskModel.STATUS_IN_PROGRESS: 'is being processed',
        ImprovementTaskModel.STATUS_TESTING: 'is being tested',
        ImprovementTaskModel.STATUS_COMPLETED: 'completed successfully',
        ImprovementTaskModel.STATUS_ERROR: 'encountered an error',
        ImprovementTaskModel.STATUS_ROLLED_BACK: 'was rolled back',
    }
    return status_actions.get(task.status, 'was updated')
