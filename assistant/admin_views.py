"""
Admin views for approving and rejecting improvement tasks.

This module provides secure endpoints for admin approval of improvement
tasks via email links with one-time tokens.
"""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

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
