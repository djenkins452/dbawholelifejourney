# CoS Intelligence Upgrade Plan

**Created:** 2026-02-25
**Goal:** Make CoS as contextually aware and intelligent as Claude Code / ChatGPT
**Status:** ALL PHASES COMPLETE (1a, 1b, 1c, 2a, 2b, 3a, 3b, 4a, 4b, 4c)

---

## Problem Statement

CoS sometimes loses context and gives irrelevant responses. Example: user is on a Bible reading plan page reading Matthew 12 about Jesus and the Sabbath, asks "what does this mean for the Sabbath?" and CoS responds about their work routines instead of the scripture. A real chief of staff would never make this mistake.

## Current Architecture Audit

| Capability | CoS Today | Claude Code / ChatGPT |
|---|---|---|
| **Model** | gpt-4o (response) + gpt-4o-mini (intent) | Claude Opus 4.6 / GPT-4o |
| **Context window** | 15 messages (~3K tokens of history) | 200K tokens |
| **Response length** | 250-600 tokens max | Unlimited |
| **Page awareness** | CSS selector scraping (fragile) | Full file/codebase access |
| **Session memory** | Rolling 15 messages, no cross-session | Full conversation |
| **Self-correction** | None | Detects own mistakes |
| **Multi-step reasoning** | Single intent → single response | Chain of thought, planning |
| **Knowledge retrieval** | No RAG, no vector search | Can search/read anything |
| **Action capabilities** | Good — 14 intent modules, creates tasks/logs data | Deep tool use |

**Key files:**
- System prompt & personality: `apps/ai/personal_assistant.py` (lines 46-356)
- Intent recognition: `apps/ai/intent_service.py`
- Intent modules: `apps/ai/intents/` (14 modules)
- Action handlers: `apps/ai/action_handlers.py`
- Context gathering: `apps/core/ai_orchestrator/cos_context.py`
- Executive briefing: `apps/ai/executive_briefing.py`
- Learning/profile: `apps/core/ai_learning/learning_extractor.py`
- Governance: `apps/core/blueprint/cos_governance.py`

---

## Implementation Plan

### Phase 1: Immediate Intelligence Upgrades (High Impact, Low Effort)

#### 1a. Increase Context Window + Response Tokens
**Impact:** High | **Effort:** Low (config changes)

Current limits are too restrictive:
- Chat history: 15 → 30-40 messages
- Response tokens: brief 250→400, adaptive 450→800, deep 600→1200

**Files:** `apps/ai/personal_assistant.py` (lines 2960, 3597)

**Cost consideration:** More tokens per request = higher API cost. Monitor via telemetry.

#### 1b. Context-Priority Routing (Pre-Response Disambiguation)
**Impact:** Critical — fixes the Sabbath-type failures | **Effort:** Medium

Before generating a response, add a lightweight classification step:

```
Given:
- Page context: [reading plan, Matthew 12, Sabbath healing]
- Last conversation: [created Approve Payroll routine task]
- User message: "what does this mean for the Sabbath"

What is the user asking about?
A) The scripture they're reading (page context)
B) The task/routine just discussed (conversation context)
→ Answer: A
```

Implementation approach:
- Add `_resolve_context_priority()` method in `personal_assistant.py`
- When page context exists AND user message could apply to either page or conversation, prepend a disambiguation instruction to the system prompt
- For reading plans specifically: if ANY faith/scripture/theological keyword appears, force page context priority

**Files:** `apps/ai/personal_assistant.py`

#### 1c. Richer Page Content Capture
**Impact:** Medium | **Effort:** Medium

Generalize the scripture text fix across all page types. For every page, capture what the user is *actually looking at*, not just metadata:
- Reading plans: actual verse text (done — 2026-02-25)
- Journal entries: full entry body (may already exist)
- Health pages: visible charts/data tables
- Goal pages: milestone list, progress details
- Task pages: task details, notes

**Files:** `templates/components/chat_widget.html`

---

### Phase 2: Session Awareness (Medium Effort)

#### 2a. Session Activity Tracking
**Impact:** High | **Effort:** Medium

Track page visits in the current browser session. When user opens CoS chat, inject recent navigation:

```
Session Activity (last 10 minutes):
- 5:42 AM: Faith > Reading Plans > Journey Through Matthew
- 5:43 AM: Expanded scripture: Matthew 12:1-50
- 5:48 AM: Opened CoS chat
```

Implementation:
- Add lightweight session tracking in `chat_widget.html` (store last N page visits in sessionStorage)
- Send `session_activity` array with chat messages
- Inject into system prompt as temporal context

**Files:** `templates/components/chat_widget.html`, `apps/ai/personal_assistant.py`

#### 2b. Conversation Topic Threading
**Impact:** Medium | **Effort:** Medium

Before responding, classify whether the user is:
- Continuing a previous conversation thread
- Starting a new topic (signaled by page change + topic shift)
- Asking about the page they're currently viewing

When topic shifts are detected, reset conversation weighting so old topics don't dominate.

**Files:** `apps/ai/personal_assistant.py`

---

### Phase 3: Long-Term Memory (Higher Effort)

#### 3a. Conversation Memory with Vector Search (RAG)
**Impact:** Very High | **Effort:** High

Store past conversations with vector embeddings (OpenAI embeddings API or similar). When user asks something, retrieve the 3-5 most relevant past exchanges:

- "Last Tuesday you mentioned struggling with consistency in your Quiet Time..."
- "Remember when you said you wanted to focus more on prayer this month?"

Implementation:
- Add embedding model (OpenAI `text-embedding-3-small`)
- Store embeddings for each conversation turn in a new model (e.g., `ConversationEmbedding`)
- On each new message, embed the query, retrieve top-K similar past messages
- Inject retrieved context into system prompt under "RELEVANT PAST CONVERSATIONS"

**New files:** `apps/ai/memory_service.py`, migration for embedding storage
**Modified:** `apps/ai/personal_assistant.py`

**Alternative:** Use pgvector extension for PostgreSQL (already using PostgreSQL in prod)

#### 3b. Expanded Learned Patterns
**Impact:** Medium | **Effort:** Medium

Extend the learning extractor to capture:
- Conversation patterns (what topics user asks about most)
- Preferred explanation depth (brief vs. detailed)
- Topics that should always reference page context (faith, health data)
- Time-of-day behavioral patterns (morning = routines, evening = reflection)

**Files:** `apps/core/ai_learning/learning_extractor.py`

---

### Phase 4: Reasoning Quality (Architecture Change)

#### 4a. Pre-Response Reasoning Step ("Think Before Speaking")
**Impact:** High | **Effort:** Medium

Before generating the final response, add an internal reasoning step:

```
System: Before responding, briefly reason about:
1. What is the user's current context? (page, time, recent activity)
2. What are they most likely asking about?
3. What data do I have that's relevant?
4. What should I NOT talk about? (avoid mixing unrelated topics)
Then respond.
```

This uses "chain of thought" prompting to improve reasoning quality. The reasoning isn't shown to the user — just the final response.

**Files:** `apps/ai/personal_assistant.py` (system prompt construction)

**Cost:** Slightly higher token usage per response (reasoning tokens + response tokens)

#### 4b. Model Upgrade Consideration
**Impact:** Very High | **Effort:** Low (config change, higher cost)

Options:
1. **Use gpt-4o consistently** (not gpt-4o-mini for intent) — better reasoning everywhere
2. **Use Claude API** (Anthropic) — same quality as this conversation. Claude Sonnet 4 for routine, Claude Opus 4 for complex questions
3. **Hybrid approach** — Use cheaper model for simple lookups, better model for complex reasoning

**Cost impact:** ~2-4x per request for model upgrade. Monitor via telemetry and set budget alerts.

**Files:** `config/settings.py`, `apps/ai/intent_service.py`, `apps/ai/services.py`

#### 4c. Response Quality Validation
**Impact:** Medium | **Effort:** Medium

After generating a response, do a lightweight validation:
- Does this response reference the page context when page context exists?
- Does it answer what the user asked (not a tangent)?
- Is it consistent with the user's current activity?

If validation fails, regenerate with stronger context emphasis.

**Cost:** ~1.5x per response (extra validation call). Only trigger on ambiguous queries.

**Files:** `apps/ai/personal_assistant.py`

---

## Implementation Priority

| Priority | Item | Impact | Effort | Dependencies |
|---|---|---|---|---|
| **1** | 1b: Context-priority routing | Critical | Medium | None |
| **2** | 1a: Increase context window + tokens | High | Low | None |
| **3** | 4a: Pre-response reasoning step | High | Medium | None |
| **4** | 1c: Richer page content capture | Medium | Medium | None |
| **5** | 2a: Session activity tracking | High | Medium | None |
| **6** | 4b: Model upgrade consideration | Very High | Low | Cost approval |
| **7** | 2b: Topic threading | Medium | Medium | 2a |
| **8** | 3a: Conversation memory (RAG) | Very High | High | pgvector or embedding storage |
| **9** | 3b: Expanded learned patterns | Medium | Medium | 3a |
| **10** | 4c: Response validation | Medium | Medium | 4a |

---

## Cost Projections

Current CoS API cost: ~$X/month (check telemetry)

Estimated increases:
- Phase 1 (context + tokens): +30-50% per request
- Phase 2 (session tracking): +10% (more context in prompt)
- Phase 3 (RAG): +20% (embedding calls + retrieval)
- Phase 4 (reasoning + validation): +40-80% per request

Total estimated increase: 2-3x current cost for significantly better quality.

---

## Success Metrics

1. **Context accuracy:** CoS references the correct context (page vs. conversation) >95% of the time
2. **User satisfaction:** Fewer "that's not what I asked" moments
3. **Reasoning depth:** Responses demonstrate understanding of the user's situation, not just keyword matching
4. **Memory recall:** CoS can reference relevant past conversations when appropriate
5. **No hallucination:** CoS never fabricates data or misattributes context
