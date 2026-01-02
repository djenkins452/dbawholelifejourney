# ==============================================================================
# File: docs/wlj_backup.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Disaster recovery playbook and backup procedures
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-28
# Last Updated: 2026-01-02
# ==============================================================================

# WLJ Backup - Disaster Recovery Playbook

**Document Version:** 1.1
**Last Updated:** 2026-01-02
**Authority:** This document is the SOLE operational authority for backup, restore, and disaster recovery operations. Claude instances executing recovery operations treat this document as executable specification.

---

## 1. BACKUP SYSTEM OVERVIEW

### 1.1 What Is Backed Up

| Category | Description | Backup Method | Frequency |
|----------|-------------|---------------|-----------|
| Application Code | Django app, templates, static files | Git (GitHub) | Every commit |
| Database Schema | PostgreSQL structure | Django migrations in Git | Every schema change |
| Database Data | User data, content, preferences | Railway PostgreSQL automatic backups + manual exports | Daily (auto), Weekly (manual) |
| System Data | Fixtures, reference data | Git fixtures + data migrations | Every release |
| User-Generated Content | Avatars, documents, images | Cloudinary (external) | Real-time sync |
| Configuration | Environment variables | Railway dashboard + encrypted backup | On change |
| AI Configuration | Prompts, coaching styles | Database + Git fixtures | Every change |

### 1.2 Backup Philosophy: Defense-in-Depth

1. **Primary:** Git repository on GitHub (code, schema, fixtures)
2. **Secondary:** Railway PostgreSQL managed backups (production data)
3. **Tertiary:** Manual database exports to encrypted GitHub releases
4. **Quaternary:** Cloudinary CDN replication (media files)

### 1.3 Recovery Guarantees

| Scenario | Recovery Time | Data Loss |
|----------|--------------|-----------|
| Code rollback | < 5 minutes | None |
| Database restore (Railway) | < 30 minutes | Up to 24 hours |
| Full environment rebuild | < 2 hours | Up to 24 hours |
| Catastrophic failure | < 4 hours | Up to 1 week |

---

## 2. BACKUP PROCEDURES

### 2.1 Automatic Backups

**Railway PostgreSQL:**
- Automatic point-in-time recovery (PITR) enabled
- 7-day retention for instant recovery
- Daily snapshots retained for 30 days

**GitHub:**
- Every push creates a recoverable point
- Tags created for major releases
- Branch protection on `main`

### 2.2 Manual Backup Commands

```bash
# Create a backup tag before major changes
git tag -a "backup-YYYY-MM-DD-description" -m "Backup before [description]"
git push origin "backup-YYYY-MM-DD-description"

# Export database (if Railway CLI available)
railway run pg_dump $DATABASE_URL > backup_YYYY-MM-DD.sql

# Create encrypted backup archive
tar -czvf wlj-backup-YYYY-MM-DD.tar.gz backup_YYYY-MM-DD.sql
gpg --symmetric --cipher-algo AES256 wlj-backup-YYYY-MM-DD.tar.gz
```

---

## 3. RECOVERY PROCEDURES

### 3.1 Code Rollback

```bash
# List available backup points
git tag -l "backup-*"

# Rollback to specific tag
git checkout backup-YYYY-MM-DD-description

# Or revert specific commits
git revert HEAD~3..HEAD
```

### 3.2 Database Restore (Railway)

1. Go to Railway Dashboard > Project > Database
2. Click "Backups" tab
3. Select desired restore point
4. Click "Restore"
5. Wait for confirmation
6. Verify with `python manage.py check`

### 3.3 Full Environment Rebuild

```bash
# 1. Clone repository
git clone https://github.com/djenkins452/dbawholelifejourney.git
cd dbawholelifejourney

# 2. Set up environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# 3. Configure environment variables (from Railway backup)
cp .env.example .env
# Edit .env with production values

# 4. Run migrations
python manage.py migrate

# 5. Load initial data
python manage.py load_initial_data

# 6. Collect static files
python manage.py collectstatic --noinput

# 7. Verify
python manage.py check
python manage.py test
```

---

## 4. VERIFICATION

After any restore:

1. **Check database connectivity:** `python manage.py check`
2. **Run test suite:** `python manage.py test`
3. **Verify user login:** Test with known account
4. **Check module access:** Navigate through each app
5. **Verify AI features:** Test AI coaching (if consent given)

---

## 5. CONTACT & ESCALATION

**Primary Contact:** Danny Jenkins (dannyjenkins71@gmail.com)

**Resources:**
- Railway Status: https://status.railway.app/
- GitHub Status: https://www.githubstatus.com/
- Cloudinary Status: https://status.cloudinary.com/

---

## 6. BACKUP TAG HISTORY

| Tag | Date | Description | Command to Restore |
|-----|------|-------------|-------------------|
| `backup-2026-01-02-timezone-fix` | 2026-01-02 | After timezone IANA format fix - Dashboard working | `git checkout backup-2026-01-02-timezone-fix` |

### Most Recent Backup Command Used

```bash
# Created 2026-01-02 after fixing timezone error (US/Eastern → America/New_York)
git tag -a "backup-2026-01-02-timezone-fix" -m "Backup after timezone IANA format fix - Dashboard working"
git push origin "backup-2026-01-02-timezone-fix"
```

---

*For backup operation reports, see `docs/wlj_backup_report.md`*
*Last updated: 2026-01-02*
