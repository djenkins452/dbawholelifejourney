# Whole Life Journey - Codebase Metrics Report

**Generated:** 2026-01-05
**Project:** Whole Life Journey - Django 5.x Personal Wellness/Journaling App

---

## Overview

This document captures comprehensive metrics about the Whole Life Journey codebase, including file statistics, code architecture, and git activity patterns. These metrics are also available in real-time via the Admin Console.

---

## Project Summary

| Metric | Value |
|--------|-------|
| **Project Age** | 12 days (Dec 24, 2025 - Jan 5, 2026) |
| **Total Size** | ~16 MB |
| **Django Apps** | 15 |
| **Total Commits** | 894+ |

---

## File Statistics

| File Type | Count | Lines |
|-----------|-------|-------|
| Python files | 539 | 140,580 |
| HTML templates | 330 | 81,997 |
| JavaScript files | 7 | - |
| CSS files | 6 | - |
| Markdown docs | 39 | - |
| Test files | 71 | - |
| Migration files | 158 | - |

---

## Code Architecture

| Component | Count |
|-----------|-------|
| Django Models | 81 |
| View Functions | 866 |
| URL Routes | 557 |
| Python Classes | 2,052 |
| Python Functions | 5,658 |
| Test Methods | 2,688 |
| Dependencies | 31 |
| Unique Imports | 380 |
| TODOs/FIXMEs | 15 |

### Django Apps

The project includes the following Django apps:

- `admin_console` - Custom admin interface for site management
- `ai` - AI coaching and assistant features (OpenAI integration)
- `core` - Core models, themes, categories, site configuration
- `dashboard` - User dashboard and navigation
- `faith` - Faith journey tracking (optional feature)
- `finance` - Financial wellness tracking
- `health` - Health metrics and glucose tracking (Dexcom/Clarity import)
- `help` - Help system and documentation
- `journal` - Journal entries and prompts
- `life` - Organize: tasks, projects, events, and milestones
- `purpose` - Goals: life goals, intentions, and annual direction
- `scan` - Document scanning features
- `sms` - SMS notifications
- `users` - Custom user model and authentication

---

## Git Activity

### Overall Statistics

| Metric | Value |
|--------|-------|
| Total Commits | 894 |
| Total Insertions | 285,641 |
| Total Deletions | 14,059 |
| Net Lines Added | +271,582 |
| Unique Days with Commits | 12 |
| Average Commits per Day | ~74.5 |

### Commit Breakdown by Type

| Type | Count | Percentage |
|------|-------|------------|
| Features/Additions | 453 | ~51% |
| Bug Fixes | 239 | ~27% |
| AI-Assisted (Claude) | 187 | ~21% |
| Refactoring | 28 | ~3% |

### Most Productive Days

| Rank | Date | Commits |
|------|------|---------|
| 1st | Dec 28, 2025 | 136 |
| 2nd | Jan 4, 2026 | 112 |
| 3rd | Jan 5, 2026 | 105 |
| 4th | Dec 27, 2025 | 97 |
| 5th | Dec 29, 2025 | 92 |

### Commits by Day of Week

| Day | Commits |
|-----|---------|
| Sunday | 248 |
| Monday | 197 |
| Saturday | 164 |
| Friday | 103 |
| Thursday | 91 |
| Wednesday | 80 |
| Tuesday | 11 |

### Peak Coding Hours

| Hour | Commits |
|------|---------|
| 10 AM | 73 |
| 11 AM | 68 |
| 7 PM | 66 |
| 9 AM | 66 |
| 10 PM | 60 |

---

## Accessing Live Metrics

The Codebase Metrics report is available in the Admin Console:

**URL:** `/admin-console/codebase-metrics/`

**Access Requirements:**
- Must be logged in as a staff user (is_staff=True)

**Features:**
- Real-time metrics generation on page load
- Refresh button to regenerate metrics
- Visual charts for commits by day of week
- Progress bars for commit type breakdown

---

## Technical Implementation

### Service Module

The metrics are gathered by `apps/admin_console/metrics_service.py`:

```python
from apps.admin_console.metrics_service import get_project_metrics

# Get all metrics
metrics = get_project_metrics()

# Access specific metric categories
file_metrics = metrics.file_metrics
code_metrics = metrics.code_metrics
git_metrics = metrics.git_metrics
```

### Data Classes

The service uses Python dataclasses for structured data:

- `FileMetrics` - File counts and sizes
- `CodeMetrics` - Code structure metrics
- `GitMetrics` - Git history and activity
- `ProjectMetrics` - Combined metrics container

### View

The view is implemented as a Django `TemplateView`:

```python
class CodebaseMetricsView(HelpContextMixin, AdminRequiredMixin, TemplateView):
    template_name = "admin_console/codebase_metrics.html"
```

---

## Fun Facts

- Code has been written **every single day** since project start (12 consecutive days)
- **21% of commits** were AI-assisted with Claude
- Most intense day (Dec 28) had **136 commits** - about 8.5 commits per waking hour!
- The project has grown by **~23,800 lines per day** on average
- **2,688 test methods** demonstrate strong test coverage focus
- Sunday is the most productive day with **248 commits**

---

## Related Documentation

- [CLAUDE.md](../CLAUDE.md) - Project context for Claude Code
- [wlj_claude_features.md](wlj_claude_features.md) - Feature documentation
- [wlj_claude_changelog.md](wlj_claude_changelog.md) - Change history

---

*Last updated: 2026-01-05*
