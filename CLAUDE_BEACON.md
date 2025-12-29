# WLJ Financial Dashboard - Session Context

## What Was Built
A protected financial dashboard app (wlj) was created within the Beacon Innovations Django site (C:\django-beaconinnovation\beaconinnovation) to display Whole Life Journey business metrics for investors.

## Architecture
Beacon Innovations Site hosts company-specific apps. The wlj app is the first, and the pattern can be replicated for future companies (e.g., xyz_company app).

**Access:** https://beacon-innovation.com/wlj/ (login required)

**Credentials:**
- Username: danny
- Password: Set via Railway env var DJANGO_SUPERUSER_PASSWORD

## WLJ App Structure (C:\django-beaconinnovation\beaconinnovation\wlj\)

| File | Purpose |
|------|---------|
| models.py | ServiceCost, FinancialProjection, CodebaseMetric, Document, DocumentDownload |
| views.py | Login-protected views: dashboard, financials, costs, metrics, data_room, api_projections |
| urls.py | Routes under /wlj/ namespace |
| admin.py | Django admin for all models |
| templates/wlj/ | base.html, login.html, dashboard.html, financials.html, service_costs.html, codebase_metrics.html, data_room.html |

## Migrations

| Migration | Purpose |
|-----------|---------|
| 0001_initial.py | Creates all model tables |
| 0002_create_superuser.py | Creates superuser from env vars (uses make_password for historical model compatibility) |
| 0003_load_initial_data.py | Loads 15 financial projections (3 scenarios × 5 years), 15 service costs, 1 codebase metrics snapshot |

## Database
Production uses Railway PostgreSQL. Data is stored in:
- wlj_financialprojection (15 rows)
- wlj_servicecost (15 rows)
- wlj_codebasemetric (1 row)
- wlj_document / wlj_documentdownload (for investor data room)

## Railway Configuration

**Environment Variables:**
- DJANGO_SUPERUSER_USERNAME = danny
- DJANGO_SUPERUSER_EMAIL = dannyjenkins71@gmail.com
- DJANGO_SUPERUSER_PASSWORD = (your password)

**Key Settings Added:**
```python
CSRF_TRUSTED_ORIGINS = [
    'https://beacon-innovation.com',
    'https://beaconinnovation-production.up.railway.app',
]
```

**Note:** Railway uses Railpack which auto-detects Django and runs `python manage.py migrate && gunicorn beaconinnovation.wsgi:application`. The Procfile is ignored.

## URLs

| URL | View |
|-----|------|
| /wlj/login/ | Login page |
| /wlj/ | Dashboard (metrics overview) |
| /wlj/financials/ | 3-scenario projections with Chart.js |
| /wlj/costs/ | Service costs breakdown |
| /wlj/metrics/ | Codebase metrics history |
| /wlj/data-room/ | Document downloads for investors |
| /wlj/api/projections/ | JSON API for charts |
| /admin/wlj/ | Django admin for data management |

## WLJ Repo Changes (C:\dbawholelifejourney\)
Added to the WLJ repo (separate from Beacon site):
- docs/business/README.md - Business documentation hub
- docs/business/MASTER_PROMPT.md - Prompt for regenerating business docs
- docs/business/exports/*.csv - Financial data CSVs
- .claude/commands/regenerate-business-docs.md - Slash command
- .claude/commands/audit-codebase.md - Slash command

## Key Technical Decisions
- **Data migrations over fixtures** - More reliable for Railway deployment
- **make_password() in migrations** - set_password() not available on historical models from apps.get_model()
- **CSRF_TRUSTED_ORIGINS required** - Django 4+ requires explicit trusted origins for HTTPS
- **Login protection** - All views use @login_required(login_url='wlj:login')
- **TailwindCSS + Chart.js via CDN** - No build step needed

## Financial Data Loaded

**Scenarios:** Conservative, Base Case, Aggressive

**Years:** 2026-2030

**Key Projections (Base Case Y5):**
- 40,000 paying users
- $3.96M annual revenue
- $2.76M net profit
- 7 team members

---

*Use this context to continue development on either the Beacon Innovations site or the WLJ financial dashboard.*
