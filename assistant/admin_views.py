"""
Admin views for approving and rejecting improvement tasks.

This module provides secure endpoints for admin approval of improvement
tasks via email links with one-time tokens, plus a dashboard for managing tasks.
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
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
