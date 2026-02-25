# PHASE 8: EXECUTIVE ARBITRATION ENGINE (EAE) — DESIGN SPECIFICATION

**Version:** 1.0
**Date:** 2026-02-25
**Status:** WAITING FOR APPROVAL TO IMPLEMENT
**Author:** Claude Code (design phase only — zero code written)

---

## TABLE OF CONTENTS

1. [Current Signal Map (Code-Verified)](#1-current-signal-map-code-verified)
2. [Arbitration Insertion Points (Code-Verified)](#2-arbitration-insertion-points-code-verified)
3. [EAE Output Schema](#3-eae-output-schema)
4. [Scoring & Normalization Model](#4-scoring--normalization-model)
5. [Noise Budget & Bundling Rules](#5-noise-budget--bundling-rules)
6. [Escalation + Override State Machine](#6-escalation--override-state-machine)
7. [Command Center Integration](#7-command-center-integration)
8. [Cost / Token Impact Model](#8-cost--token-impact-model)
9. [Test Plan](#9-test-plan)
10. [Phase 8 Implementation Plan](#10-phase-8-implementation-plan)

---

## 1. CURRENT SIGNAL MAP (CODE-VERIFIED)

### 1.1 Complete Signal Inventory

Every "signal" or "item" that can surface to the user, with source, storage, injection, and delivery channel.

| # | Signal Type | Source Engine | Generated In | Stored In (Model) | Injected Via | Delivered Via |
|---|-------------|--------------|-------------|-------------------|-------------|---------------|
| 1 | Insight (warning/critical/positive/info) | PIE | `apps/core/ai_insights/insight_engine.py` | `Insight` (ai_insights) | `cos_context.py` → `format_cos_system_injection()` | Chat + DNE (warning/critical only) |
| 2 | Prediction (trajectory projection) | PRIE | `apps/core/ai_predictions/prediction_engine.py` | `Prediction` (ai_predictions) | `cos_context.py` → `format_cos_system_injection()` | Chat + DNE (confidence ≥ 0.75) |
| 3 | Guidance item (priority 1–5) | PGE | `apps/core/ai_guidance/guidance_engine.py` | `GuidanceItem` (ai_guidance) | `cos_context.py` → `format_cos_system_injection()` | Chat + DNE + Dashboard tile |
| 4 | Cross-domain correlation | CDCE | `apps/core/ai_cross_domain/cdce_engine.py` | `DomainCorrelation` (ai_cross_domain) | `cos_context.py` → `format_cos_system_injection()` | Chat + DNE (strong/moderate only) |
| 5 | Daily briefing | DBE | `apps/core/ai_briefing/briefing_engine.py` | `DailyBriefing` (ai_briefing) | Dashboard tile + `views.py` context | Dashboard + DNE |
| 6 | Weekly report | WIRE | `apps/core/ai_weekly_report/report_engine.py` | `WeeklyIntelligenceReport` (ai_weekly_report) | Dashboard tile + `views.py` context | Dashboard + DNE |
| 7 | Arbitration narrative | UAL | `apps/core/ai_arbitration/arbitration_engine.py` | `ArbitrationDecisionLog` (ai_arbitration) | `personal_assistant.py:3334` → narrative_injection | Chat only |
| 8 | Active commitment | ECC | `apps/core/ai_orchestrator/commitment_contract.py` | `CommitmentContract` (ai_orchestrator) | `cos_context.py` → ECC section | Chat only |
| 9 | Drift signal | Drift Engine | `apps/core/drift/engine.py` | `DriftSignal`, `ExecutionLog` (drift) | `cos_context.py` → drift probability | Chat (via CoS context) |
| 10 | Pressure snapshot | Pressure Engine | `apps/core/blueprint/pressure_engine.py` | `PressureSnapshot` (blueprint) | `cos_context.py` → capacity section | Chat (via CoS context) |
| 11 | Protective recommendation | Protective Engine | `apps/core/blueprint/protective_engine.py` | `InterventionLog` (blueprint) | `cos_context.py` → protective briefing | Chat + DNE alerts |
| 12 | Escalation state | Escalation Engine | `apps/core/blueprint/escalation_engine.py` | Escalation level in Blueprint state | `cos_context.py` → protective briefing | Chat (implicit) |
| 13 | Reflection prompt | Reflection Engine | `apps/core/blueprint/reflection_engine.py` | Pending reflections | `personal_assistant.py:3311` → `deliver_pending_reflections()` | Chat (injected at session start) |
| 14 | Recalibration prompt | Governance | `apps/core/ai_governance/recalibration.py` | `GovernanceProfile` (ai_governance) | `personal_assistant.py:3265` → `build_recalibration_injection()` | Chat (overrides other context) |
| 15 | Governance alignment | Governance | `apps/core/ai_governance/alignment_session.py` | `GovernanceAlignmentSession` | `personal_assistant.py:3270` → `build_alignment_system_injection()` | Chat (overrides other context) |
| 16 | Executive briefing (morning) | EBE | `apps/ai/executive_briefing.py` | Ephemeral (built on-the-fly) | `personal_assistant.py:3317` → `build_executive_briefing()` | Chat (first-of-day or 4h gap) |
| 17 | Explain record (evidence) | E3 | `apps/core/ai_explain/explain_engine.py` | `ExplainRecord` (ai_explain) | Not directly injected; linked to PGE/DBE/WIRE | Indirect (via parent item) |
| 18 | Self-error audit | Self-Error | `apps/core/ai_governance/models.py` | `SelfError` (ai_governance) | Not injected into user-facing | Ops Wall only |
| 19 | Medication adherence signal | UAL signal collector | `apps/core/ai_arbitration/signal_collector.py` | Ephemeral (per-request) | UAL → intervention candidates → chat narrative | Chat (via UAL) |
| 20 | Sleep deficit signal | UAL signal collector | `apps/core/ai_arbitration/signal_collector.py` | Ephemeral (per-request) | UAL → intervention candidates → chat narrative | Chat (via UAL) |
| 21 | Mood decline signal | UAL signal collector | `apps/core/ai_arbitration/signal_collector.py` | Ephemeral (per-request) | UAL → intervention candidates → chat narrative | Chat (via UAL) |
| 22 | Relationship drift signal | UAL signal collector | `apps/core/ai_arbitration/signal_collector.py` | Ephemeral (per-request) | UAL → intervention candidates → chat narrative | Chat (via UAL) |
| 23 | Deadline pressure signal | UAL signal collector | `apps/core/ai_arbitration/signal_collector.py` | Ephemeral (per-request) | UAL → intervention candidates → chat narrative | Chat (via UAL) |
| 24 | Nudge dedup memory | Nudge Memory | `apps/core/ai_arbitration/nudge_memory.py` | `RecentNudgeMemory` (ai_arbitration) | Penalty applied to UAL candidates | Suppression (not surfaced) |
| 25 | Quality suppression record | ICQG | `apps/core/ai_quality/repeat_suppression.py` | `QualitySuppressionRecord` (ai_quality) | Filter applied to PGE/DBE/WIRE/DNE | Suppression (not surfaced) |
| 26 | Learning profile (responsiveness) | GLOE | `apps/core/ai_guidance_learning/learning_engine.py` | `GuidanceLearningProfile` | Ranking weight in PGE | Indirect (ranking influence) |
| 27 | Prediction accuracy profile | Feedback | `apps/core/ai_feedback/feedback_engine.py` | `PredictionAccuracyProfile` | Confidence adjustment in PRIE | Indirect (confidence modifier) |
| 28 | Intervention effectiveness | Feedback | `apps/core/ai_feedback/feedback_engine.py` | `InterventionEffectivenessProfile` | Escalation speed modifier | Indirect (escalation timing) |

### 1.2 Signal Flow Paths

```
                     ┌─────────────────────────────────────┐
                     │         USER ACTION / TIMER          │
                     └──────────────┬──────────────────────┘
                                    │
                     ┌──────────────▼──────────────────────┐
                     │     UAIO Execution Engine            │
                     │  (apps/core/ai_orchestrator/)        │
                     └──────────────┬──────────────────────┘
                                    │ fires event
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                       ▼
         ┌────────┐          ┌──────────┐           ┌──────────┐
         │  SAE   │          │   PIE    │           │   CDCE   │
         │ State  │          │ Insights │           │ Correlate│
         └───┬────┘          └────┬─────┘           └────┬─────┘
             │                    │ triggers              │
             │               ┌────▼─────┐                │
             │               │   PRIE   │                │
             │               │ Predict  │                │
             │               └────┬─────┘                │
             │                    │                       │
             ▼                    ▼                       ▼
    ┌─────────────────────────────────────────────────────────┐
    │              PGE — Proactive Guidance                    │
    │  (merges SAE + PIE + PRIE + CDCE into guidance)         │
    └────────────────────────┬────────────────────────────────┘
                             │
              ┌──────────────┼──────────────────┐
              ▼              ▼                    ▼
         ┌────────┐    ┌─────────┐         ┌──────────┐
         │  ICQG  │    │   E3    │         │   GLOE   │
         │Quality │    │Evidence │         │ Learning │
         └───┬────┘    └─────────┘         └──────────┘
             │
    ┌────────┼──────────────────────────────┐
    ▼        ▼                               ▼
┌────────┐ ┌──────────┐              ┌───────────┐
│  DBE   │ │  WIRE    │              │    DNE    │
│Briefing│ │ Report   │              │ Delivery  │
└───┬────┘ └────┬─────┘              └─────┬─────┘
    │           │                          │
    ▼           ▼                          ▼
┌──────────────────────────────────────────────┐
│        CURRENT: No unified arbitration        │
│   Each channel independently filters/caps     │
│                                               │
│ ►► THIS IS WHERE EAE INSERTS ◄◄              │
└──────────────────────────────────────────────┘
    │           │            │            │
    ▼           ▼            ▼            ▼
  Chat      Dashboard     DNE Push    Briefing
```

---

## 2. ARBITRATION INSERTION POINTS (CODE-VERIFIED)

### 2A. Chat Responses

**Current flow:**
`personal_assistant.py:_generate_response()` → builds system prompt with 18+ injection layers → calls OpenAI API

**EAE insertion point:**
- **WHERE:** `personal_assistant.py:_generate_response()`, after all context is assembled (line ~3340) but BEFORE the OpenAI API call (line ~3790)
- **WHAT ENTERS:** All assembled intelligence context (CoS context dict, UAL arbitration result, executive briefing, reflections, ECC commitments, page context)
- **WHAT EAE DOES:** Runs the full arbitration pipeline → produces `EAEDecision` → replaces the raw intelligence sections in system prompt with arbitrated, budgeted output
- **WHAT COMES OUT:** A filtered, ranked, bundled intelligence payload (max 3–5 cognitive units) formatted for system prompt injection
- **HOW EXISTING FLOW REMAINS INTACT:** EAE wraps the existing `format_cos_system_injection()` call and UAL narrative injection. Existing engines still compute everything. EAE only controls what reaches the LLM prompt.

**Concrete insertion:**
```
BEFORE (current):
  cos_context = build_cos_context(user)
  system_parts.append(format_cos_system_injection(cos_context))
  ...
  system_parts.append(arbitration.narrative_injection)

AFTER (with EAE):
  cos_context = build_cos_context(user)
  ual_result = run_arbitration(user)
  eae_decision = eae_engine.arbitrate(
      user=user,
      cos_context=cos_context,
      ual_result=ual_result,
      channel="chat",
      session_context={reflections, ecc, page_context}
  )
  system_parts.append(eae_decision.format_for_prompt())
```

### 2B. DNE Proactive Delivery (Push/Email/SMS/In-App)

**Current flow:**
`delivery_engine.py:deliver_due_notifications()` → collects undelivered PGE/DBE/WIRE/PIE/CDCE → applies ICQG filter → delivers per channel

**EAE insertion point:**
- **WHERE:** `apps/core/ai_delivery/delivery_engine.py:deliver_due_notifications()`, after candidate collection but BEFORE per-channel delivery
- **WHAT ENTERS:** List of delivery candidates (GuidanceItems, Insights, Correlations, Briefings)
- **WHAT EAE DOES:** Runs arbitration with `channel="push"` → applies noise budget → bundles related items → enforces cross-channel dedup
- **WHAT COMES OUT:** Filtered, bundled delivery payload respecting channel-specific budgets
- **HOW EXISTING FLOW REMAINS INTACT:** ICQG still runs first (quality gate). EAE sits between ICQG output and channel dispatch. DNE channel mechanics (APNS, SMS, email) unchanged.

### 2C. Executive Briefing Generation

**Current flow:**
- Morning: `executive_briefing.py:build_executive_briefing()` → ephemeral, injected into chat system prompt
- Daily: `briefing_engine.py:generate_daily_briefing()` → stored in `DailyBriefing` → displayed on dashboard

**EAE insertion point:**
- **WHERE:** `apps/ai/executive_briefing.py:build_executive_briefing()`, at the point where it assembles the briefing content
- **ALSO:** `apps/core/ai_briefing/briefing_engine.py:generate_daily_briefing()`, after snapshot aggregation
- **WHAT ENTERS:** All engine snapshots (SAE state, PIE insights, PRIE predictions, PGE guidance, protective alerts)
- **WHAT EAE DOES:** Runs arbitration with `channel="briefing"` → selects top 3–5 cognitive units → assigns Primary Focus → generates "why this matters" lines
- **WHAT COMES OUT:** Structured briefing with ranked items, Primary Focus designation, and suppressed items list
- **HOW EXISTING FLOW REMAINS INTACT:** Engine snapshots still captured in full for the `DailyBriefing` model JSON fields. EAE only controls the `summary` field and what's highlighted.

### 2D. Command Center Visibility / Telemetry

**Current flow:**
- `views_intelligence_center.py:IntelligenceCommandCenterView` → aggregates engine outputs for display
- `ai_observability/ops_views.py` → Ops Wall with engine health, SAME narrative, anomalies

**EAE insertion point:**
- **WHERE:** New section in Command Center template + new API endpoint in `views_intelligence_center.py`
- **WHAT ENTERS:** EAE decision log (all decisions with timestamps)
- **WHAT COMES OUT:** Dashboard panels showing: active focus, suppressed signals, override history, noise budget usage, escalation state
- **HOW EXISTING FLOW REMAINS INTACT:** Additive only. New panels alongside existing engine cards. No modification to Ops Wall or SAME narrative.

---

## 3. EAE OUTPUT SCHEMA

### 3.1 EAEDecision (Primary Output)

```python
EAEDecision:
    # Identity
    decision_id:            UUID
    user_id:                int
    channel:                str          # "chat" | "push" | "briefing" | "command_center"
    created_at:             datetime

    # Ranked Intelligence Stack
    cognitive_units:        List[CognitiveUnit]   # Ordered by rank, max 5
    total_candidates:       int                    # How many signals entered arbitration
    suppressed_count:       int                    # How many were suppressed

    # Primary Focus
    primary_focus:          Optional[PrimaryFocus]
    focus_change_locked:    bool                   # True if focus changed today (max 2/day)
    focus_changes_today:    int                    # 0, 1, or 2
    last_focus_change_at:   Optional[datetime]

    # Escalation
    escalation_level:       int                    # 0–4
    escalation_reason:      str                    # Human-readable reason code
    drift_risk_severity:    float                  # 0–100 (anchor metric)

    # Tone
    tone_band:              str                    # See §3.4

    # Override State
    active_overrides:       List[OverrideRecord]
    active_cooldowns:       List[CooldownRecord]
    permanent_suppressions: List[str]              # List of suppressed signal types

    # Audit
    reason_codes:           List[str]              # Machine-readable decision reasons
    source_engines:         List[str]              # Engines that contributed signals
    arbitration_duration_ms: int
    noise_budget_used:      int                    # Cognitive units consumed
    noise_budget_max:       int                    # Budget for this channel
```

### 3.2 CognitiveUnit (Bundled Intelligence Item)

```python
CognitiveUnit:
    unit_id:                UUID
    rank:                   int              # 1 = highest priority
    unit_type:              str              # "single" | "bundle"

    # Content
    title:                  str              # Short headline (≤80 chars)
    why_this_matters:       str              # 1–2 sentence explanation for user
    source_engine:          str              # Primary engine (PIE/PRIE/PGE/CDCE/ECC/Drift/Protective)
    source_items:           List[SourceItem] # Underlying signals (1 for single, 2+ for bundle)

    # Scoring
    normalized_score:       float            # 0–100 (EAE-normalized)
    confidence:             float            # 0.0–1.0
    drift_anchor_weight:    float            # How much drift severity influenced ranking

    # Metadata
    module:                 str              # health, faith, journal, goals, etc.
    severity:               str              # info | positive | warning | critical
    actionable:             bool             # Does this have a concrete next step?
    action_url:             Optional[str]    # Deep link if actionable
    expires_at:             Optional[datetime]

    # Bundle info (if unit_type == "bundle")
    bundle_label:           Optional[str]    # e.g., "Medications (3 items)"
    bundled_count:          Optional[int]
```

### 3.3 SourceItem (Individual Signal Reference)

```python
SourceItem:
    engine:                 str              # PIE, PRIE, PGE, CDCE, etc.
    object_type:            str              # Insight, Prediction, GuidanceItem, etc.
    object_id:              int
    local_score:            float            # Engine's own score (pre-normalization)
    confidence:             float
    created_at:             datetime
```

### 3.4 Tone Band Assignment

| Band | Trigger Condition | Style |
|------|-------------------|-------|
| `REFLECTIVE_GENTLE` | Escalation 0, drift < 30 | Warm, observational, invitational |
| `REFLECTIVE_FIRM` | Escalation 0–1, drift 30–59 | Factual, structured, encouraging |
| `DIRECT_CLEAR` | Escalation 1–2, drift 60–69 | No fluff, priorities first, direct |
| `DIRECT_URGENT` | Escalation 2–3, drift 70–84 | Consequences visible, compressed |
| `EXECUTIVE_OVERRIDE` | Escalation 3–4, drift 85–100 | Minimal words, single action, no options |

### 3.5 PrimaryFocus

```python
PrimaryFocus:
    focus_label:            str              # e.g., "Medication Adherence"
    focus_module:           str              # e.g., "health"
    reason:                 str              # e.g., "2 missed doses in 24h"
    drift_contribution:     float            # How much this contributes to drift score
    set_at:                 datetime
    change_type:            str              # "morning" | "midday_correction" | "retained"
```

---

## 4. SCORING & NORMALIZATION MODEL

### 4.1 Local Engine Scoring (Pre-Normalization)

Each engine provides its own score on its own scale. EAE normalizes these.

| Engine | Local Score Source | Range | What It Measures |
|--------|-------------------|-------|-----------------|
| PIE | `Insight.confidence_score` × severity_weight | 0–100 | severity: info(10), positive(25), warning(60), critical(100) × confidence |
| PRIE | `Prediction.confidence_score` × horizon_urgency | 0–100 | confidence × (1.0 if ≤7d, 0.7 if ≤30d, 0.4 if ≤90d) |
| PGE | `GuidanceItem.priority` mapped + confidence | 0–100 | priority: Critical(100), High(80), Medium(50), Low(25), Info(10) × confidence |
| CDCE | `DomainCorrelation.strength_score` × 100 | 0–100 | Direct strength score |
| ECC | Commitment tier × deadline proximity | 0–100 | tier(1=100,2=70,3=40) × (1.0 if due today, 0.5 if this week) |
| Drift | `drift_score` from SAE state | 0–100 | Already on 0–100 scale |
| Protective | CPI (Composite Pressure Index) | 0–100 | Already on 0–100 scale |
| UAL | Scenario score × 100 | 0–100 | From UAL signal fusion |

### 4.2 Global Normalization Formula

```
normalized_score = (
    local_score × 0.35                    # Engine's own assessment
  + drift_anchor_weight × 0.30           # Drift Risk Severity contribution
  + governance_weight × 0.20             # GovernanceProfile importance_weight
  + recency_weight × 0.15               # How recent the signal is
)
```

**Drift Anchor Weight:**
```
drift_anchor_weight = 0  (default)

If signal.module matches a drifting domain:
  drift_anchor_weight = drift_severity_for_module × governance_importance

Where:
  drift_severity_for_module = from SAE pillar_scores or drift engine per-module
  governance_importance = GovernanceProfile.importance_weight (0.3–2.0)
```

**Governance Weight:**
```
governance_weight = GovernanceProfile.importance_weight for signal's module
  non_negotiable: 2.0
  important: 1.0
  flexible: 0.3
  uncategorized: 0.5 (default)
```

**Recency Weight:**
```
recency_weight = max(0, 1.0 - (hours_since_creation / 168))  # Linear decay over 7 days
```

### 4.3 Confidence Thresholds

| Threshold | Value | Effect |
|-----------|-------|--------|
| Minimum for surfacing (chat) | 0.40 | Below this, suppress entirely |
| Minimum for surfacing (push) | 0.60 | Higher bar for push delivery |
| Minimum for surfacing (briefing) | 0.30 | Lower bar for briefing (context, not interruption) |
| High-confidence boost | ≥ 0.85 | +10 to normalized_score |
| Low-confidence penalty | ≤ 0.50 | -15 to normalized_score |

### 4.4 Deduplication Rules

EAE dedup is a SECOND layer on top of per-engine dedup (which remains unchanged):

1. **Same-module, same-type, same-day:** If two signals share (module, type, date), keep higher-scored one only
2. **Overlapping predictions:** If two PRIE predictions target same metric at similar horizons (≤7d apart), bundle them
3. **Insight + Guidance overlap:** If PIE insight and PGE guidance item reference the same underlying data, keep guidance (more actionable), suppress insight
4. **Cross-channel dedup:** If a signal was delivered via push in last 4 hours, suppress from chat (unless severity increased)

### 4.5 Expiry Rules

| Signal Type | Expiry | After Expiry |
|-------------|--------|-------------|
| PIE Insight (info/positive) | 48 hours | Auto-mark dismissed |
| PIE Insight (warning/critical) | 7 days | Remains, score decays via recency |
| PRIE Prediction | predicted_date + 1 day | Auto-mark expired |
| PGE Guidance | `expires_at` or 14 days | Auto-deactivate |
| CDCE Correlation | 30 days | Auto-mark expired |
| ECC Commitment | Commitment deadline | Escalation if incomplete |
| Protective Alert | 12 hours (supersede window) | Replaced by newer |

---

## 5. NOISE BUDGET & BUNDLING RULES

### 5.1 What Is a "Cognitive Unit"

A cognitive unit is **one mental context-switch** the user must make. It is the atomic unit of attention cost.

**One cognitive unit =**
- A single insight ("Your weight trend is declining")
- A single prediction ("At this rate, you'll hit your goal by March 15")
- A single action prompt ("Take your evening medication")
- A **bundle** of related items that share context ("3 medications due: Vitamin D, Fish Oil, Magnesium" = 1 unit, NOT 3)
- A single correlation ("When you sleep <6.5h, your mood drops the next day")

**NOT a cognitive unit (these are infrastructure, not attention-consuming):**
- Tone/style instructions to the LLM
- Context about user's current page
- Conversation memory
- User profile data
- Module permissions

### 5.2 Default Caps Per Channel

| Channel | Default Cap | Hard Max | Rationale |
|---------|------------|----------|-----------|
| Chat response | 3 | 5 | Primary interaction; must not overwhelm |
| Push notification | 1 | 2 | Most interruptive channel |
| SMS | 1 | 1 | Character-limited + most intrusive |
| Email digest | 5 | 7 | Async, user reads at own pace |
| Daily briefing | 5 | 7 | Dedicated intelligence summary |
| Weekly report | 7 | 10 | Longitudinal, user expects density |
| Command Center | Unlimited | — | Admin visibility, no noise concern |

### 5.3 Bundling Rules

**Bundling triggers:**
1. **Same module + same action type:** 3 medications due → "Medications (3 due)" = 1 unit
2. **Same module + opposing signals:** Weight insight + weight prediction → "Weight Trajectory" = 1 unit
3. **Causal chain:** Sleep deficit → mood decline → journal drop-off → bundle as "Recovery Priority" = 1 unit
4. **Routine cluster:** All morning routine items → "Morning Routine" = 1 unit

**Bundling constraints:**
- Max items per bundle: 5
- Min items to trigger bundle: 2
- Bundle replaces individual items in the budget (never both)
- Bundles inherit the highest severity of their members
- Bundle score = max(member_scores) + 5 (bundling bonus for coherence)

**Bundle label format:** `"{Category} ({N} items)"` e.g., "Medications (3 due)", "Health Alerts (2 items)"

### 5.4 Cross-Channel Budget Enforcement

**Daily global budget:** User sees max 8 cognitive units across ALL channels combined per day.

**Allocation priority:**
1. Chat interactions get first claim (most interactive)
2. Push/SMS get second claim (time-sensitive alerts only)
3. Briefing gets remainder (comprehensive but lower priority items)

**Cross-channel dedup:**
- If item was in chat within 4 hours → suppress from push
- If item was pushed → mark as "already delivered" in chat (mention briefly, don't re-explain)
- Briefing includes ALL items (even delivered ones) but marks which were already surfaced

### 5.5 Capacity-Adjusted Budget

| Capacity State | Budget Modifier | Rationale |
|----------------|----------------|-----------|
| CRITICAL (< 0.2) | -2 from cap | User overwhelmed; only most critical |
| LOW (0.2–0.4) | -1 from cap | Reduce load |
| NORMAL (0.4–0.7) | 0 (default) | Standard operation |
| HIGH_CAPACITY (> 0.7) | +1 to cap | User has bandwidth for more |

**Floor:** Never below 1 cognitive unit (always surface the #1 priority).

---

## 6. ESCALATION + OVERRIDE STATE MACHINE

### 6.1 Drift Risk Bands

| Band | Drift Score | Label | Behavior |
|------|------------|-------|----------|
| 0–39 | GREEN | On Track | Standard operation, reflective tone |
| 40–59 | YELLOW | Attention Needed | Increased surfacing priority for drifting modules |
| 60–69 | ORANGE | Active Drift | Direct tone, non-negotiables surfaced first |
| 70–84 | RED | Significant Drift | Urgent tone, escalation engaged, consequences visible |
| 85–100 | CRITICAL | Crisis | Executive override tone, single focus, no bundling—one action only |

### 6.2 Escalation Ladder

| Level | Label | Trigger | Surfacing Behavior | Tone Band |
|-------|-------|---------|-------------------|-----------|
| 0 | NOMINAL | Drift < 40 | Normal budget, standard ranking | REFLECTIVE_GENTLE or REFLECTIVE_FIRM |
| 1 | ELEVATED | Drift 40–59 OR 2+ consecutive missed non-negotiables | +1 cognitive unit for drifting module, governance weight boosted | REFLECTIVE_FIRM or DIRECT_CLEAR |
| 2 | ACTIVE | Drift 60–69 OR 3+ consecutive days of decline | Non-negotiable items always surfaced (bypass budget for 1 slot), ECC commitments highlighted | DIRECT_CLEAR or DIRECT_URGENT |
| 3 | CRITICAL | Drift 70–84 OR override strike 2 | Budget compressed to top 2 items only, consequences in every response, recalibration prompt queued | DIRECT_URGENT |
| 4 | OVERRIDE | Drift 85+ OR sustained 5+ days at level 3 | Single item only, executive override tone, system initiates recalibration conversation | EXECUTIVE_OVERRIDE |

### 6.3 Escalation Transitions

**Upward transitions (immediate):**
- Any condition that meets a higher level's trigger → escalate immediately
- Log: `EAEEscalationEvent(direction="up", from_level, to_level, trigger_reason)`

**Downward transitions (gated — must meet ALL criteria):**
- Drift score decreased by ≥ 10 points from peak
- At least 48 hours at current level
- No new non-negotiable misses in 48 hours
- At least 1 positive compliance event (honored commitment, acted on guidance)
- Can only de-escalate one level at a time (no jumps)
- Log: `EAEEscalationEvent(direction="down", from_level, to_level, recovery_criteria_met)`

**Integration with existing escalation engine:**
- Blueprint's `escalation_engine.py` levels (CLEAN, EARLY_EROSION, STRUCTURAL_DRIFT) map to EAE levels 0, 1, 2
- EAE extends with levels 3–4 (CRITICAL, OVERRIDE) which don't exist in current system
- EAE reads existing escalation state; does NOT write to it. EAE tracks its own level in `EAEState`

### 6.4 Primary Focus Rules

- **Max changes per day:** 2 (morning set + 1 midday correction)
- **Morning set:** First interaction of the day (or first briefing generation) → set Primary Focus from highest-ranked cognitive unit
- **Midday correction:** Allowed only if drift increased by ≥ 15 points since morning OR a critical event occurred
- **Lockout:** After 2 changes, focus is locked until next day (00:00 user timezone)
- **Persistence:** Primary Focus stored in `EAEState.primary_focus_*` fields
- **Chat behavior:** Primary Focus item is ALWAYS included in cognitive units, even if it wouldn't otherwise rank high enough

### 6.5 Override State Machine

```
                    ┌──────────────┐
                    │   NORMAL     │
                    │ (no override)│
                    └──────┬───────┘
                           │ User pushes back on signal
                    ┌──────▼───────┐
                    │  STRIKE 1    │
                    │ Clarify +    │
                    │ Recommend    │
                    └──────┬───────┘
                           │ User pushes back again (same signal type)
                    ┌──────▼───────┐
                    │  STRIKE 2    │
                    │ Confirm +    │
                    │ Consequences │
                    └──────┬───────┘
                           │ User pushes back third time
                    ┌──────▼───────┐
                    │  STRIKE 3    │
                    │ Comply + Log │
                    │ + Suppress   │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
     ┌────────────┐ ┌───────────┐ ┌──────────┐
     │ PERMANENT  │ │ TEMPORARY │ │ AMBIGUOUS │
     │ "don't ask │ │ "not      │ │ unclear   │
     │  again"    │ │  today"   │ │ intent    │
     └────────────┘ └───────────┘ └──────────┘
           │              │              │
           │              │              │ Ask 1 clarification
           │              │              │ No response in 60s?
           │              │              ▼
           │              │         TEMPORARY (default)
           │              │
           │              ▼
           │         Cooldown expires
           │         (24h default)
           │              │
           │              ▼
           │         ┌──────────┐
           │         │  NORMAL  │
           │         └──────────┘
           │
           ▼
     ┌─────────────────┐
     │ PERMANENT_SUPP   │
     │ Never surface    │
     │ this signal type │
     │ again            │
     └─────────────────┘
```

**Override classification rules:**
- "don't ask again", "stop reminding me", "I don't care about this" → `PERMANENT`
- "not today", "not now", "later", "I know" → `TEMPORARY` (24h cooldown)
- "okay", "fine", "whatever" (no clear direction) → `AMBIGUOUS` → ask one clarifying question
- If clarification unanswered within 60 seconds of next interaction → default to `TEMPORARY`

**Cooldown durations:**
- `TEMPORARY`: 24 hours
- `TEMPORARY` from ambiguous: 12 hours (shorter, since user didn't explicitly request suppression)
- After 3 temporary cooldowns on same signal in 14 days → auto-escalate to `PERMANENT`

### 6.6 Required Database State

**New model: `EAEState` (OneToOne per user)**
```
Fields:
  user                    FK (OneToOne)
  escalation_level        IntegerField (0–4)
  escalation_since        DateTimeField
  drift_risk_severity     FloatField (0–100)
  primary_focus_label     CharField(100, nullable)
  primary_focus_module    CharField(50, nullable)
  primary_focus_set_at    DateTimeField(nullable)
  focus_changes_today     IntegerField (0–2)
  focus_date              DateField (for daily reset)
  noise_budget_used_today IntegerField
  noise_budget_date       DateField
  last_arbitration_at     DateTimeField
  updated_at              DateTimeField(auto_now)
```

**New model: `EAEDecisionLog` (append-only audit)**
```
Fields:
  decision_id             UUIDField (primary key)
  user                    FK
  channel                 CharField(20)
  created_at              DateTimeField(auto_now_add, indexed)
  escalation_level        IntegerField
  drift_risk_severity     FloatField
  tone_band               CharField(30)
  primary_focus_label     CharField(100, nullable)
  cognitive_units_json    JSONField          # Full CognitiveUnit list
  suppressed_items_json   JSONField          # What was suppressed and why
  total_candidates        IntegerField
  surfaced_count          IntegerField
  suppressed_count        IntegerField
  noise_budget_used       IntegerField
  noise_budget_max        IntegerField
  override_events_json    JSONField(nullable) # Any overrides applied
  reason_codes            JSONField           # List of reason code strings
  source_engines          JSONField           # List of contributing engine names
  arbitration_duration_ms IntegerField
```

**New model: `EAEOverride` (per user, per signal type)**
```
Fields:
  user                    FK
  signal_type             CharField(100)     # e.g., "PIE:medication_adherence"
  override_type           CharField(20)      # permanent | temporary
  strike_count            IntegerField (1–3)
  cooldown_until          DateTimeField(nullable) # For temporary overrides
  temporary_count_14d     IntegerField(default=0) # For auto-escalation to permanent
  created_at              DateTimeField
  updated_at              DateTimeField(auto_now)

  Unique constraint: (user, signal_type)
```

**New model: `EAEEscalationEvent` (append-only)**
```
Fields:
  user                    FK
  direction               CharField(10)      # "up" | "down"
  from_level              IntegerField
  to_level                IntegerField
  trigger_reason          CharField(200)
  drift_risk_at_event     FloatField
  created_at              DateTimeField(auto_now_add, indexed)
```

**Integration with existing models (read-only by EAE):**
- `GovernanceProfile` — importance_weight, commitment_level
- `ArbitrationDecisionLog` — UAL scenario, surfaced items
- `DailyCapacityLog` — capacity_state, capacity_score
- `InterventionResponseLog` — compliance tracking
- `QualitySuppressionRecord` — ICQG suppression state
- `PressureSnapshot` — CPI score
- `DriftSignal` — drift events
- `GuidanceLearningProfile` — responsiveness score
- `InterventionEffectivenessProfile` — effectiveness score
- `PersonalOperatingBlueprint` — operating style, interruption tolerance

---

## 7. COMMAND CENTER INTEGRATION

### 7.1 New Panels for Command Center

**Panel 1: Active Focus & Escalation**
- Current Primary Focus (label, module, since when)
- Escalation level (0–4) with color coding (green → red)
- Drift Risk Severity gauge (0–100)
- Focus changes today (0/2, 1/2, 2/2 locked)
- Time since last escalation change

**Panel 2: Noise Budget Tracker**
- Today's budget: used / max (per channel)
- Global daily budget: used / 8
- Visual bar chart of budget consumption
- Top suppressed signals (what DIDN'T surface today, and why)

**Panel 3: Override History**
- Active permanent suppressions (signal types the user doesn't want)
- Active temporary cooldowns (what + when they expire)
- Override strike counts by signal type
- Last 7 days: override events timeline

**Panel 4: Arbitration Audit Log**
- Last 10 `EAEDecisionLog` entries with expandable details
- For each: channel, cognitive units surfaced, suppressed count, tone band, reason codes
- Filterable by channel and date

**Panel 5: Cognitive Unit Analytics (Weekly)**
- Distribution: how many units surfaced per day (bar chart)
- By engine: which engines contributed most signals
- By module: which life domains had most signals
- Bundle rate: % of cognitive units that were bundles
- User engagement: acted vs dismissed vs ignored (from GLOE/feedback)

### 7.2 Heartbeat Cadence

| Check | Frequency | What It Verifies |
|-------|-----------|-----------------|
| EAE state integrity | Every ISE cycle (5 min) | `EAEState` exists for all active users, escalation level consistent with drift |
| Budget reset | Daily at 00:00 user timezone | `noise_budget_used_today` reset, `focus_changes_today` reset |
| Override cleanup | Daily | Remove expired temporary cooldowns, check 14-day auto-escalation |
| Audit log pruning | Weekly | Archive `EAEDecisionLog` entries older than 90 days |

### 7.3 Integrity Scoring

**EAE Health Score (0–100):**
```
health = 100
- 20 if arbitration hasn't run in 15+ minutes for any active user
- 15 if escalation level doesn't match drift band
- 10 if noise budget is negative (overcounting bug)
- 10 if any EAEState.focus_date is stale (not today)
- 5 per override with strike_count > 3 (shouldn't happen)
```

**Anomaly Flags:**
- Escalation stuck at level 4 for > 3 days → flag for admin review
- Budget consistently maxed before noon → capacity model may be miscalibrated
- Override auto-escalation to permanent happened → user may be disengaging from module

### 7.4 Logging Requirements

All EAE decisions logged to:
1. `EAEDecisionLog` — full audit trail (as defined in §6.6)
2. `AIUsageLog` — token impact (via existing telemetry; EAE adds no LLM calls)
3. `LLMUsageEvent` — cost tracking (EAE reduces tokens, so this should show improvement)
4. `EngineRun` (observability) — EAE registered as engine "EAE" with expected cadence
5. `DecisionRecord` (observability) — key arbitration decisions with reason codes

---

## 8. COST / TOKEN IMPACT MODEL

### 8.1 Current Prompt Token Usage

Based on `AIUsageLog` and `LLMUsageEvent` tracking:

| Component | Estimated Tokens | Notes |
|-----------|-----------------|-------|
| Base system prompt | ~800 | Personality, capabilities, rules |
| CoS context injection | ~1,200–2,500 | Blueprint, capacity, drift, guidance, insights, predictions, correlations |
| UAL narrative | ~200–400 | Scenario narrative injection |
| Executive briefing | ~300–600 | Morning briefing (when triggered) |
| Reflections | ~100–300 | Pending reflection prompts |
| ECC commitments | ~100–200 | Active commitment list |
| Page context | ~200–500 | Current page data |
| Personal data | ~200–800 | Recent weight, journal, medication, etc. |
| Conversation memory | ~500–1,000 | Rolling summary |
| **TOTAL CURRENT** | **~3,600–6,600** | Per chat interaction |

### 8.2 Expected Token Impact with EAE

**Reduction from arbitration:**
- Current: ALL signals injected into prompt (~1,200–2,500 tokens in CoS context alone)
- With EAE: Only 3–5 cognitive units injected (~400–800 tokens)
- **Estimated savings: 600–1,700 tokens per chat interaction**

**Addition from EAE metadata:**
- Tone band instruction: ~30 tokens
- Primary Focus directive: ~50 tokens
- Escalation context: ~40 tokens
- Override state: ~20 tokens
- **Estimated addition: ~140 tokens**

**Net impact: ~460–1,560 token REDUCTION per chat interaction**

### 8.3 Added API Calls

**EAE adds ZERO new LLM calls.** EAE is entirely deterministic:
- Signal collection: database queries
- Scoring/normalization: arithmetic
- Bundling: rule-based matching
- Tone selection: lookup table
- Override evaluation: state machine check

### 8.4 Database Query Impact

**Per chat interaction (new queries):**
- `EAEState` read: 1 query (indexed by user)
- `EAEOverride` read: 1 query (user + signal_type, filtered)
- `EAEDecisionLog` write: 1 insert
- `EAEState` update: 1 write

**Total: ~4 additional queries per chat interaction** (negligible vs. current ~30+ queries for context building)

### 8.5 Mitigation Strategies

1. **EAEState is cached in-memory** per request (single read, used throughout)
2. **Override lookup uses select_related** to batch with state query
3. **Decision log writes are fire-and-forget** (async, non-blocking, same pattern as E3)
4. **Budget counters update atomically** via F-expressions (no read-modify-write race)

### 8.6 Telemetry Measurement Plan

| Metric | How to Measure | Where to Log |
|--------|---------------|-------------|
| Prompt token reduction | Compare `AIUsageLog.prompt_tokens` before/after EAE rollout | Weekly `IntelligenceMetricsSnapshot` |
| Arbitration latency | `EAEDecisionLog.arbitration_duration_ms` | Per-decision + daily P95 |
| Budget utilization | `EAEDecisionLog.noise_budget_used / noise_budget_max` | Daily aggregate |
| Override frequency | Count `EAEOverride` events per week | Weekly WIRE integration |
| Escalation distribution | `EAEEscalationEvent` counts by level | Weekly metric snapshot |

---

## 9. TEST PLAN

### 9.1 Unit Test Categories

**A. Scoring & Normalization (apps/core/ai_eae/tests/test_scoring.py)**
- Each engine's local score maps correctly to 0–100
- Drift anchor weight correctly multiplies governance importance
- Recency decay is linear over 7 days
- Confidence thresholds apply correctly (minimum surfacing, boost, penalty)
- Edge cases: zero confidence, max confidence, no drift, max drift, no governance profile

**B. Bundling (apps/core/ai_eae/tests/test_bundling.py)**
- 3 medications → 1 bundle with highest severity
- 2 same-module items → 1 bundle with max+5 score
- Causal chain detection (sleep → mood → journal)
- Max 5 items per bundle enforced
- Bundles correctly replace individual items in budget
- No bundling when items are from different modules with no causal link

**C. Noise Budget (apps/core/ai_eae/tests/test_budget.py)**
- Chat capped at 3 (default), push at 1, briefing at 5
- Capacity adjustment: CRITICAL reduces by 2, LOW by 1, HIGH adds 1
- Floor: always at least 1 cognitive unit
- Cross-channel dedup: push within 4h suppresses from chat
- Daily global budget (8) enforced across channels
- Budget resets at midnight user timezone

**D. Tone Selection (apps/core/ai_eae/tests/test_tone.py)**
- Each escalation level + drift band → correct tone band
- Tone band format string is valid for prompt injection

**E. Primary Focus (apps/core/ai_eae/tests/test_focus.py)**
- Morning set from highest-ranked unit
- Midday correction only on drift increase ≥ 15
- Lockout after 2 changes per day
- Focus retained across interactions (same day)
- Daily reset at midnight

**F. Override State Machine (apps/core/ai_eae/tests/test_override.py)**
- Strike 1 → clarify + recommend behavior
- Strike 2 → confirm + consequences
- Strike 3 → comply + log + suppress
- "don't ask again" → PERMANENT
- "not today" → TEMPORARY (24h)
- Ambiguous → ask clarification → timeout → TEMPORARY (12h)
- 3 temporaries in 14 days → auto-escalate to PERMANENT
- Expired cooldowns cleared correctly

**G. Escalation Ladder (apps/core/ai_eae/tests/test_escalation.py)**
- Each drift band → correct escalation level
- Consecutive non-negotiable misses trigger escalation
- De-escalation requires ALL criteria
- Can only de-escalate one level at a time
- Integration with existing escalation engine (read, not write)
- Level 3 queues recalibration
- Level 4 initiates recalibration conversation

### 9.2 Integration Test Scenarios

**I1. Full Chat Pipeline**
- Build CoS context → EAE arbitrate → verify prompt contains exactly N cognitive units → verify tone directive → verify Primary Focus included

**I2. DNE Pipeline**
- Collect delivery candidates → EAE arbitrate (channel=push) → verify max 1 item delivered → verify cross-channel dedup with recent chat

**I3. Briefing Pipeline**
- Generate daily briefing → EAE arbitrate (channel=briefing) → verify summary reflects top 5 → verify suppressed items listed

**I4. Escalation Cascade**
- Simulate 5-day drift increase → verify level transitions 0→1→2→3 → simulate recovery → verify de-escalation gates

**I5. Override Full Cycle**
- Simulate 3 pushbacks on medication reminder → verify TEMPORARY override → simulate 3 more rounds → verify auto-escalation to PERMANENT

**I6. Cross-Channel Coordination**
- Push medication reminder → within 4 hours, chat interaction → verify medication not re-surfaced in chat cognitive units

**I7. Budget Exhaustion**
- Generate 10+ signals → verify only 3 surface in chat → verify budget counter increments → verify remaining go to briefing

**I8. Governance Integration**
- Set module as non_negotiable → trigger drift in that module → verify EAE escalation is more aggressive than for flexible module

### 9.3 Regression Tests

**R1. Existing engines unaffected**
- PIE still generates insights (same count, same confidence) with EAE enabled
- PRIE still generates predictions unchanged
- PGE still generates guidance unchanged
- CDCE still detects correlations unchanged
- UAL still classifies scenarios unchanged
- DNE still delivers via all channels (EAE only filters candidates)
- DBE/WIRE still generate full snapshots in JSON fields

**R2. Token count does not increase**
- Compare `AIUsageLog.prompt_tokens` average before/after → must be equal or lower

**R3. Quality gate still applies**
- ICQG 72h suppression still works (EAE doesn't un-suppress)
- ICQG conflict detection still merges contradictions

**R4. Feature flag off = zero change**
- With `eae_enabled=False`, all current behavior is identical
- No additional queries, no prompt changes

### 9.4 Stress Tests

**S1. Signal Overload (8+ simultaneous signals)**
- User has: 3 missed medications, 2 critical insights, 1 critical prediction, 2 drift warnings, 1 deadline collision, 1 relationship event, 1 ECC commitment due
- Verify: Only 3–5 cognitive units surface, bundled correctly, highest priority first

**S2. Conflicting Signals**
- PIE says "weight trend up" (warning), PRIE says "weight will decrease by March" (positive)
- Verify: EAE detects conflict, surfaces higher-confidence one, suppresses other with reason code "CONFLICT_SUPPRESSED"

**S3. Rapid Escalation + De-escalation**
- Drift jumps from 20 to 80 in one event → verify immediate escalation to level 3
- Drift drops to 30 next day → verify de-escalation is gated (48h minimum)

**S4. Override Spam**
- User overrides 10 different signal types in one session
- Verify: Each tracked independently, no budget inflation, no performance degradation

**S5. Concurrent Channels**
- Chat + push + briefing all fire within 1 minute for same user
- Verify: Cross-channel dedup works, global budget shared correctly, no double-surfacing

**S6. New User (Cold Start)**
- User with no governance profile, no history, no drift
- Verify: EAE defaults gracefully (escalation 0, budget 3, no Primary Focus, REFLECTIVE_GENTLE tone)

**S7. Edge: All Signals Suppressed**
- User has permanently suppressed all signal types
- Verify: EAE returns empty cognitive units list, logs "ALL_SUPPRESSED" reason code, does not crash

**S8. Edge: Zero Signals**
- Stable user with no active insights, predictions, guidance
- Verify: EAE returns empty list, no Primary Focus, REFLECTIVE_GENTLE tone, logs "NO_SIGNALS"

### 9.5 Acceptance Criteria

1. EAE never surfaces more than `noise_budget_max` cognitive units per channel
2. EAE never changes Primary Focus more than 2 times per day
3. EAE's escalation level always matches drift band within 1 level
4. EAE's override state machine transitions are deterministic and logged
5. EAE adds zero LLM API calls
6. EAE reduces average prompt tokens by ≥ 10%
7. EAE arbitration completes in < 50ms (P95)
8. Existing engine outputs unchanged with EAE enabled
9. Feature flag `eae_enabled=False` produces zero behavior change
10. All 28 signal types from §1.1 are accounted for in EAE's input collection

---

## 10. PHASE 8 IMPLEMENTATION PLAN

### 10.1 Sub-Phases

#### Phase 8.1: Foundation (Models + Feature Flag)
**Scope:**
- Create `apps/core/ai_eae/` app with models: `EAEState`, `EAEDecisionLog`, `EAEOverride`, `EAEEscalationEvent`
- Create migrations
- Register in `INSTALLED_APPS`
- Create feature flag: `EAE_ENABLED` in `PersonalOperatingBlueprint` (default False)
- Write model unit tests
- **Independently deployable:** Yes — models exist but nothing reads/writes them yet

#### Phase 8.2: Signal Collector + Scorer
**Scope:**
- `signal_collector.py` — gather all 28 signal types into a unified `RawSignalSet`
- `scorer.py` — normalize each signal to 0–100 using §4 formula
- `dedup.py` — apply EAE-level dedup rules (§4.4)
- Unit tests for scoring, normalization, dedup
- **Independently deployable:** Yes — collector runs but output not consumed yet

#### Phase 8.3: Bundler + Budget Engine
**Scope:**
- `bundler.py` — detect bundle opportunities, create CognitiveUnit bundles
- `budget.py` — enforce per-channel caps, capacity adjustment, cross-channel tracking
- Unit tests for bundling and budget enforcement
- **Independently deployable:** Yes — budget engine runs but not wired to output yet

#### Phase 8.4: Escalation + Override Engine
**Scope:**
- `escalation.py` — drift band mapping, level transitions, de-escalation gates
- `override.py` — strike tracking, cooldown management, permanent suppression
- `tone.py` — tone band selection from escalation level + drift
- `focus.py` — Primary Focus set/change/lockout logic
- Unit tests for state machine transitions
- **Independently deployable:** Yes — state tracked but not surfaced yet

#### Phase 8.5: Core Arbitration Pipeline
**Scope:**
- `eae_engine.py` — main `arbitrate()` function that chains: collect → score → dedup → bundle → budget → escalation → tone → focus → output
- Produces `EAEDecision` dict
- Integration tests (I1–I8)
- **Independently deployable:** Yes — pipeline runs end-to-end but not inserted into actual flow yet

#### Phase 8.6: Chat Insertion
**Scope:**
- Modify `personal_assistant.py:_generate_response()` to call `eae_engine.arbitrate(channel="chat")` when `EAE_ENABLED`
- Replace raw CoS context injection with EAE's formatted output
- `format_for_prompt()` method on EAEDecision
- Override detection in `send_message()` response analysis
- Regression tests (R1–R4)
- **Independently deployable:** Yes, behind feature flag

#### Phase 8.7: DNE + Briefing Insertion
**Scope:**
- Modify `delivery_engine.py` to call `eae_engine.arbitrate(channel="push")` when `EAE_ENABLED`
- Modify `briefing_engine.py` to call `eae_engine.arbitrate(channel="briefing")` when `EAE_ENABLED`
- Cross-channel dedup implementation
- Integration tests for DNE and briefing pipelines
- **Independently deployable:** Yes, behind feature flag

#### Phase 8.8: Command Center + Telemetry
**Scope:**
- New panels in Command Center template (§7.1)
- New API endpoints for EAE dashboard data
- Heartbeat registration with ISE/observability
- Telemetry integration (§8.6)
- **Independently deployable:** Yes — additive UI only

#### Phase 8.9: Stress Testing + Tuning
**Scope:**
- Run all stress tests (S1–S8)
- Performance benchmarking (< 50ms P95)
- Token impact measurement
- Tune scoring weights based on initial data
- **Independently deployable:** N/A — testing phase

### 10.2 Feature Flag Strategy

**Flag location:** `PersonalOperatingBlueprint.eae_enabled` (BooleanField, default=False)

**Rollout plan:**
1. Phase 8.1–8.5: Flag off for everyone. Models and logic exist but are inert.
2. Phase 8.6: Enable for admin user (Danny) only via `eae_enabled=True` on his Blueprint
3. Phase 8.7–8.8: Still admin-only. Validate across all channels.
4. Phase 8.9: After stress testing passes, flip default to True for all users.

**Flag check pattern:**
```python
# At every insertion point:
blueprint = PersonalOperatingBlueprint.objects.filter(user=user).first()
if blueprint and blueprint.eae_enabled:
    decision = eae_engine.arbitrate(user=user, channel="chat", ...)
    # Use EAE output
else:
    # Use existing flow unchanged
```

### 10.3 Rollback Plan

**Per sub-phase rollback:**
- Each sub-phase is independently deployable → can revert that migration/code change alone
- Feature flag is the primary safety valve → set `eae_enabled=False` for immediate rollback
- EAE models are additive (new tables) → dropping them doesn't affect existing models
- EAE reads existing models (read-only) → no risk of corrupting existing data

**Emergency rollback:**
1. Set `PersonalOperatingBlueprint.eae_enabled = False` for all users (1 SQL update)
2. Deploy without EAE insertion point changes (revert 8.6/8.7 code)
3. EAE tables can remain (unused) or be dropped in separate migration

**Data preservation:**
- `EAEDecisionLog` is append-only → safe to keep for analysis even after rollback
- `EAEState` can be recreated from decision log if needed
- `EAEOverride` represents user preferences → preserve across rollback/re-enable

### 10.4 File Structure

```
apps/core/ai_eae/
├── __init__.py
├── apps.py
├── models.py              # EAEState, EAEDecisionLog, EAEOverride, EAEEscalationEvent
├── admin.py               # Admin views for EAE models
├── eae_engine.py          # Main arbitrate() pipeline
├── signal_collector.py    # Gather all 28 signal types
├── scorer.py              # Normalize to 0–100
├── dedup.py               # EAE-level deduplication
├── bundler.py             # Cognitive unit bundling
├── budget.py              # Noise budget enforcement
├── escalation.py          # Escalation ladder + transitions
├── override.py            # Override state machine
├── tone.py                # Tone band selection
├── focus.py               # Primary Focus management
├── formatter.py           # format_for_prompt() output
├── constants.py           # All thresholds, weights, caps
├── tests/
│   ├── __init__.py
│   ├── test_scoring.py
│   ├── test_bundling.py
│   ├── test_budget.py
│   ├── test_tone.py
│   ├── test_focus.py
│   ├── test_override.py
│   ├── test_escalation.py
│   ├── test_integration.py
│   ├── test_stress.py
│   └── test_regression.py
└── migrations/
    └── 0001_initial.py
```

---

## OPEN QUESTIONS (TO VERIFY IN CODE)

1. **CommitmentContract model location:** ECC commitment contracts referenced in `cos_context.py` — need to verify exact model name and app_label for signal collection.
2. **Drift per-module scores:** `cos_context.py` references pillar scores — need to verify if these are per-module or aggregate only.
3. **UAL is_enabled flag:** UAL currently runs unconditionally — verify if there's an existing feature flag or if EAE should wrap UAL invocation.
4. **GLOE responsiveness influence on PGE ranking:** Verify exact weight formula in `guidance_ranker.py` to ensure EAE doesn't double-count.
5. **Quiet hours in DNE:** Verify exact quiet hours implementation to ensure EAE budget doesn't count quiet-hour-suppressed items against the budget.

---

## DESIGN PRINCIPLES CHECKLIST

- [x] Compute everything, surface very little
- [x] Hard cap 3–5 cognitive units per interaction
- [x] Drift Risk Severity anchors arbitration (30% of normalized score)
- [x] Max 2 Primary Focus changes per day
- [x] Escalation is state-based, not emotional
- [x] User autonomy wins, consequences reflected and logged
- [x] 3-strike override doctrine with permanent/temporary/ambiguous classification
- [x] Deterministic decisions (zero LLM calls in EAE)
- [x] Engines score locally; EAE normalizes globally (hybrid model)
- [x] Preserves all existing engine behavior
- [x] Feature-flagged, independently deployable sub-phases

---

**WAITING FOR APPROVAL TO IMPLEMENT**
