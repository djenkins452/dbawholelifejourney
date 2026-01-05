# Self-Improvement System Runbook

**Owner:** admin@wholelifejourney.com
**Last Updated:** 2026-01-05

Operational procedures and troubleshooting guide for the Personal Assistant Self-Improvement System.

---

## Table of Contents

1. [Quick Reference](#quick-reference)
2. [Common Operations](#common-operations)
3. [Troubleshooting](#troubleshooting)
4. [Emergency Procedures](#emergency-procedures)
5. [Monitoring](#monitoring)

---

## Quick Reference

### Key URLs

| URL | Description |
|-----|-------------|
| `/assistant/admin/dashboard/` | Task management dashboard |
| `/assistant/admin/analytics/` | Task analytics and metrics |
| `/assistant/admin/health/` | System health status |

### Management Commands

```bash
# Check queue status
python manage.py shell -c "from assistant.tasks import get_queue_status; print(get_queue_status())"

# Run health check
python manage.py shell -c "from assistant.health_monitor import run_health_check; print(run_health_check())"
```

### Safety Limit Defaults

| Limit | Value |
|-------|-------|
| Hourly executions | 5 |
| Daily executions | 20 |
| Pending task cap | 50 |
| File mods/day | 3 |
| Error rate threshold | 30% |

---

## Common Operations

### How to Manually Rollback a Change

#### Via Admin Dashboard

1. Navigate to `/assistant/admin/dashboard/`
2. Find the completed task in the task list
3. Click "Rollback" button
4. Enter rollback reason when prompted
5. Confirm the rollback

#### Via Django Shell

```python
from assistant.models import ImprovementTaskModel
from assistant.git_service import GitProtectionService

# Find the task
task = ImprovementTaskModel.objects.get(id='<task-uuid>')

# Perform git rollback
git = GitProtectionService()
result = git.rollback_to_commit(task.git_commit_before)
print(f"Rollback result: {result.success} - {result.message}")

# Update task status
if result.success:
    task.rollback(reason='Manual rollback via shell')
    print(f"Task {task.id} rolled back successfully")
```

#### Via Git Command Line

```bash
# Find the commit to rollback to
git log --oneline -10

# Hard reset to pre-task commit
git reset --hard <commit-hash>

# Force push if needed (CAUTION: destructive)
git push --force origin main
```

---

### How to Pause All Autonomous Improvements

#### Via Admin Dashboard

1. Navigate to `/assistant/admin/health/`
2. Click "Pause System" button
3. Enter reason for pausing

#### Via Django Shell

```python
from assistant.safety_limits import SafetyLimitService

service = SafetyLimitService()
service.pause_system(reason='Maintenance window')
print("System paused")
```

#### Via Cache Directly

```python
from django.core.cache import cache

# Pause for 24 hours (default)
cache.set('safety_limits:system_paused', 'Manual pause', timeout=86400)

# Verify pause status
print(f"System paused: {cache.get('safety_limits:system_paused')}")
```

---

### How to Resume Autonomous Improvements

#### Via Admin Dashboard

1. Navigate to `/assistant/admin/health/`
2. Click "Resume System" button

#### Via Django Shell

```python
from assistant.safety_limits import SafetyLimitService

service = SafetyLimitService()
service.resume_system()
print("System resumed")
```

#### Via Cache Directly

```python
from django.core.cache import cache

cache.delete('safety_limits:system_paused')
print("System resumed")
```

---

### How to Investigate a Failed Task

#### Step 1: Find the Task

```python
from assistant.models import ImprovementTaskModel

# Find by ID
task = ImprovementTaskModel.objects.get(id='<task-uuid>')

# Or find recent errors
errors = ImprovementTaskModel.objects.filter(
    status=ImprovementTaskModel.STATUS_ERROR
).order_by('-updated_at')[:5]

for task in errors:
    print(f"{task.id}: {task.title}")
    print(f"  Error: {task.error_message}")
    print(f"  Updated: {task.updated_at}")
    print()
```

#### Step 2: Check Error Details

```python
# View full task details
task = ImprovementTaskModel.objects.get(id='<task-uuid>')
print(f"Title: {task.title}")
print(f"Status: {task.status}")
print(f"Error: {task.error_message}")
print(f"Git Before: {task.git_commit_before}")
print(f"Git After: {task.git_commit_after}")
print(f"Code Template:\n{task.code_template}")
print(f"Test Template:\n{task.test_template}")
```

#### Step 3: Check Git Diff

```bash
# If git_commit_before and git_commit_after exist
git diff <git_commit_before> <git_commit_after>
```

#### Step 4: Review Logs

```bash
# Check Django logs
tail -f /var/log/wlj/django.log | grep "task.*<task-uuid>"

# Or in development
grep "task.*<task-uuid>" logs/django.log
```

#### Step 5: Retry or Reject

```python
# Retry the task
task.transition_status(ImprovementTaskModel.STATUS_NEW)
print(f"Task {task.id} reset to NEW status")

# Or reject permanently
task.reject(reason='Manual investigation - issue with approach')
print(f"Task {task.id} rejected")
```

---

### How to Reset the System After Errors

#### Full System Reset

```python
from django.core.cache import cache
from assistant.models import ImprovementTaskModel

# 1. Clear all rate limit caches
cache.delete('safety_limits:autonomous_hourly_count')
cache.delete('safety_limits:autonomous_daily_count')
cache.delete('safety_limits:system_paused')

# 2. Clear file modification caches (if needed)
# These expire after 24 hours automatically

# 3. Reset stuck tasks
stuck = ImprovementTaskModel.objects.filter(
    status=ImprovementTaskModel.STATUS_IN_PROGRESS
)
for task in stuck:
    task.transition_status(
        ImprovementTaskModel.STATUS_ERROR,
        error_message='Reset during system recovery'
    )
print(f"Reset {stuck.count()} stuck tasks")

# 4. Resume system
cache.delete('safety_limits:system_paused')
print("System reset complete")
```

#### Reset Specific File Modification Limit

```python
from django.core.cache import cache

file_path = 'assistant/intent_detector.py'
normalized = file_path.replace('/', '_').replace('\\', '_')
cache_key = f'safety_limits:file_modifications:{normalized}'
cache.delete(cache_key)
print(f"Reset modification limit for {file_path}")
```

---

## Troubleshooting

### Task Stuck in IN_PROGRESS

**Symptoms:**
- Task shows "In Progress" for more than 30 minutes
- No completion or error notification received

**Resolution:**

```python
from assistant.models import ImprovementTaskModel
from django.utils import timezone
from datetime import timedelta

# Find stuck tasks
threshold = timezone.now() - timedelta(minutes=30)
stuck = ImprovementTaskModel.objects.filter(
    status=ImprovementTaskModel.STATUS_IN_PROGRESS,
    updated_at__lt=threshold
)

for task in stuck:
    print(f"Stuck task: {task.id} - {task.title}")

    # Option 1: Reset to approved to retry
    task.transition_status(ImprovementTaskModel.STATUS_APPROVED)

    # Option 2: Mark as error
    # task.transition_status(
    #     ImprovementTaskModel.STATUS_ERROR,
    #     error_message='Task timeout - stuck in IN_PROGRESS'
    # )
```

---

### Rate Limit Hit - Can't Execute Tasks

**Symptoms:**
- Tasks failing with "Rate limit exceeded" message
- System appears to be paused

**Resolution:**

```python
from assistant.safety_limits import SafetyLimitService

service = SafetyLimitService()

# Check current limits
rate_result = service.check_rate_limits()
print(f"Allowed: {rate_result.allowed}")
print(f"Reason: {rate_result.reason}")
print(f"Current: {rate_result.current_count}")
print(f"Limit: {rate_result.limit}")

# Option 1: Wait for limit to reset (hourly counters)

# Option 2: Increase limit temporarily
from assistant.safety_limits import SafetyLimitOverride
from django.utils import timezone
from datetime import timedelta

SafetyLimitOverride.objects.create(
    limit_name='max_autonomous_per_hour',
    value=10,
    is_active=True,
    reason='Emergency increase',
    expires_at=timezone.now() + timedelta(hours=2)
)
```

---

### System Auto-Paused Due to Error Rate

**Symptoms:**
- System health shows CRITICAL or DEGRADED
- Autonomous execution stopped
- Error rate notification received

**Resolution:**

```python
from assistant.health_monitor import HealthMonitor

# 1. Check health status
monitor = HealthMonitor()
report = monitor.get_health_report()
print(f"Status: {report['status']}")
print(f"Error Rate: {report['error_rate']}%")
print(f"Recommendations: {report['recommendations']}")

# 2. Investigate recent errors (see "How to Investigate a Failed Task")

# 3. Fix underlying issue (code bug, test issue, etc.)

# 4. Resume system after fixing
from assistant.safety_limits import SafetyLimitService
service = SafetyLimitService()
service.resume_system()
```

---

### Git Rollback Failed

**Symptoms:**
- Error notification shows "Rollback failed"
- Working directory may be in inconsistent state

**Resolution:**

```bash
# 1. Check git status
cd /path/to/dbawholelifejourney
git status

# 2. Check for uncommitted changes
git diff

# 3. Stash or discard changes
git stash  # or: git checkout -- .

# 4. Verify repository state
git log --oneline -5

# 5. Manual rollback if needed
git reset --hard <known-good-commit>
```

---

### Approval Token Expired

**Symptoms:**
- Admin clicks approval link, gets "Token expired" error
- Task still in PENDING_APPROVAL status

**Resolution:**

```python
from assistant.models import ImprovementTaskModel

task = ImprovementTaskModel.objects.get(id='<task-uuid>')

# Option 1: Regenerate token
new_token = task.generate_approval_token()
print(f"New approval link: /assistant/admin/approve/{task.id}/{new_token}/")

# Option 2: Approve via dashboard (no token needed)
# Navigate to /assistant/admin/dashboard/ and use the approve button

# Option 3: Approve via shell
task.approve(user=None)  # Or pass a User object
print(f"Task {task.id} approved")
```

---

## Emergency Procedures

### Complete System Shutdown

If the self-improvement system is causing issues in production:

```python
from django.core.cache import cache
from assistant.safety_limits import SafetyLimitOverride

# 1. Pause system immediately
cache.set('safety_limits:system_paused', 'EMERGENCY SHUTDOWN', timeout=86400*30)

# 2. Disable via override
SafetyLimitOverride.objects.update_or_create(
    limit_name='system_enabled',
    defaults={
        'value': 0,
        'is_active': True,
        'reason': 'EMERGENCY SHUTDOWN'
    }
)

print("System shut down - no autonomous improvements will execute")
```

### Revert All Recent Changes

```bash
# Find commits from self-improvement system
git log --oneline --grep="Task" -20

# Reset to before self-improvement commits
git reset --hard <pre-improvement-commit>

# Force push (DANGEROUS - coordinate with team)
git push --force origin main
```

---

## Monitoring

### Key Metrics to Watch

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| Error Rate (24h) | < 20% | 20-40% | > 40% |
| Rollback Rate (24h) | < 15% | 15-30% | > 30% |
| Consecutive Failures | < 3 | 3-4 | >= 5 |
| Pending Tasks | < 30 | 30-50 | > 50 |
| Stuck Tasks | 0 | 1-2 | > 2 |

### Health Check Command

```python
from assistant.health_monitor import run_health_check

result = run_health_check()
print(f"""
System Health: {result['status']}
Reason: {result['reason']}
Error Rate: {result['error_rate']}%
Rollback Rate: {result['rollback_rate']}%
Consecutive Failures: {result['consecutive_failures']}
""")
```

### Queue Status Command

```python
from assistant.tasks import get_queue_status

status = get_queue_status()
print(f"""
Queue Status:
  Pending Approval: {status['pending_approval']}
  Approved (ready): {status['approved']}
  Autonomous (ready): {status['autonomous']}
  In Progress: {status['in_progress']}
  Stuck (>30min): {status['stuck']}
  Completed Today: {status['completed_today']}
  Errors Today: {status['errors_today']}
""")
```

---

## See Also

- [SELF_IMPROVEMENT.md](./SELF_IMPROVEMENT.md) - System architecture and configuration
- [wlj_claude_troubleshoot.md](../wlj_claude_troubleshoot.md) - General troubleshooting
