# Medical Ingestion - Repository Map

*Generated during Step 0 (Repo Discovery) — 2026-02-12*

---

## 1. Medical App Location

**Does not exist yet.** No `apps/medical/` directory. Will be created as a new Django app.

Existing health-related models live in `apps/health/models.py` (blood pressure, glucose, blood oxygen, body temperature, weight, heart rate, sleep, steps, water). These are individual vital tracking entries, **not** structured lab results. The new medical module will be separate.

---

## 2. Organize → Documents Feature

**Location:** `apps/life/models.py` (line 938+)

**Model:** `Document` (extends `UserOwnedModel`)
- Categories include `'medical'` → `'Medical Records'`
- File stored via `FileField` with `get_document_storage()` (Cloudinary in prod, filesystem in dev)
- Fields: `title`, `description`, `category`, `file`, `file_type`, `file_size`, `document_date`, `expiration_date`, `tags` (JSON), `notes`, `is_archived`
- Related items: `related_inventory_item`, `related_pet`

**Views:** `apps/life/views.py`
- `DocumentListView`, `DocumentDetailView`, `DocumentCreateView`, `DocumentUpdateView`, `DocumentDeleteView`, `DocumentDownloadView`, `DocumentViewInlineView`

**URLs:** `/life/documents/` (namespace: `life`)
- List: `/life/documents/`
- Create: `/life/documents/new/`
- Detail: `/life/documents/<id>/`
- Download: `/life/documents/<id>/download/`

**Templates:** `templates/life/document_*.html`

---

## 3. User Model & Profile

**AUTH_USER_MODEL:** `"users.User"` (in `config/settings.py` line 522)

**Custom User:** `apps/users/models.py`
- `User(AbstractBaseUser, PermissionsMixin)` — email-based auth, no username
- Fields: `email` (unique), `first_name`, `last_name`, `avatar`, `date_of_birth`, `is_staff`, `is_active`, `date_joined`

**Profile:** `UserPreferences` (one-to-one with User, auto-created via signal)
- Theme, modules, AI settings, timezone, notifications, etc.

---

## 4. Existing Medical/Lab/Vital Models

All in `apps/health/models.py`:

| Model | Purpose |
|-------|---------|
| `BloodPressureEntry` | Systolic/diastolic + context/arm/position |
| `GlucoseEntry` | Blood glucose (mg/dL) |
| `BloodOxygenEntry` | SpO2 |
| `BodyTemperatureEntry` | Body temperature |
| `WeightEntry` | Weight + BMI calc |
| `HeartRateEntry` | Heart rate + context |
| `SleepEntry` | Sleep duration/quality |
| `StepsEntry` | Steps + active calories |
| `WaterEntry` | Water intake |

**No existing lab test/panel/catalog models.** No structured lab result storage. No PDF ingestion. The new medical module is a greenfield build.

---

## 5. File Storage Configuration

**`config/settings.py` lines 274-330:**

| Environment | Backend |
|-------------|---------|
| **Production** | `cloudinary_storage.storage.MediaCloudinaryStorage` |
| **Testing** | `django.core.files.storage.FileSystemStorage` |
| **Development** | Cloudinary if configured, else filesystem |

**Document-specific storage:** `get_document_storage()` in `apps/life/models.py` returns `RawMediaCloudinaryStorage` (handles PDFs as raw files, not images).

**Media root:** `BASE_DIR / "media"` (local dev)

**Cloudinary config:** env vars `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`

**Security note:** Cloudinary supports server-side encryption. Medical files will use the same Cloudinary storage with `RawMediaCloudinaryStorage`. Encryption-at-rest is handled by Cloudinary's infrastructure.

---

## 6. UI Stack

**Server-rendered Django templates** (not SPA)

- Template engine: Django template language
- Base template: `templates/base.html`
- CSS: Custom CSS in `static/css/` (main.css, themes.css) — uses CSS variables, mobile-first responsive
- Interactivity: HTMX for dynamic updates
- Forms: Django ModelForms (crispy_forms in INSTALLED_APPS but custom CSS classes used)
- View pattern: Class-based views (CBV) with `LoginRequiredMixin`
- Base model: `UserOwnedModel` (soft delete + user ownership + `created_via` tracking)
- Template convention: `templates/<app_name>/<model>_<action>.html`

---

## 7. Key Patterns to Follow

**URL pattern:** `/health/physical/<feature>/` or `/life/documents/`
**New app URL:** `/medical/` (new top-level namespace)

**Model inheritance:** All user data models extend `UserOwnedModel` which provides:
- `user` FK to `AUTH_USER_MODEL`
- `created_via` (manual, ai_camera, import, api)
- `status` (active, archived, deleted) with soft delete
- `created_at`, `updated_at` timestamps
- `SoftDeleteManager` (filters deleted records by default)

**View pattern:** Standard Django CBVs with `LoginRequiredMixin`, custom mixins for help context

**Registration:** New app must be added to `INSTALLED_APPS` in `config/settings.py` and `urlpatterns` in `config/urls.py`

---

## 8. Build Status

| Component | Status |
|-----------|--------|
| `apps/medical/` app | Done |
| Models (9 models, ~690 LOC) | Done |
| Services (7 modules, ~2100 LOC) | Done |
| Admin interface | Done |
| Views (upload, import, summary, detail, trend, delete) | Done |
| Templates (`templates/medical/` — 6 templates) | Done |
| URL registration (`/medical/`) | Done |
| Navigation integration (Health mega menu) | Done |
| Integration with `apps/life/Document` (category='medical') | Done |
| Tests (41 tests) | Done |
| Documentation | Done |
| Seed data (45 tests, 150+ aliases) | Done |
