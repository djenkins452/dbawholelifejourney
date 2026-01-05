# WLJ Personal Assistant Self-Improvement System

**Owner:** admin@wholelifejourney.com
**Last Updated:** 2026-01-05

This document describes the architecture, components, and operation of the Personal Assistant Self-Improvement System - an autonomous system that detects knowledge gaps and generates improvement tasks.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Module Reference](#module-reference)
4. [Task Lifecycle](#task-lifecycle)
5. [Safety Limits](#safety-limits)
6. [Email Notifications](#email-notifications)
7. [Admin Dashboard](#admin-dashboard)
8. [Configuration](#configuration)

---

## System Overview

The Self-Improvement System enables the Personal Assistant to:

1. **Detect Knowledge Gaps** - Identify when user queries cannot be answered
2. **Generate Improvement Tasks** - Create actionable tasks to address gaps
3. **Execute Safely** - Apply changes with git snapshots and rollback capability
4. **Notify Administrators** - Keep admins informed of all activities

### Key Principles

- **Safety First**: All changes are reversible via git rollback
- **Rate Limited**: Prevents runaway self-modification
- **Approval Workflow**: HIGH/MEDIUM severity tasks require admin approval
- **Full Audit Trail**: Every task has git commit hashes for before/after states

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER QUERY FLOW                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   Intent Detector   │───▶│   Data Service      │───▶│   Gap Detector      │
│  (intent_detector)  │    │   (data_service)    │    │   (gap_detector)    │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
                                                               │
                                                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         IMPROVEMENT TASK PIPELINE                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   Task Generator    │───▶│  ImprovementTask    │───▶│   Admin Review      │
│  (task_generator)   │    │   Model (models)    │    │  (admin_views)      │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
                                                               │
                                    ┌──────────────────────────┼──────────────┐
                                    │                          │              │
                                    ▼                          ▼              ▼
                           ┌──────────────┐           ┌──────────────┐ ┌────────────┐
                           │   Approved   │           │   Rejected   │ │   Pending  │
                           └──────────────┘           └──────────────┘ └────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXECUTION ENGINE                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Safety Limits   │    │  Git Protection  │    │   Test Runner    │
│ (safety_limits)  │    │  (git_service)   │    │  (test_runner)   │
└──────────────────┘    └──────────────────┘    └──────────────────┘
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    │
                                    ▼
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│  File Modifier      │───▶│   Executor          │───▶│  Health Monitor     │
│ (file_modifier)     │    │   (executor)        │    │ (health_monitor)    │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NOTIFICATION LAYER                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────┐    ┌─────────────────────┐
│  Admin Email        │    │  Admin Dashboard    │
│  (notifications)    │    │  (admin_views)      │
└─────────────────────┘    └─────────────────────┘
```

---

## Module Reference

### Core Modules

| Module | File | Purpose |
|--------|------|---------|
| **Intent Detector** | `intent_detector.py` | Detects user query intent and data types requested |
| **Data Service** | `data_service.py` | Retrieves personal data (weight, journal, mood, etc.) |
| **Gap Detector** | `gap_detector.py` | Identifies knowledge gaps when queries fail |
| **Task Generator** | `task_generator.py` | Creates improvement tasks from detected gaps |
| **Models** | `models.py` | `ImprovementTaskModel` with full lifecycle tracking |

### Execution Engine

| Module | File | Purpose |
|--------|------|---------|
| **Executor** | `executor.py` | `ImprovementExecutor` - main orchestrator for task execution |
| **Autonomous Executor** | `executor.py` | `AutonomousExecutor` - handles LOW severity tasks without approval |
| **Git Service** | `git_service.py` | `GitProtectionService` - creates snapshots and handles rollback |
| **File Modifier** | `file_modifier.py` | `SafeFileModifier` - applies code changes safely |
| **Test Runner** | `test_runner.py` | `MockTestRunner` - validates changes with tests |

### Safety & Monitoring

| Module | File | Purpose |
|--------|------|---------|
| **Safety Limits** | `safety_limits.py` | Rate limiting, file modification limits, system pause |
| **Health Monitor** | `health_monitor.py` | Tracks error rates, triggers system pause on degradation |
| **Notifications** | `notifications.py` | `AdminNotificationService` - sends email alerts |

### Admin Interface

| Module | File | Purpose |
|--------|------|---------|
| **Admin Views** | `admin_views.py` | Dashboard, approval, rollback, health check endpoints |
| **URLs** | `urls.py` | URL routing for admin interface |
| **Tasks** | `tasks.py` | Background task definitions (APScheduler) |

---

## Task Lifecycle

### Status Flow Diagram

```
    ┌─────────┐
    │   NEW   │ ────────────────────────────────────────┐
    └────┬────┘                                          │
         │                                               │
         │ (requires_approval=True)                      │ (LOW severity,
         ▼                                               │  no approval)
┌─────────────────────┐                                  │
│  PENDING_APPROVAL   │◀─────────────────────────────────┘
└────────┬────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐  ┌──────────┐
│APPROVED│  │ REJECTED │
└───┬────┘  └──────────┘
    │
    ▼
┌─────────────┐
│ IN_PROGRESS │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   TESTING   │
└──────┬──────┘
       │
   ┌───┴───┐
   │       │
   ▼       ▼
┌─────────┐  ┌───────┐
│COMPLETED│  │ ERROR │
└────┬────┘  └───┬───┘
     │           │
     ▼           ▼
┌─────────────┐
│ ROLLED_BACK │
└─────────────┘
```

### Status Definitions

| Status | Description |
|--------|-------------|
| `NEW` | Task created, awaiting initial processing |
| `PENDING_APPROVAL` | Waiting for admin approval (email sent with approval link) |
| `APPROVED` | Admin approved, ready for execution |
| `REJECTED` | Admin rejected the task |
| `IN_PROGRESS` | Currently being executed |
| `TESTING` | Code applied, running tests |
| `COMPLETED` | Successfully executed and committed |
| `ERROR` | Execution failed, rolled back to snapshot |
| `ROLLED_BACK` | Manually rolled back by admin |

### Valid Transitions

```python
ALLOWED_TRANSITIONS = {
    'new': ['pending_approval', 'approved'],
    'pending_approval': ['approved', 'rejected', 'new'],
    'approved': ['in_progress', 'pending_approval'],
    'rejected': ['new'],  # Can retry rejected tasks
    'in_progress': ['testing', 'error', 'approved'],
    'testing': ['completed', 'error', 'in_progress'],
    'completed': ['rolled_back'],
    'error': ['new', 'approved', 'rolled_back'],
    'rolled_back': ['new'],
}
```

---

## Safety Limits

### Default Limits

| Limit | Default Value | Description |
|-------|---------------|-------------|
| `MAX_AUTONOMOUS_PER_HOUR` | 5 | Maximum autonomous executions per hour |
| `MAX_AUTONOMOUS_PER_DAY` | 20 | Maximum autonomous executions per day |
| `MAX_PENDING_TASKS` | 50 | Maximum tasks in queue before pausing |
| `MAX_FILE_MODIFICATIONS_PER_FILE_PER_DAY` | 3 | Maximum modifications per file per day |
| `ERROR_RATE_THRESHOLD` | 30% | Error rate that triggers system pause |

### Overriding Limits

Limits can be overridden via Django Admin or programmatically:

```python
from assistant.safety_limits import SafetyLimitOverride

# Increase hourly limit temporarily
SafetyLimitOverride.objects.create(
    limit_name='max_autonomous_per_hour',
    value=10,
    is_active=True,
    reason='Increased for batch processing',
    expires_at=timezone.now() + timedelta(hours=4)
)

# Disable system entirely
SafetyLimitOverride.objects.create(
    limit_name='system_enabled',
    value=0,  # 0 = disabled
    is_active=True,
    reason='Maintenance window'
)
```

### Cache Keys

| Cache Key | Purpose |
|-----------|---------|
| `safety_limits:autonomous_hourly_count` | Hourly execution counter |
| `safety_limits:autonomous_daily_count` | Daily execution counter |
| `safety_limits:file_modifications:{file_path}` | Per-file modification counter |
| `safety_limits:system_paused` | System pause flag |

---

## Email Notifications

### Notification Types

| Type | Trigger | Template |
|------|---------|----------|
| **Task Created** | New improvement task detected | `task_created.html` |
| **Approval Request** | Task needs admin approval | `approval_request.html` |
| **Task Completed** | Task executed successfully | `task_completed.html` |
| **Task Error** | Task failed, rolled back | `task_error.html` |
| **Auto Improvement** | Autonomous execution completed | `auto_improvement.html` |
| **Queue Status** | Safety limit reached | `queue_status.html` |

### Email Configuration

Set in Django settings:

```python
# settings.py
ADMIN_EMAIL = 'admin@wholelifejourney.com'
DEFAULT_FROM_EMAIL = 'noreply@wholelifejourney.com'

# Email backend (production)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.example.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
```

### Approval Links

Approval emails contain secure token-based links:

```
https://wholelifejourney.com/assistant/admin/approve/{task_id}/{token}/
https://wholelifejourney.com/assistant/admin/reject/{task_id}/{token}/
```

Tokens expire after **24 hours** (configurable via `APPROVAL_TOKEN_EXPIRY_HOURS`).

---

## Admin Dashboard

### Available URLs

| URL | View | Purpose |
|-----|------|---------|
| `/assistant/admin/dashboard/` | `improvement_dashboard` | Main task management dashboard |
| `/assistant/admin/analytics/` | `improvement_analytics` | Task metrics and charts |
| `/assistant/admin/health/` | `system_health_check` | System health status |
| `/assistant/admin/health/pause/` | `system_pause` | Pause autonomous execution |
| `/assistant/admin/health/resume/` | `system_resume` | Resume autonomous execution |

### Dashboard Actions

- **Approve Task**: Approve pending task from dashboard
- **Reject Task**: Reject pending task with reason
- **Rollback Task**: Rollback completed task to pre-change state
- **View Details**: See full task details including git diff

### Health Dashboard

The health dashboard shows:

- **Error Rate (24h)**: Percentage of failed tasks
- **Rollback Rate (24h)**: Percentage of rolled back tasks
- **Consecutive Failures**: Number of tasks failed in a row
- **System Status**: HEALTHY / DEGRADED / CRITICAL

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_EMAIL` | admin@wholelifejourney.com | Admin notification recipient |
| `APPROVAL_TOKEN_EXPIRY_HOURS` | 24 | Hours until approval tokens expire |

### Django Settings

```python
# Enable/disable the self-improvement system
ASSISTANT_SELF_IMPROVEMENT_ENABLED = True

# Files allowed for autonomous modification
ASSISTANT_ALLOWED_FILES = [
    'assistant/intent_detector.py',
    'assistant/data_service.py',
    'assistant/context_builder.py',
]
```

### APScheduler Jobs

Background tasks are scheduled via APScheduler:

| Job | Interval | Function |
|-----|----------|----------|
| Process Approved Tasks | 5 minutes | `process_approved_tasks()` |
| Process Autonomous Tasks | 5 minutes | `process_autonomous_tasks()` |
| Monitor Stuck Tasks | 10 minutes | `monitor_stuck_tasks()` |
| Health Check | 15 minutes | `run_health_check()` |

---

## See Also

- [RUNBOOK.md](./RUNBOOK.md) - Troubleshooting and operational procedures
- [wlj_claude_troubleshoot.md](../wlj_claude_troubleshoot.md) - Known issues and solutions
- [wlj_claude_changelog.md](../wlj_claude_changelog.md) - Historical changes
