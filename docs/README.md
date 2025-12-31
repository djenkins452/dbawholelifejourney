# ==============================================================================
# File: docs/README.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Index of all project documentation files
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-30
# Last Updated: 2025-12-30
# ==============================================================================

# WLJ Project Documentation

This directory contains all project documentation for the Whole Life Journey application. Files follow a consistent naming convention: `wlj_<category>_<descriptor>.md`.

## Naming Convention

All documentation files follow this pattern:
```
wlj_<category>_<descriptor>.md
```

**Categories:**
- `wlj_claude_*` - Claude Code AI context files
- `wlj_backup_*` - Backup and disaster recovery
- `wlj_security_*` - Security reviews and reports
- `wlj_system_*` - System audits and reviews
- `wlj_third_party_*` - Third-party service documentation
- `wlj_camera_*` - Camera/scan feature architecture

## Documentation Index

### Claude Context Files
| File | Description |
|------|-------------|
| `wlj_claude_changelog.md` | Historical record of fixes, migrations, and changes |
| `wlj_claude_features.md` | Detailed feature documentation for all major features |
| `wlj_claude_beacon.md` | Session context for WLJ Financial Dashboard (Beacon site) |

### Backup & Operations
| File | Description |
|------|-------------|
| `wlj_backup.md` | Disaster recovery playbook and backup procedures |
| `wlj_backup_report.md` | Backup operation reports and history |

### Security
| File | Description |
|------|-------------|
| `wlj_security_review.md` | Security review with 21 findings and remediation status |

### System
| File | Description |
|------|-------------|
| `wlj_system_audit.md` | System audit report with health score and findings |
| `wlj_system_review.md` | Repeatable audit process and checklists |

### Third-Party Services
| File | Description |
|------|-------------|
| `wlj_third_party_services.md` | Inventory of all third-party services and APIs |

### Architecture
| File | Description |
|------|-------------|
| `wlj_camera_scan_architecture.md` | Camera scan feature architecture and security design |

## Root-Level Files

The main Claude context file remains at the project root for discovery:
- **`CLAUDE.md`** - Master prompt and project context (references files in this directory)

## Adding New Documentation

When creating new documentation files:

1. Use the naming convention: `wlj_<category>_<descriptor>.md`
2. Add the standard header:
   ```markdown
   # ==============================================================================
   # File: docs/wlj_<category>_<descriptor>.md
   # Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
   # Description: Brief description
   # Owner: Danny Jenkins (dannyjenkins71@gmail.com)
   # Created: YYYY-MM-DD
   # Last Updated: YYYY-MM-DD
   # ==============================================================================
   ```
3. Update this README with the new file
4. Update `CLAUDE.md` if it should be referenced there

---

*Last updated: 2025-12-30*
