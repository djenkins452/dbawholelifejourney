# BACKUP.md - Whole Life Journey Disaster Recovery Playbook

**Document Version:** 1.0
**Last Updated:** 2025-12-28
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

| Metric | Target | Guarantee |
|--------|--------|-----------|
| **RPO** (Recovery Point Objective) | 24 hours | Data loss limited to 24 hours maximum |
| **RTO** (Recovery Time Objective) | 4 hours | Full system operational within 4 hours |
| **Code Recovery** | 0 minutes | Instant from GitHub |
| **Schema Recovery** | 15 minutes | Via Django migrations |
| **Data Recovery** | 2-4 hours | From Railway backup or encrypted export |

---

## 2. SOURCE OF TRUTH DEFINITION

### 2.1 Canonical Data (MUST BE PRESERVED)

| Data Type | Location | Criticality | Recovery Method |
|-----------|----------|-------------|-----------------|
| User accounts | PostgreSQL `users_user` | CRITICAL | Database restore |
| User preferences | PostgreSQL `users_userpreferences` | HIGH | Database restore |
| Terms acceptances | PostgreSQL `users_termsacceptance` | HIGH | Database restore |
| Journal entries | PostgreSQL `journal_journalentry` | CRITICAL | Database restore |
| Faith data (prayers, milestones, saved verses) | PostgreSQL `faith_*` | CRITICAL | Database restore |
| Health data (weight, fasting, heart rate, glucose) | PostgreSQL `health_*` | CRITICAL | Database restore |
| Life data (projects, tasks, events, inventory) | PostgreSQL `life_*` | CRITICAL | Database restore |
| Purpose data (goals, reflections, intentions) | PostgreSQL `purpose_*` | HIGH | Database restore |
| AI insights (cached) | PostgreSQL `ai_aiinsight` | MEDIUM | Regenerate from data |
| AI usage logs | PostgreSQL `ai_aiusagelog` | LOW | Database restore |
| Help conversations | PostgreSQL `help_*` | LOW | Database restore |

### 2.2 Derived Data (Can Be Regenerated)

| Data Type | Source | Regeneration Command |
|-----------|--------|---------------------|
| Static files | Source code | `python manage.py collectstatic --noinput` |
| Django cache | Runtime | Automatic cache rebuild |
| AI insights | User data + OpenAI API | Regenerated on-demand |
| Soft-deleted records | Database | Preserved in database with status='deleted' |

### 2.3 Reference Data (Loaded from Fixtures)

| Data Type | Fixture File | App |
|-----------|--------------|-----|
| Categories | `apps/core/fixtures/categories.json` | core |
| Encouragements | `apps/dashboard/fixtures/encouragements.json` | dashboard |
| Scripture verses | `apps/faith/fixtures/scripture.json` | faith |
| Journal prompts | `apps/journal/fixtures/prompts.json` | journal |
| Coaching styles | `apps/ai/fixtures/coaching_styles.json` | ai |
| AI prompt configs | `apps/ai/fixtures/ai_prompt_configs.json` | ai |
| Help topics | `apps/help/fixtures/help_topics.json` | help |
| Admin help topics | `apps/help/fixtures/admin_help_topics.json` | help |
| Help categories | `apps/help/fixtures/help_categories.json` | help |
| Help articles | `apps/help/fixtures/help_articles.json` | help |

---

## 3. BACKUP INVENTORY

### 3.1 Application Code

**Location:** GitHub repository `djenkins452/dbawholelifejourney`

**Structure:**
```
dbawholelifejourney/
├── apps/                    # Django applications
│   ├── admin_console/       # Admin management interface
│   ├── ai/                  # AI coaching and insights
│   ├── core/                # Base models, utilities
│   ├── dashboard/           # User dashboard
│   ├── faith/               # Faith module (prayers, scripture)
│   ├── health/              # Health tracking (weight, fasting, etc.)
│   ├── help/                # Context-aware help system
│   ├── journal/             # Journal entries
│   ├── life/                # Life management (tasks, projects)
│   ├── purpose/             # Goals and reflections
│   └── users/               # Authentication, preferences
├── config/                  # Django settings
├── static/                  # Static assets
├── templates/               # HTML templates
├── manage.py                # Django management
├── requirements.txt         # Python dependencies
├── Procfile                 # Railway process definition
├── railway.json             # Railway configuration
├── CLAUDE.md                # Project instructions
└── BACKUP.md                # This file
```

### 3.2 Configuration Files

| File | Purpose | Backup Location |
|------|---------|-----------------|
| `config/settings.py` | Django configuration | Git |
| `requirements.txt` | Python dependencies | Git |
| `Procfile` | Railway process definition | Git |
| `railway.json` | Railway build/deploy config | Git |
| `.env` (local only) | Local environment variables | NOT backed up (regenerate from template) |

### 3.3 Environment Variables Strategy

**Production (Railway):**
- Stored in Railway dashboard under project variables
- Backup strategy: Export via Railway CLI or manual documentation

**Required Environment Variables:**
```
SECRET_KEY              # Django secret key (CRITICAL)
DATABASE_URL            # PostgreSQL connection string
DEBUG                   # False in production
OPENAI_API_KEY          # For AI features
OPENAI_MODEL            # AI model selection
CLOUDINARY_CLOUD_NAME   # Media storage
CLOUDINARY_API_KEY      # Media storage auth
CLOUDINARY_API_SECRET   # Media storage auth
RESEND_API_KEY          # Email service
DEFAULT_FROM_EMAIL      # Email sender address
BIBLE_API_KEY           # Scripture API
GOOGLE_CALENDAR_*       # Calendar integration (optional)
```

**Secret Handling:**
- NEVER commit secrets to Git
- Secrets regenerated during recovery, not restored from backup
- Document secret purposes, not values

### 3.4 Database Schema

**Schema files:** All migrations in `apps/*/migrations/`

**Critical migration files:**
- `apps/users/migrations/0001_initial.py` - User model
- `apps/core/migrations/0001_initial.py` - Base models
- `apps/journal/migrations/0001_initial.py` - Journal models
- `apps/faith/migrations/0001_initial.py` - Faith models
- `apps/health/migrations/0001_initial.py` - Health models
- `apps/life/migrations/0001_initial.py` - Life models
- `apps/purpose/migrations/0001_initial.py` - Purpose models
- `apps/ai/migrations/0001_initial.py` - AI models
- `apps/help/migrations/0001_initial.py` - Help models

**Data migrations (one-time operations):**
- `apps/journal/migrations/0002_import_chatgpt_journal.py` - ChatGPT import
- `apps/journal/migrations/0003_load_journal_prompts.py` - Load prompts
- `apps/faith/migrations/0003_migrate_existing_verses_to_danny.py` - User verse migration

### 3.5 Database Data

**PostgreSQL Tables by App:**

**users app:**
- `users_user` - User accounts
- `users_userpreferences` - User settings
- `users_termsacceptance` - Legal compliance

**core app:**
- `core_tag` - User-defined tags
- `core_category` - System categories
- `core_siteconfiguration` - Site settings
- `core_theme` - Theme definitions
- `core_choicecategory` - Dynamic choice categories
- `core_choiceoption` - Dynamic choice options
- `core_testrun` - Test history (dev)
- `core_testrundetail` - Test details (dev)

**journal app:**
- `journal_journalentry` - User journal entries (CRITICAL)
- `journal_journalprompt` - Writing prompts
- `journal_entrylink` - Cross-entry links

**faith app:**
- `faith_scriptureverse` - Curated scripture
- `faith_dailyverse` - Daily verse assignments
- `faith_prayerrequest` - User prayers (CRITICAL)
- `faith_savedverse` - User saved verses (CRITICAL)
- `faith_faithmilestone` - User milestones (CRITICAL)

**health app:**
- `health_weightentry` - Weight records (CRITICAL)
- `health_fastingwindow` - Fasting records (CRITICAL)
- `health_heartrateentry` - Heart rate records (CRITICAL)
- `health_glucoseentry` - Glucose records (CRITICAL)
- `health_exercise` - Exercise library
- `health_workoutsession` - Workout records
- `health_workoutexercise` - Workout details
- `health_exerciseset` - Set details
- `health_cardiodetails` - Cardio details
- `health_personalrecord` - PR tracking
- `health_workouttemplate` - Saved templates
- `health_templateexercise` - Template details

**life app:**
- `life_project` - User projects (CRITICAL)
- `life_task` - User tasks (CRITICAL)
- `life_lifeevent` - Calendar events
- `life_inventoryitem` - Home inventory
- `life_inventoryphoto` - Inventory photos
- `life_maintenancelog` - Maintenance records
- `life_pet` - Pet profiles
- `life_petrecord` - Pet records
- `life_recipe` - Saved recipes
- `life_document` - Uploaded documents
- `life_googlecalendarcredential` - OAuth tokens

**purpose app:**
- `purpose_lifedomain` - Life domains
- `purpose_reflectionprompt` - Reflection prompts
- `purpose_annualdirection` - Year focus (CRITICAL)
- `purpose_lifegoal` - User goals (CRITICAL)
- `purpose_changeintention` - User intentions
- `purpose_reflection` - User reflections
- `purpose_reflectionresponse` - Reflection responses
- `purpose_planningaction` - Planning items

**ai app:**
- `ai_coachingstyle` - AI coaching styles
- `ai_aiinsight` - Cached AI insights
- `ai_aipromptconfig` - AI prompt configs
- `ai_aiusagelog` - API usage logs

**help app:**
- `help_helptopic` - User help topics
- `help_adminhelptopic` - Admin help topics
- `help_helpcategory` - Help categories
- `help_helparticle` - Help articles
- `help_helpconversation` - Chat sessions
- `help_helpmessage` - Chat messages

### 3.6 User-Generated Content

**Storage:** Cloudinary CDN

**Content types:**
- User avatars: `avatars/user_<id>/avatar.<ext>`
- Project images: `life/projects/`
- Inventory photos: `life/inventory/`
- Pet photos: `life/pets/`
- Recipe images: `life/recipes/`
- Documents: `life/documents/<year>/<month>/`
- Site branding: `site/`

**Cloudinary backup:**
- Cloudinary maintains its own replication
- Media URLs stored in PostgreSQL
- Recovery: Restore database, media URLs remain valid

### 3.7 AI Artifacts

**Database-stored AI configuration:**
- `ai_aipromptconfig` - 10 prompt types with instructions
- `ai_coachingstyle` - 7 coaching personalities
- `ai_aiinsight` - Cached user insights (regenerable)

**Fixture backups:**
- `apps/ai/fixtures/ai_prompt_configs.json`
- `apps/ai/fixtures/coaching_styles.json`

---

## 4. GITHUB-BASED BACKUP STRATEGY

### 4.1 Branching Model for Safety

```
main (protected)
├── Production code
├── All migrations committed
├── All fixtures committed
└── Tagged releases

feature/* (development)
├── New features
├── Bug fixes
└── Merged to main via PR

backup/* (backup artifacts)
├── Database exports
└── Encrypted snapshots
```

**Branch protection rules for `main`:**
- Require pull request before merging
- All tests must pass
- No force push allowed

### 4.2 Immutable Backup Tags

**Tag format:** `backup-YYYY-MM-DD-HH-MM`

**Creating backup tags:**
```bash
# Tag current state with timestamp
git tag -a "backup-$(date +%Y-%m-%d-%H-%M)" -m "Automated backup checkpoint"
git push origin "backup-$(date +%Y-%m-%d-%H-%M)"
```

**Release tags:** `v1.x.x`

### 4.3 Release Snapshots

**GitHub Releases contain:**
1. Tagged source code
2. CHANGELOG of changes since last release
3. Database schema snapshot (migration state)
4. Encrypted database export (attached as asset)

**Creating a release:**
1. Tag the commit: `git tag -a v1.x.x -m "Release v1.x.x"`
2. Push tag: `git push origin v1.x.x`
3. Create GitHub release via web UI
4. Attach encrypted database backup

### 4.4 Encrypted Backup Artifacts

**Encryption method:** GPG symmetric encryption

**Creating encrypted backup:**
```bash
# Export database (locally with DATABASE_URL tunnel)
pg_dump $DATABASE_URL > backup.sql

# Encrypt
gpg --symmetric --cipher-algo AES256 backup.sql

# Result: backup.sql.gpg (attach to GitHub release)

# Delete unencrypted file
rm backup.sql
```

**Decryption:**
```bash
gpg --decrypt backup.sql.gpg > backup.sql
```

### 4.5 Off-Branch Cold Storage

**Strategy:** Orphan branch for encrypted database backups

```bash
# Create orphan branch (no history)
git checkout --orphan backup-cold-storage
git rm -rf .

# Add encrypted backup
cp /path/to/backup.sql.gpg ./db-backup-$(date +%Y-%m-%d).sql.gpg
git add .
git commit -m "Database backup $(date +%Y-%m-%d)"
git push origin backup-cold-storage
```

### 4.6 GitHub Actions for Automated Backups

**File:** `.github/workflows/backup.yml`

```yaml
name: Scheduled Backup Verification

on:
  schedule:
    # Weekly on Sunday at 2 AM UTC
    - cron: '0 2 * * 0'
  workflow_dispatch:

jobs:
  verify-backup-readiness:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Verify migrations
        run: python manage.py makemigrations --check --dry-run

      - name: Verify fixtures loadable
        run: python manage.py check

      - name: Create backup tag
        run: |
          git tag -a "backup-$(date +%Y-%m-%d)" -m "Weekly backup checkpoint"
          git push origin "backup-$(date +%Y-%m-%d)"
```

---

## 5. AUTOMATED BACKUP EXECUTION

### 5.1 Trigger Conditions

| Trigger | Action | Frequency |
|---------|--------|-----------|
| Git push to main | Tag creation | Every push |
| Sunday 2 AM UTC | Full backup verification | Weekly |
| Before major deployment | Manual backup tag | On-demand |
| Database schema change | Migration commit + tag | On change |

### 5.2 Backup Cadence

| Backup Type | Frequency | Retention |
|-------------|-----------|-----------|
| Git commits | Continuous | Indefinite |
| Backup tags | Weekly | Indefinite |
| Railway PostgreSQL | Daily (automatic) | 7 days |
| Encrypted exports | Monthly | 12 months |
| GitHub releases | Per version | Indefinite |

### 5.3 Validation Steps After Backup

**Post-backup checklist (Claude executes):**

1. **Verify tag exists:**
   ```bash
   git tag -l | grep "backup-$(date +%Y-%m-%d)"
   ```

2. **Verify tag pushed:**
   ```bash
   git ls-remote --tags origin | grep "backup-$(date +%Y-%m-%d)"
   ```

3. **Verify migrations consistent:**
   ```bash
   python manage.py makemigrations --check --dry-run
   ```

4. **Verify fixtures loadable:**
   ```bash
   python manage.py loaddata --dry-run categories
   ```

### 5.4 Failure Handling

**If backup verification fails:**

1. Log failure with specific error
2. Attempt retry (max 3 attempts)
3. If all retries fail, create incident tag: `incident-backup-failed-YYYY-MM-DD`
4. Continue operations (backup failure does not block deployment)
5. Next successful backup resolves incident

### 5.5 Backup Success Confirmation

**Success criteria:**
- Backup tag created and pushed
- All migrations in committed state
- No pending fixture changes
- Previous backup less than 7 days old

---

## 6. DATABASE BACKUP & RESTORE STRATEGY

### 6.1 Schema-First Restore

**Restore order (mandatory):**

1. Create empty PostgreSQL database
2. Apply Django migrations (creates schema)
3. Load fixtures (reference data)
4. Restore user data (from backup)
5. Verify foreign key integrity

**Schema restore commands:**
```bash
# Apply all migrations
python manage.py migrate --noinput

# Load reference data
python manage.py load_initial_data
```

### 6.2 Data Restore Ordering

**Table dependency order (respecting foreign keys):**

**Phase 1: Independent tables**
- `auth_group`
- `auth_permission`
- `django_content_type`
- `django_site`
- `core_category`
- `core_siteconfiguration`
- `core_theme`
- `core_choicecategory`
- `ai_coachingstyle`
- `ai_aipromptconfig`
- `purpose_lifedomain`
- `purpose_reflectionprompt`
- `health_exercise`
- `help_helpcategory`

**Phase 2: User-dependent tables**
- `users_user`
- `users_userpreferences`
- `users_termsacceptance`
- `core_tag`
- `core_choiceoption`

**Phase 3: Content tables**
- `journal_journalprompt`
- `journal_journalentry`
- `journal_entrylink`
- `faith_scriptureverse`
- `faith_dailyverse`
- `faith_prayerrequest`
- `faith_savedverse`
- `faith_faithmilestone`
- `health_*` (all health tables)
- `life_*` (all life tables)
- `purpose_*` (all purpose tables)
- `ai_aiinsight`
- `ai_aiusagelog`
- `help_*` (all help tables)

### 6.3 Transaction Safety

**All data restores wrapped in transactions:**

```sql
BEGIN;
-- Restore operations here
-- If any error occurs, entire restore is rolled back
COMMIT;
```

**Django management command pattern:**
```python
from django.db import transaction

with transaction.atomic():
    # All restore operations
    pass
```

### 6.4 Idempotent Restore Behavior

**All fixture loads use `update_or_create` pattern:**
- Running load_initial_data multiple times is safe
- Existing records updated, not duplicated
- Primary keys preserved where possible

### 6.5 Corruption Detection

**Pre-restore checks:**

1. **Verify backup file integrity:**
   ```bash
   # Check GPG signature/decryption
   gpg --verify backup.sql.gpg
   ```

2. **Verify SQL syntax:**
   ```bash
   head -1000 backup.sql | psql --echo-errors
   ```

3. **Verify table counts post-restore:**
   ```sql
   SELECT
     (SELECT COUNT(*) FROM users_user) as users,
     (SELECT COUNT(*) FROM journal_journalentry) as entries,
     (SELECT COUNT(*) FROM faith_prayerrequest) as prayers;
   ```

### 6.6 Rollback Safety Nets

**Pre-restore snapshot:**
```bash
# Before any restore operation
pg_dump $DATABASE_URL > pre_restore_snapshot.sql
```

**Quick rollback:**
```bash
# If restore fails or corrupts data
psql $DATABASE_URL < pre_restore_snapshot.sql
```

---

## 7. ENVIRONMENT RECONSTRUCTION

### 7.1 Rebuilding Environment from Scratch

**Complete environment rebuild procedure:**

**Step 1: Clone repository**
```bash
git clone https://github.com/djenkins452/dbawholelifejourney.git
cd dbawholelifejourney
```

**Step 2: Check out specific version**
```bash
# Use latest backup tag
git checkout backup-YYYY-MM-DD
# Or specific release
git checkout v1.x.x
```

**Step 3: Create Railway project**
- Create new Railway project via dashboard
- Add PostgreSQL plugin
- Note DATABASE_URL from plugin

**Step 4: Configure environment variables**
Set in Railway dashboard:
```
SECRET_KEY=<generate new Django secret key>
DATABASE_URL=<from PostgreSQL plugin>
DEBUG=False
OPENAI_API_KEY=<from OpenAI dashboard>
OPENAI_MODEL=gpt-4o-mini
CLOUDINARY_CLOUD_NAME=<from Cloudinary>
CLOUDINARY_API_KEY=<from Cloudinary>
CLOUDINARY_API_SECRET=<from Cloudinary>
RESEND_API_KEY=<from Resend>
DEFAULT_FROM_EMAIL=noreply@wholelifejourney.com
BIBLE_API_KEY=<existing or regenerate>
```

**Step 5: Deploy**
Railway auto-deploys on connection to GitHub repo.

**Step 6: Verify deployment**
```bash
# Check application health
curl https://your-app.up.railway.app/
```

**Step 7: Restore database (if needed)**
```bash
# Decrypt backup
gpg --decrypt backup.sql.gpg > backup.sql

# Restore via Railway CLI or psql tunnel
psql $DATABASE_URL < backup.sql
```

### 7.2 Rehydrating Secrets Safely

**Secret regeneration procedure:**

| Secret | Regeneration Method |
|--------|---------------------|
| SECRET_KEY | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| OPENAI_API_KEY | Generate new key in OpenAI dashboard |
| CLOUDINARY_* | Retrieve from Cloudinary dashboard |
| RESEND_API_KEY | Generate new key in Resend dashboard |
| BIBLE_API_KEY | Retrieve from API.Bible dashboard |
| GOOGLE_CALENDAR_* | Regenerate OAuth credentials in Google Cloud Console |

**Post-secret-rotation:**
- All active user sessions invalidated (SECRET_KEY change)
- Users must re-login
- OAuth tokens must be re-authorized

### 7.3 Validating Environment Parity

**Validation checklist:**

1. **Version match:**
   ```bash
   git rev-parse HEAD  # Compare with production
   ```

2. **Migration state:**
   ```bash
   python manage.py showmigrations | grep "\[ \]"
   # Should return nothing (all applied)
   ```

3. **Fixture data loaded:**
   ```bash
   python manage.py shell -c "from apps.ai.models import CoachingStyle; print(CoachingStyle.objects.count())"
   # Should return 7
   ```

4. **External services connected:**
   ```bash
   python manage.py check
   # Should return no errors
   ```

### 7.4 Detecting Environment Drift

**Drift detection commands:**

```bash
# Check for uncommitted migration changes
python manage.py makemigrations --check --dry-run

# Check fixture sync
python manage.py dumpdata ai.coachingstyle --indent 2 > /tmp/current.json
diff /tmp/current.json apps/ai/fixtures/coaching_styles.json
```

---

## 8. ROLLBACK & DISASTER RECOVERY PLAYBOOK

### 8.1 Code Rollback

**Scenario:** Bad deployment, need to revert code

**Procedure:**

1. **Identify target version:**
   ```bash
   git log --oneline -20
   # Find last known good commit
   ```

2. **Create rollback commit:**
   ```bash
   git checkout main
   git revert HEAD --no-edit
   git push origin main
   ```

3. **Or deploy specific tag:**
   ```bash
   git checkout v1.x.x
   git push -f origin main  # Force push to main (use with caution)
   ```

4. **Verify deployment:**
   - Railway auto-redeploys on push
   - Monitor deployment logs

### 8.2 Database Rollback

**Scenario:** Bad migration or data corruption

**Procedure:**

1. **Assess damage:**
   ```sql
   -- Check for missing or corrupted data
   SELECT COUNT(*) FROM users_user;
   SELECT COUNT(*) FROM journal_journalentry;
   ```

2. **Stop the application (if needed):**
   - Railway dashboard: Scale to 0 instances

3. **Restore from Railway backup:**
   - Railway dashboard > Database > Backups
   - Select backup point
   - Click "Restore"

4. **Or restore from encrypted export:**
   ```bash
   gpg --decrypt backup.sql.gpg > backup.sql
   psql $DATABASE_URL < backup.sql
   ```

5. **Verify data integrity:**
   ```sql
   SELECT
     (SELECT COUNT(*) FROM users_user) as users,
     (SELECT COUNT(*) FROM journal_journalentry) as entries;
   ```

6. **Restart application:**
   - Railway dashboard: Scale to 1 instance

### 8.3 Partial Failure Recovery

**Scenario:** Some tables corrupted, others intact

**Procedure:**

1. **Identify affected tables:**
   ```sql
   -- Check for orphaned records
   SELECT COUNT(*) FROM journal_journalentry je
   LEFT JOIN users_user u ON je.user_id = u.id
   WHERE u.id IS NULL;
   ```

2. **Export intact tables:**
   ```bash
   pg_dump $DATABASE_URL -t users_user -t users_userpreferences > intact.sql
   ```

3. **Restore affected tables only:**
   ```bash
   # From backup
   pg_restore -t journal_journalentry backup.dump
   ```

4. **Verify referential integrity:**
   ```sql
   -- Django check for FK violations
   python manage.py check --database default
   ```

### 8.4 Full System Restore

**Scenario:** Complete infrastructure loss

**Procedure:**

1. **Clone from GitHub:**
   ```bash
   git clone https://github.com/djenkins452/dbawholelifejourney.git
   cd dbawholelifejourney
   git checkout main
   ```

2. **Create new Railway project:**
   - Create project via Railway dashboard
   - Add PostgreSQL plugin
   - Connect GitHub repository

3. **Set environment variables:**
   - Set all required variables in Railway dashboard
   - Regenerate secrets as needed

4. **Wait for initial deployment:**
   - Railway runs: migrate, load_initial_data, collectstatic

5. **Restore database:**
   ```bash
   # Get encrypted backup from GitHub release
   gh release download v1.x.x -p "*.sql.gpg"

   # Decrypt
   gpg --decrypt backup.sql.gpg > backup.sql

   # Restore (via Railway CLI or tunnel)
   psql $DATABASE_URL < backup.sql
   ```

6. **Verify restoration:**
   ```bash
   curl https://new-app.up.railway.app/
   # Verify login, data visibility
   ```

7. **Update DNS (if custom domain):**
   - Point wholelifejourney.com to new Railway app
   - Update Railway custom domain settings

### 8.5 Point-in-Time Recovery

**Scenario:** Need data from specific point in time

**Procedure:**

1. **Identify target timestamp:**
   - Review git history for relevant commits
   - Check Railway backup timestamps

2. **Create isolated recovery environment:**
   ```bash
   # Clone to separate directory
   git clone https://github.com/djenkins452/dbawholelifejourney.git wlj-recovery
   cd wlj-recovery
   git checkout backup-YYYY-MM-DD
   ```

3. **Create temporary database:**
   - Create new Railway PostgreSQL instance
   - Or use local PostgreSQL

4. **Restore to target point:**
   ```bash
   psql $TEMP_DATABASE_URL < backup-YYYY-MM-DD.sql
   ```

5. **Extract needed data:**
   ```sql
   -- Export specific records
   COPY (SELECT * FROM journal_journalentry WHERE entry_date = '2025-12-25')
   TO '/tmp/christmas_entries.csv' CSV HEADER;
   ```

6. **Import to production:**
   ```sql
   -- Insert recovered records
   COPY journal_journalentry FROM '/tmp/christmas_entries.csv' CSV HEADER;
   ```

7. **Clean up:**
   - Delete temporary database
   - Delete recovery directory

---

## 9. VERIFICATION & INTEGRITY CHECKS

### 9.1 Hashing Strategy

**File integrity verification:**
```bash
# Generate checksums for critical files
sha256sum apps/*/migrations/*.py > migrations.sha256
sha256sum apps/*/fixtures/*.json > fixtures.sha256

# Verify later
sha256sum -c migrations.sha256
sha256sum -c fixtures.sha256
```

**Database backup integrity:**
```bash
# Include checksum with encrypted backup
sha256sum backup.sql > backup.sql.sha256
gpg --symmetric backup.sql
gpg --symmetric backup.sql.sha256
```

### 9.2 Consistency Checks

**Pre-restore consistency check:**
```bash
# Verify migration graph is valid
python manage.py migrate --check

# Verify no circular dependencies
python manage.py check --deploy
```

**Post-restore consistency check:**
```bash
# Verify all migrations applied
python manage.py showmigrations | grep -v "\[X\]"
# Should return only section headers, no unapplied migrations

# Verify foreign keys
python manage.py check --database default
```

### 9.3 Smoke Tests

**Automated smoke test script:**
```python
# smoke_test.py
import requests
import sys

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

tests = [
    ("/", 200),                           # Landing page
    ("/account/login/", 200),             # Login page
    ("/admin/", 302),                     # Admin redirect to login
]

failed = 0
for path, expected in tests:
    try:
        resp = requests.get(f"{BASE_URL}{path}", allow_redirects=False, timeout=10)
        if resp.status_code != expected:
            print(f"FAIL: {path} returned {resp.status_code}, expected {expected}")
            failed += 1
        else:
            print(f"PASS: {path} returned {resp.status_code}")
    except Exception as e:
        print(f"FAIL: {path} error: {e}")
        failed += 1

sys.exit(1 if failed else 0)
```

**Run smoke tests:**
```bash
python smoke_test.py https://wholelifejourney.com
```

### 9.4 Post-Restore Validation Gates

**Validation gate checklist (ALL must pass):**

| Check | Command | Expected |
|-------|---------|----------|
| Django system check | `python manage.py check --deploy` | No errors |
| All migrations applied | `python manage.py showmigrations --plan` | All [X] |
| User count matches | `SELECT COUNT(*) FROM users_user` | > 0 |
| Reference data loaded | `SELECT COUNT(*) FROM ai_coachingstyle` | 7 |
| Site accessible | `curl -I https://app.url/` | 200 OK |
| Login works | Manual test | Success |

**If any gate fails:**
- HALT restore operation
- Do not mark restore as complete
- Investigate and resolve before proceeding

### 9.5 Conditions That Halt Recovery

**STOP recovery if:**
- Database connection fails after 3 retries
- Migration errors (schema mismatch)
- Foreign key violations detected
- User count is 0 after restore
- Django check returns errors
- Smoke tests fail

**Resume recovery only after:**
- Root cause identified
- Corrective action documented
- Fresh attempt from clean state

---

## 10. FAILURE MODES & AUTOMATED RESPONSES

### 10.1 Known Failure Scenarios

| Scenario | Detection Method | Automated Response |
|----------|------------------|-------------------|
| Railway PostgreSQL unavailable | Connection timeout | Retry 3x, then alert |
| Corrupted migration | `migrate --check` fails | Halt, preserve state |
| Missing fixture file | `loaddata` fails | Skip, continue with warnings |
| Cloudinary unavailable | Media 404s | Serve placeholder, log |
| OpenAI API unavailable | API timeout | Disable AI features, log |
| GitHub unreachable | Clone fails | Use local cached repo |
| Encryption key lost | Decrypt fails | Recovery requires manual intervention |

### 10.2 Detection Methods

**Health check endpoint (to implement):**
```python
# apps/core/views.py
def health_check(request):
    checks = {
        'database': check_database(),
        'cache': check_cache(),
        'static_files': check_static(),
    }
    status = 'healthy' if all(checks.values()) else 'degraded'
    return JsonResponse({'status': status, 'checks': checks})
```

**Database connectivity check:**
```python
def check_database():
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        return True
    except:
        return False
```

### 10.3 Automatic Containment Actions

**On database failure:**
1. Log error with timestamp
2. Retry connection 3 times with exponential backoff
3. If persistent, mark application as degraded
4. Return 503 for database-dependent routes

**On backup failure:**
1. Log failure reason
2. Create incident tag in git
3. Alert via commit message
4. Continue normal operations
5. Retry on next scheduled backup

### 10.4 Escalation Logic

**Escalation path (automated, no human steps):**

1. **Level 1:** Retry operation
2. **Level 2:** Use fallback mechanism
3. **Level 3:** Disable affected feature
4. **Level 4:** Enter maintenance mode
5. **Level 5:** Halt and preserve state

**Example: AI service failure escalation:**
```
L1: Retry OpenAI API call (3x)
L2: Return cached insight if available
L3: Show "AI insights temporarily unavailable"
L4: Disable AI feature flag for all users
L5: (Never reached for AI - non-critical service)
```

---

## 11. SECURITY & COMPLIANCE

### 11.1 Encryption at Rest

| Data Type | Encryption | Key Management |
|-----------|------------|----------------|
| PostgreSQL data | Railway managed encryption | Railway infrastructure |
| Backup exports | GPG AES-256 | Manual key management |
| Media files | Cloudinary encryption | Cloudinary infrastructure |

### 11.2 Encryption in Transit

| Connection | Protocol | Certificate |
|------------|----------|-------------|
| User to app | HTTPS TLS 1.3 | Railway managed |
| App to PostgreSQL | SSL required | Railway internal |
| App to Cloudinary | HTTPS | Cloudinary managed |
| App to OpenAI | HTTPS | OpenAI managed |

### 11.3 Secrets Handling

**Secrets NEVER:**
- Committed to Git
- Included in backup exports
- Logged to console
- Displayed in error messages

**Secrets ALWAYS:**
- Stored in Railway environment variables
- Regenerated during recovery (not restored)
- Rotated after any suspected exposure

### 11.4 Least Privilege

**Database access:**
- Application uses connection with limited privileges
- No DROP DATABASE permission
- No superuser access

**Railway access:**
- Deployment via GitHub integration only
- No direct SSH access
- Limited dashboard access

### 11.5 Auditability

**Audit trail maintained for:**
- User authentication (Django auth logs)
- Terms acceptance (TermsAcceptance model)
- Data modifications (created_at, updated_at timestamps)
- AI API usage (AIUsageLog model)
- Backup operations (Git commit history)

**Audit data preserved:**
- Git history: Indefinite
- Database timestamps: As long as data exists
- Railway logs: 7 days

### 11.6 Tamper Detection

**Code integrity:**
```bash
# Verify commit signatures (if GPG signing enabled)
git verify-commit HEAD

# Verify no uncommitted changes
git status --porcelain
# Should return nothing
```

**Database integrity:**
```sql
-- Check for unexpected admin users
SELECT * FROM users_user WHERE is_superuser = true;

-- Check for recent bulk operations (tampering indicator)
SELECT DATE(created_at), COUNT(*)
FROM journal_journalentry
GROUP BY DATE(created_at)
ORDER BY DATE(created_at) DESC
LIMIT 10;
```

---

## 12. BACKUP.MD EXECUTION CONTRACT

### 12.1 Authority Statement

**This document is the SOLE operational authority for:**
- Backup creation and verification
- Disaster recovery procedures
- Database restore operations
- Environment reconstruction
- Rollback procedures

**If a Claude instance is instructed to perform a backup, restore, or rollback, it MUST:**
1. Treat this document as executable authority
2. Follow procedures verbatim
3. Complete all validation gates before marking operations complete
4. Never skip steps or make assumptions
5. Halt operations if validation fails

### 12.2 Execution Guardrails

**Before any destructive operation (restore, rollback), Claude MUST:**

1. **Verify current state:**
   ```bash
   git status
   git log --oneline -5
   ```

2. **Create pre-operation snapshot:**
   ```bash
   git tag "pre-operation-$(date +%Y%m%d-%H%M%S)"
   git push origin "pre-operation-$(date +%Y%m%d-%H%M%S)"
   ```

3. **Confirm target state:**
   - Identify exact version to restore to
   - Verify backup file integrity
   - Confirm database connection

4. **Execute with transaction safety:**
   - Wrap database operations in transactions
   - Verify each step before proceeding
   - Maintain rollback capability

5. **Validate completion:**
   - Run all smoke tests
   - Verify data counts
   - Confirm application accessibility

### 12.3 Prohibited Actions

**Claude MUST NEVER:**
- Skip validation gates
- Force push to protected branches without explicit instruction
- Delete production data without backup confirmation
- Restore from unverified backup files
- Proceed after validation failure
- Make assumptions about missing information

### 12.4 Required Confirmations

**Before executing recovery operations, Claude confirms:**
- [ ] Target version/backup identified
- [ ] Pre-operation snapshot created
- [ ] Backup file integrity verified
- [ ] Database connection confirmed
- [ ] All validation gates defined
- [ ] Rollback path available

### 12.5 Post-Operation Requirements

**After any backup or recovery operation, Claude MUST:**

1. **Document the operation:**
   - Record start time, end time
   - List all steps executed
   - Note any warnings or issues

2. **Verify success:**
   - Run all smoke tests
   - Confirm data integrity
   - Test critical user flows

3. **Update this document if needed:**
   - Add new failure scenarios encountered
   - Improve procedures based on experience
   - Update version history

---

## APPENDIX A: QUICK REFERENCE COMMANDS

### Backup Commands
```bash
# Create backup tag
git tag -a "backup-$(date +%Y-%m-%d)" -m "Backup checkpoint"
git push origin "backup-$(date +%Y-%m-%d)"

# Export database (requires tunnel/local access)
pg_dump $DATABASE_URL > backup-$(date +%Y-%m-%d).sql

# Encrypt backup
gpg --symmetric --cipher-algo AES256 backup-$(date +%Y-%m-%d).sql

# Verify migrations
python manage.py migrate --check
```

### Recovery Commands
```bash
# Clone from GitHub
git clone https://github.com/djenkins452/dbawholelifejourney.git

# Checkout specific backup
git checkout backup-YYYY-MM-DD

# Apply migrations
python manage.py migrate --noinput

# Load reference data
python manage.py load_initial_data

# Restore database
gpg --decrypt backup.sql.gpg > backup.sql
psql $DATABASE_URL < backup.sql
```

### Verification Commands
```bash
# Check Django system
python manage.py check --deploy

# Check migrations
python manage.py showmigrations

# Check data counts
python manage.py shell -c "
from apps.users.models import User
from apps.journal.models import JournalEntry
print(f'Users: {User.objects.count()}')
print(f'Journal entries: {JournalEntry.objects.count()}')
"
```

---

## APPENDIX B: MODEL REFERENCE

### User Data Models (CRITICAL)
- `users.User` - User accounts
- `users.UserPreferences` - User settings
- `journal.JournalEntry` - Journal entries
- `faith.PrayerRequest` - Prayer requests
- `faith.SavedVerse` - Saved scripture
- `faith.FaithMilestone` - Faith milestones
- `health.WeightEntry` - Weight records
- `health.FastingWindow` - Fasting records
- `health.HeartRateEntry` - Heart rate records
- `health.GlucoseEntry` - Glucose records
- `health.WorkoutSession` - Workouts
- `life.Project` - Projects
- `life.Task` - Tasks
- `life.LifeEvent` - Calendar events
- `purpose.AnnualDirection` - Year focus
- `purpose.LifeGoal` - Goals
- `purpose.Reflection` - Reflections

### System Data Models
- `core.Category` - Journal categories
- `core.Theme` - UI themes
- `ai.CoachingStyle` - AI personalities
- `ai.AIPromptConfig` - AI prompts
- `dashboard.DailyEncouragement` - Encouragements
- `help.HelpTopic` - Help content
- `help.HelpArticle` - Help articles

---

## APPENDIX C: FIXTURE FILE MANIFEST

| Fixture | Path | Records |
|---------|------|---------|
| categories | `apps/core/fixtures/categories.json` | ~8 |
| encouragements | `apps/dashboard/fixtures/encouragements.json` | ~20 |
| scripture | `apps/faith/fixtures/scripture.json` | ~50 |
| prompts | `apps/journal/fixtures/prompts.json` | 20 |
| coaching_styles | `apps/ai/fixtures/coaching_styles.json` | 7 |
| ai_prompt_configs | `apps/ai/fixtures/ai_prompt_configs.json` | 10 |
| help_topics | `apps/help/fixtures/help_topics.json` | varies |
| admin_help_topics | `apps/help/fixtures/admin_help_topics.json` | varies |
| help_categories | `apps/help/fixtures/help_categories.json` | varies |
| help_articles | `apps/help/fixtures/help_articles.json` | varies |

---

## VERSION HISTORY

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-28 | Initial comprehensive backup playbook |

---

*END OF BACKUP.MD*
