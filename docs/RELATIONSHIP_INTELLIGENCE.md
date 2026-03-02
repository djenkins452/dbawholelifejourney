# Relationship Intelligence — Phase R1 Foundation

**App:** `apps/relationships/`
**Status:** Phase R1 Complete
**Date:** 2026-03-02

---

## Domain Purpose

The Relationships app is **platform infrastructure** for relational intelligence.
It provides a canonical Person model that can be referenced from any module in the
Whole Life Journey ecosystem via @mentions, GenericForeignKey interactions, and
direct associations.

This is NOT a feature app — it is the foundation layer that other features build upon.

### Capabilities

- **Contacts** — User-scoped Person records with name, type, contact info
- **@Mentions** — Detect `@Name` patterns across Journal, Tasks, Prayer, Events, Meals
- **Interaction Tracking** — Cross-module interaction recording via GenericForeignKey
- **Analytics** — Interaction frequency, context breakdown, recency metrics
- **CoS Integration** — Top-10 interacted persons surfaced in CoS context
- **Household Sharing** — Optional link to Household for shared contacts
- **Autocomplete API** — AJAX endpoint for real-time @mention suggestions
- **Inline Creation** — Create new contacts from autocomplete without leaving the form

---

## Data Model

```
┌─────────────────────┐
│       Person        │
├─────────────────────┤
│ owner (FK User)     │
│ first_name          │
│ last_name           │
│ display_name        │
│ email (nullable)    │
│ phone (nullable)    │
│ relationship_type   │
│ notes               │
│ household (FK, opt) │
│ last_interaction    │←─── denormalized
│ interaction_count   │←─── denormalized
│ status (soft del)   │
└────────┬────────────┘
         │
    ┌────┴───────────────────────┐
    │                            │
    ▼                            ▼
┌─────────────────────┐  ┌──────────────────┐
│ RelationshipInter.  │  │     Mention      │
├─────────────────────┤  ├──────────────────┤
│ person (FK)         │  │ person (FK)      │
│ user (FK)           │  │ content_type     │
│ context_type_label  │  │ object_id        │
│ interaction_date    │  │ content_object   │← GenericFK
│ content_type        │  │ created_at       │
│ object_id           │  └──────────────────┘
│ source_object       │← GenericFK
│ created_at          │
└─────────────────────┘
```

### Relationship Types

| Value | Label |
|-------|-------|
| `spouse` | Spouse |
| `family` | Family |
| `friend` | Friend |
| `coworker` | Coworker |
| `church` | Church |
| `mentor` | Mentor |
| `other` | Other |

### Context Types (Interactions)

| Value | Source Model |
|-------|-------------|
| `journal` | JournalEntry |
| `task` | Task |
| `meal` | MealPlan |
| `prayer` | PrayerRequest |
| `event` | LifeEvent |
| `chat` | Chat conversation |
| `manual` | Manual entry |
| `other` | Other |

---

## Interaction Flow

```
User creates/saves content (Journal, Task, etc.)
    │
    ▼
post_save signal fires
    │
    ▼
_extract_mentions_from_instance()
    │
    ├── Checks: AI enabled? Contacts exist?
    │
    ▼
MentionParserService.parse_and_link()
    │
    ├── Phase 1: @mention pattern matching (@Name)
    ├── Phase 2: Bare name matching (word boundary)
    │
    ├── Creates Mention record (GenericFK → source object)
    ├── Creates RelationshipInteraction record
    └── Updates Person.last_interaction_date + interaction_count
```

---

## Mention Parsing Logic

### Detection Strategy

1. **@mention patterns**: `@John`, `@John Smith`, `@"John Smith Jr"`
2. **Bare name matching**: Scans for known contact names with word boundary regex
3. **Case-insensitive**: All matching is lowercased
4. **Deduplication**: Same person + same source object = single Mention

### Matching Priority

1. Exact `display_name` match
2. Exact `first_name` match
3. Prefix match on `first_name` (≥3 chars)

### Word Boundary Safety

Uses `\b` regex boundaries to prevent false positives:
- "John" matches in "Talked to John today"
- "John" does NOT match in "Johnson called"

---

## CoS Integration Strategy

The CoS context builder (`apps/core/ai_orchestrator/cos_context.py`) includes
relationship signals in every LLM request:

```python
# For top 10 interacted persons:
{
    'name': 'Heather',
    'relationship_type': 'spouse',
    'days_since_contact': 3,
    'drifting': False,
    'interaction_count': 47,
    'context_distribution': {
        'journal': 20,
        'task': 12,
        'prayer': 10,
        'event': 5
    }
}
```

This enables future prompts like:
- "You haven't interacted with Heather in 12 days."
- "Sarah appears mostly in prayer requests (80%). Want to schedule coffee?"

**Note:** Nudges are NOT auto-triggered yet. Data is surfaced for awareness only.

---

## Permissions

| Scope | Rule |
|-------|------|
| Default | Contacts are **private** (owner-scoped) |
| Household | If Person linked to Household, household members can **view** |
| Admin | Household admins can **edit** shared contacts |

All views enforce `owner=request.user` filtering. Cross-user access returns 404.

---

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/relationships/` | GET | Person list (paginated, filterable) |
| `/relationships/add/` | GET/POST | Create new Person |
| `/relationships/<pk>/` | GET | Person detail with analytics |
| `/relationships/<pk>/edit/` | GET/POST | Edit Person |
| `/relationships/<pk>/delete/` | POST | Soft-delete Person |
| `/relationships/autocomplete/?q=` | GET | AJAX autocomplete |
| `/relationships/quick-create/` | POST | Inline Person creation (JSON) |

---

## Phase R2: Relationship Insights Dashboard

**Status:** Complete
**Date:** 2026-03-02

### Scoring Model

Deterministic health score (0–100), computed on demand with 5-minute cache:

```
Base score: 100

Deductions:
  -2 per person >45 days stale (cap -20)
  -1 per context imbalance flag
  -5 if no event interactions in 30 days

Additions:
  +1 per week with consistent engagement (3+ of last 4 weeks, cap +10)

Final: clamped to [0, 100]
```

### Imbalance Detection

A person is flagged as imbalanced when:
- They have ≥3 total interactions
- One context_type_label accounts for >70% of their interactions

Imbalance flags include: `person_id`, `display_name`, `dominant_context`, `percentage`

### Insights Page (`/relationships/insights/`)

Four sections:
1. **Interaction Overview** — Score circle, active (7d) / stale (30d+) counts, insight lines, quick stats grid
2. **People Needing Attention** — Table of longest-no-contact persons with days since last interaction
3. **Context Balance** — Per-person bar charts showing interaction distribution across modules, orange bars for >70%
4. **Relational Anchors** — Top interacted persons with interaction counts and relationship types

### Dashboard Tile

Compact summary card (`relational_health`) registered in `config_service.py`:
- Score circle with numerical value
- Active / Stale counts
- Up to 3 insight lines
- Link to full insights page
- Graceful handling of no-contacts state

### CoS Payload

The CoS context builder includes relational health in every LLM request:

```python
{
    'relational_health': {
        'health_score': 85,
        'stale_relationships_count': 2,
        'top_anchor_persons': ['Heather', 'Mom', 'Dave'],
        'imbalance_flags': [
            {
                'person_id': 42,
                'display_name': 'Dave',
                'dominant_context': 'journal',
                'percentage': 85
            }
        ]
    }
}
```

### Metrics Computed

| Metric | Description |
|--------|-------------|
| `score` | Health score 0-100 (None if no contacts) |
| `total_contacts` | Total active Person count |
| `active_7d` | Persons with interaction in last 7 days |
| `stale_30d` | Persons with last interaction >30 days ago |
| `avg_days_between` | Average days between interactions across all contacts |
| `top_interacted` | Top 5 persons by interaction count |
| `longest_no_contact` | Top 5 persons by days since last interaction |
| `context_distributions` | Per-person breakdown of interaction context types |
| `imbalance_flags` | Persons with >70% interactions in one context |
| `insight_lines` | Up to 3 human-readable insight strings |

### Files Created/Modified (R2)

| File | Purpose |
|------|---------|
| `apps/relationships/services.py` | Added RelationalHealthService |
| `apps/relationships/views.py` | Added RelationshipInsightsView |
| `apps/relationships/urls.py` | Added `/insights/` route |
| `templates/relationships/insights.html` | Full insights page |
| `templates/dashboard/tiles/relational_health.html` | Dashboard summary card |
| `apps/dashboard/services/config_service.py` | Tile registration |
| `templates/dashboard/home.html` | Tile include |
| `apps/dashboard/views.py` | Context data for tile |
| `apps/core/ai_orchestrator/cos_context.py` | CoS health payload |
| `apps/relationships/tests/test_relationship_insights.py` | 24 tests |

---

## Future Extensibility

Planned future phases:

- **R3: Relationship Graph** — Visualize connection network, cluster analysis
- **R4: Friends Night Out** — Group event planning with Person associations
- **R5: Collaborative Events** — Multi-user event creation with shared contacts
- **R6: Relationship Goals** — Set cadence targets, track relationship health
- **R7: AI Nudges** — Auto-triggered reconnection suggestions based on drift

---

## Files Created

| File | Purpose |
|------|---------|
| `apps/relationships/__init__.py` | App init |
| `apps/relationships/apps.py` | App config with signal registration |
| `apps/relationships/models.py` | Person, RelationshipInteraction, Mention |
| `apps/relationships/services.py` | Analytics + MentionParser services |
| `apps/relationships/signals.py` | Cross-module post_save handlers |
| `apps/relationships/views.py` | CRUD views + autocomplete API |
| `apps/relationships/urls.py` | URL routing |
| `apps/relationships/forms.py` | Person forms |
| `apps/relationships/admin.py` | Admin registration |
| `apps/relationships/migrations/0001_initial.py` | Initial migration |
| `apps/relationships/tests/test_relationships_core.py` | 55 tests |
| `templates/relationships/person_list.html` | List view |
| `templates/relationships/person_form.html` | Create/edit form |
| `templates/relationships/person_detail.html` | Detail with analytics |
| `templates/relationships/partials/_mention_autocomplete.html` | Reusable component |

## Files Modified

| File | Change |
|------|--------|
| `config/settings.py` | Added `apps.relationships` to INSTALLED_APPS |
| `config/urls.py` | Added `/relationships/` route |
| `apps/core/ai_orchestrator/cos_context.py` | Updated `_build_people_and_mood()` for new Person model |
