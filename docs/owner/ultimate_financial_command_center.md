# Owner Financial Command Center — Ultimate Spec

**Status:** Phase 1 + 2 implemented | Phase 3–5 specced
**Created:** 2026-02-21
**Owner:** Danny Jenkins

---

## Product Goal

An internal, owner-only dashboard answering:

- Total monthly cost, total monthly revenue, gross margin
- Cost per user per month, margin per user
- Cost by feature / engine / model
- Escalation economics (normal vs escalated call costs)
- Top expensive users and what drives it
- "What-if" scenario simulator (users, escalation rate, interactions/day, tier mix)
- Budget guardrails (alerts when costs exceed thresholds)

---

## Phase 0 — Discovery Findings

### LLM/AI Call Sites

| File | Function | Model | Tracked? |
|------|----------|-------|----------|
| `apps/ai/services.py` | `_call_api()` | gpt-4o (configurable) | Yes (AIUsageLog) |
| `apps/ai/intent_service.py` | `recognize_intents()` | gpt-4o-mini | **No** |
| `apps/ai/personal_assistant.py` | via `ai_service._call_api()` | gpt-4o | Yes (uses _call_api) |
| `apps/capture/services/transcription.py` | `_call_whisper_api()` | whisper | **No** |
| `apps/capture/services/summarization.py` | `summarize_transcript()` | gpt-4o-mini | **No** |
| `apps/health/services/ai_nutrition.py` | `estimate_nutrition()` | gpt-4o-mini | **No** |
| `apps/health/views.py` | healthcare provider lookup | gpt-4o-mini | **No** |
| `apps/scan/services/vision.py` | `analyze_image()` | gpt-4o-mini | **No** |
| `apps/scan/services/barcode.py` | barcode lookup | gpt-4o-mini | **No** |
| `apps/scan/services/medicine_lookup.py` | medicine lookup | gpt-4o-mini | **No** |
| `apps/scan/services/product_lookup.py` | product lookup | gpt-4o-mini | **No** |

### Other Third-Party APIs

| Vendor | Category | File | Tracked? |
|--------|----------|------|----------|
| Twilio | SMS | `apps/sms/services.py` | No (has SMSNotification model) |
| Resend | Email | `apps/core/email_backends.py` | No |
| FatSecret | Nutrition API | `apps/health/services/fatsecret.py` | No |
| Google (Gmail/Calendar) | API | `apps/life/services/gmail.py` | No |
| Plaid | Finance | `apps/finance/services/plaid_service.py` | No |
| Dexcom | Health | `apps/health/services/dexcom.py` | No |
| Railway | Hosting | N/A (external) | Manual billing entry |

### User Tiers (Existing)

`BillingProfile` model with tiers: `free`, `faith_only`, `student` ($3.99), `adult` ($7.99), `founding` (lifetime).

### Admin Console Patterns

- All admin views use `AdminRequiredMixin` (checks `is_staff`)
- Templates extend `base.html`, use `.stat-card`, `.admin-card`, `.metric-card` CSS patterns
- URLs under `/admin-console/` with `admin_console` namespace

### Existing Tracking

- `AIUsageLog` — tracks OpenAI calls from `_call_api()` only (partial coverage)
- `APIRequestLog` — HTTP request logging for `/api/*` endpoints
- `AdminActivityLog` — admin task changes
- `PaymentAuditLog` — billing events

---

## Data Model

### A) `ThirdPartyVendor`

| Field | Type | Notes |
|-------|------|-------|
| name | CharField(100), unique | e.g., "OpenAI", "Twilio" |
| category | CharField choices | LLM, TTS, SMS, EMAIL, NUTRITION_API, HOSTING, ANALYTICS, OTHER |
| notes | TextField, blank | |
| created_at | DateTimeField auto | |

### B) `VendorBillingRecord`

| Field | Type | Notes |
|-------|------|-------|
| vendor | FK → ThirdPartyVendor | |
| period_start | DateField | |
| period_end | DateField | |
| cost_usd | DecimalField(10,4) | |
| cost_type | CharField choices | FIXED, VARIABLE |
| metadata | JSONField, default={} | |
| created_at | DateTimeField auto | |

### C) `LLMPriceBook`

| Field | Type | Notes |
|-------|------|-------|
| vendor | FK → ThirdPartyVendor | |
| model_name | CharField(100) | e.g., "gpt-4o-mini" |
| effective_start | DateField | |
| effective_end | DateField, nullable | |
| input_cost_per_1m_tokens_usd | DecimalField(10,4) | |
| output_cost_per_1m_tokens_usd | DecimalField(10,4) | |
| is_active | BooleanField | |

Unique constraint on (vendor, model_name, effective_start).

### D) `LLMUsageEvent`

| Field | Type | Notes |
|-------|------|-------|
| user | FK → User, nullable | null for system calls |
| conversation_id | CharField(100), nullable | |
| request_id | UUIDField | auto-generated |
| feature | CharField choices | INTENT, MAIN_RESPONSE, TRANSCRIPTION, SUMMARIZATION, NUTRITION_AI, VISION, SCAN, HEALTHCARE_LOOKUP, OTHER |
| engine | CharField(50), nullable | e.g., "ICQG", "PGE" |
| model_name | CharField(100) | |
| input_tokens | PositiveIntegerField | |
| output_tokens | PositiveIntegerField | |
| cost_usd | DecimalField(10,6) | computed from PriceBook |
| escalated | BooleanField, default=False | |
| metadata | JSONField, default={} | |
| created_at | DateTimeField, indexed | |

### E) `UserSubscriptionSnapshot`

| Field | Type | Notes |
|-------|------|-------|
| user | FK → User | |
| tier | CharField choices | FREE, FAITH_ONLY, STUDENT, ADULT, FOUNDING, OWNER |
| monthly_price_usd | DecimalField(8,2) | |
| effective_start | DateField | |
| effective_end | DateField, nullable | |
| metadata | JSONField, default={} | |
| created_at | DateTimeField auto | |

### F) `DailyCostRollup` (Phase 3)

| Field | Type | Notes |
|-------|------|-------|
| date | DateField | |
| user | FK → User, nullable | null = system total |
| feature | CharField, nullable | |
| total_cost_usd | DecimalField(10,4) | |
| total_calls | PositiveIntegerField | |
| total_input_tokens | PositiveIntegerField | |
| total_output_tokens | PositiveIntegerField | |

Unique constraint on (date, user, feature).

---

## Phase 1 — Telemetry Foundation ✅

- [x] Django app `apps/owner_finance/`
- [x] Models with migrations
- [x] `telemetry.py` service: `log_llm_usage()` computes cost from PriceBook
- [x] Integrated into `_call_api()` and `intent_service.recognize_intents()`
- [x] `OwnerOnlyMixin` security mixin
- [x] Django admin for all models

## Phase 2 — Minimal Owner Dashboard ✅

- [x] Overview page with KPI cards (total cost, revenue, margin, avg cost/user)
- [x] Top 10 expensive users table
- [x] Top features by cost table
- [x] Escalation economics table
- [x] Per-user cost/margin page
- [x] Feature/engine/model breakdown page
- [x] Vendor billing ledger page
- [x] Date range filtering (default 30 days)
- [x] 403 for non-owner users

---

## Phase 3 — Ultimate UI (TODO)

### Navigation Map

```
/owner/finance/              → Global Snapshot (Overview)
/owner/finance/users/        → Per-User Economics
/owner/finance/features/     → Feature/Engine/Model Breakdown
/owner/finance/vendors/      → Vendor Ledger & Forecast
/owner/finance/escalation/   → Escalation Economics Deep-Dive
/owner/finance/models/       → Model Mix & Cost Curves
/owner/finance/power-users/  → Power User Diagnostics
/owner/finance/simulator/    → Scenario Simulator
/owner/finance/budgets/      → Budget Alerts & Guardrails
/owner/finance/export/       → CSV Export
/owner/finance/audit/        → Per-Call Audit Ledger
```

### Section Details

#### Global Snapshot
- KPI cards: Total Cost, Revenue, Gross Margin %, Avg Cost/User, LLM vs Non-LLM split
- Daily cost trend line chart (30/60/90 day)
- Daily LLM cost stacked by feature
- Revenue vs cost overlay chart
- MoM comparison tiles

#### Unit Economics
- Per-user table: user, tier, total_cost, revenue, margin, margin_%
- Sortable by any column
- Drill-down to per-user call ledger
- Cohort analysis by tier (avg cost per FREE vs PRO user)

#### Escalation Economics
- Normal vs escalated call counts
- Avg cost per normal call vs escalated call
- Escalation rate % trend (daily)
- Cost of escalation: additional cost attributable to escalation
- Top users by escalation count

#### Model Mix & Cost Curves
- Pie chart: cost share by model
- Time-series: model usage trend (are we shifting to cheaper models?)
- Input vs output token ratio by model
- Cost efficiency: cost per 1K tokens by model

#### Power User Diagnostics
- Top 20 users by LLM cost
- Per-user: calls/day, avg tokens, top features used, escalation rate
- Anomaly detection: users with cost > 3σ from mean

#### Vendor Ledger & Forecast
- Monthly vendor billing records
- Running total by vendor
- Simple linear forecast (next 3 months) based on trend
- Editable: add new billing records inline

#### Scenario Simulator
- Input form:
  - `user_count` (slider/input)
  - `avg_interactions_per_user_per_day` (slider)
  - `escalation_rate` (%)
  - Model mix: % gpt-4o vs gpt-4o-mini vs other
  - Tier mix: % FREE vs STUDENT vs ADULT vs FOUNDING
  - Tier prices (editable)
- Output:
  - Projected monthly cost (LLM + non-LLM)
  - Projected monthly revenue
  - Projected margin & margin %
  - Break-even user count
  - Revenue needed for target margin

#### Budget Alerts & Guardrails
- Configure:
  - Monthly total budget
  - Per-user monthly budget
  - Per-feature monthly budget
- Dashboard warning tiles when budget exceeded
- Optional: notification record creation

#### CSV Export
- Export LLM usage events (date range)
- Export vendor billing records
- Export user cost summaries
- Export escalation data

#### Per-Call Audit Ledger
- Searchable, filterable table of all LLMUsageEvent records
- Filters: user, feature, engine, model, date range, escalated
- Shows: timestamp, user, feature, model, tokens, cost, escalated flag

### Feature Flags / Tier Gating
- Ability to simulate "Free vs Pro" mix
- Included escalation caps per tier
- Feature usage caps per tier
- Used in scenario simulator for "what if we cap free users at X calls/day"

---

## Phase 4 — Scenario Simulator (TODO)

### Backend Service: `services/simulator.py`

```python
def simulate_scenario(
    user_count: int,
    avg_interactions_per_day: float,
    escalation_rate: float,  # 0.0 - 1.0
    model_mix: Dict[str, float],  # {"gpt-4o": 0.1, "gpt-4o-mini": 0.9}
    tier_mix: Dict[str, float],  # {"free": 0.6, "student": 0.2, "adult": 0.2}
    tier_prices: Dict[str, Decimal],  # monthly price per tier
    avg_tokens_per_call: Dict[str, tuple],  # model -> (input, output)
) -> SimulationResult:
    """
    Returns:
        SimulationResult with:
        - monthly_llm_cost
        - monthly_non_llm_cost (from VendorBillingRecord avg)
        - monthly_revenue
        - gross_margin
        - margin_pct
        - break_even_users
        - per_user_cost
        - per_user_revenue
    """
```

### UI: Form + Results Panel

Simple form with sliders and number inputs. Results update on submit (no live JS yet — server-rendered).

---

## Phase 5 — Budget Guardrails & Alerts (TODO)

### Model: `BudgetGuardrail`

| Field | Type | Notes |
|-------|------|-------|
| name | CharField(100) | e.g., "Monthly Total Budget" |
| scope | CharField choices | TOTAL, PER_USER, PER_FEATURE |
| scope_value | CharField, nullable | Feature name if PER_FEATURE |
| budget_usd | DecimalField(10,2) | |
| period | CharField choices | DAILY, MONTHLY |
| alert_threshold_pct | IntegerField, default=80 | Alert at X% of budget |
| is_active | BooleanField | |

### Checking Logic

- Management command: `check_budget_guardrails` (run daily via scheduler)
- Compares actual spend against budgets
- Creates `Notification` (category=SYSTEM) for owner when threshold exceeded
- Dashboard shows red/yellow warning tiles

---

## Seeding Data

### LLM PriceBook (current OpenAI pricing)

```python
# Run via Django shell or management command
from apps.owner_finance.models import ThirdPartyVendor, LLMPriceBook
from datetime import date

openai = ThirdPartyVendor.objects.create(name="OpenAI", category="LLM")

LLMPriceBook.objects.create(
    vendor=openai, model_name="gpt-4o",
    effective_start=date(2024, 5, 1),
    input_cost_per_1m_tokens_usd=2.50,
    output_cost_per_1m_tokens_usd=10.00,
    is_active=True,
)
LLMPriceBook.objects.create(
    vendor=openai, model_name="gpt-4o-mini",
    effective_start=date(2024, 7, 1),
    input_cost_per_1m_tokens_usd=0.15,
    output_cost_per_1m_tokens_usd=0.60,
    is_active=True,
)
LLMPriceBook.objects.create(
    vendor=openai, model_name="whisper-1",
    effective_start=date(2024, 1, 1),
    input_cost_per_1m_tokens_usd=0.00,  # Whisper charges per minute
    output_cost_per_1m_tokens_usd=0.00,
    is_active=True,
)
```

---

## Manual Test Checklist

1. Run migrations: `python manage.py makemigrations owner_finance && python manage.py migrate`
2. Seed PriceBook entries via Django admin or shell
3. Send a chat message to the assistant → verify LLMUsageEvent created
4. Visit `/owner/finance/` as superuser → see dashboard with data
5. Visit `/owner/finance/` as regular user → see 403
6. Check `/owner/finance/users/`, `/owner/finance/features/`, `/owner/finance/vendors/`
7. Add a VendorBillingRecord via admin → see it on vendors page
