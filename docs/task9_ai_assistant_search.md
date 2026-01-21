# Task 9: Enhanced AI Assistant - Intelligent Search & Query Gateway

**Status:** In Progress
**Created:** 2026-01-20
**Last Updated:** 2026-01-20

---

## Vision

The AI Assistant becomes the single intelligent gateway to everything in Whole Life Journey:
1. **Personal Data First** - Search Journal, Health, Goals, Faith, Organize, Finance, Capture
2. **External APIs Second** - Connected data sources (future integrations)
3. **General Knowledge Third** - OpenAI responses filtered through WLJ values

All interactions are filtered through WLJ culture: faith-positive, wellness-focused, encouraging, and protective of user dignity.

---

## Sub-Tasks

### Sub-Task 9.1: Search Service Infrastructure
**Status:** ✅ Complete
**Scope:** Build search services for each module

Create `apps/ai/services/search_service.py` with methods:
- `search_journal(user, keywords, date_range, mood, tags, limit)`
- `search_health(user, metric_type, date_range, limit)`
- `search_goals(user, keywords, status, limit)`
- `search_faith(user, keywords, content_type, limit)` - prayers, scriptures, readings
- `search_organize(user, keywords, item_type, status, limit)` - tasks, projects, events, inventory
- `search_finance(user, keywords, transaction_type, date_range, limit)`
- `search_capture(user, keywords, date_range, limit)`
- `search_all(user, keywords, limit)` - Global search across all modules

Each method returns standardized results:
```python
{
    "module": "journal",
    "count": 5,
    "results": [
        {
            "id": 123,
            "title": "Entry title or summary",
            "snippet": "Matching text excerpt...",
            "date": "2026-01-15",
            "url": "/journal/entry/123/",
            "metadata": {}  # Module-specific extra data
        }
    ]
}
```

---

### Sub-Task 9.2: Intent Detection & Query Parsing
**Status:** Pending
**Scope:** Detect search intent and extract query parameters

Create `apps/ai/services/intent_service.py`:

**Intent Categories:**
- `SEARCH_PERSONAL` - Searching user's own data
- `SEARCH_HELP` - Looking for app guidance/how-to
- `CONVERSATION` - General chat/coaching
- `INAPPROPRIATE` - Content that violates WLJ values

**Query Parser extracts:**
- `module_hint` - Which module(s) to search (or "all")
- `keywords` - Search terms
- `date_range` - start/end dates if mentioned
- `filters` - status, mood, type, etc.

**Example parses:**
```
"Show me journal entries about anxiety from last month"
→ module=journal, keywords=["anxiety"], date_range=(2025-12-21, 2026-01-20)

"What were my weight readings this week?"
→ module=health, metric=weight, date_range=(2026-01-13, 2026-01-20)

"Find tasks due tomorrow"
→ module=organize, item_type=task, date_range=(2026-01-21, 2026-01-21)
```

---

### Sub-Task 9.3: WLJ Values Guardrails
**Status:** Pending
**Scope:** Content filtering aligned with WLJ culture

Create `apps/ai/services/values_filter.py`:

**Input Filtering:**
- Detect inappropriate requests (explicit content, harmful intent)
- Categorize: `ALLOWED`, `REDIRECT`, `REFUSE`

**Redirect responses:**
- Gentle, non-judgmental tone
- Suggest positive alternatives
- "Have you explored our Faith module? We have some wonderful reading plans."
- "I'm here to support your wellness journey. How can I help with that?"

**Output Filtering:**
- Ensure AI responses align with WLJ values
- Remove/modify content that conflicts with faith-positive, wellness focus

**Configurable via admin:**
- Blocked keywords/patterns
- Redirect suggestions
- Severity levels

---

### Sub-Task 9.4: Enhanced Message Processing
**Status:** Pending
**Scope:** Integrate search and filtering into chat flow

Modify `apps/ai/personal_assistant.py`:

**New flow in `process_message()`:**
```python
1. Check values filter (input)
   - If REFUSE: Return graceful refusal
   - If REDIRECT: Return redirect message

2. Detect intent
   - If SEARCH_PERSONAL: Execute search, inject results
   - If SEARCH_HELP: Use help article search
   - If CONVERSATION: Continue to AI

3. Build context with search results (if any)

4. Call OpenAI with enhanced context

5. Check values filter (output)

6. Return response
```

---

### Sub-Task 9.5: Result Presentation & Formatting
**Status:** Pending
**Scope:** Format search results for conversational display

The AI should present results naturally:
- Summarize count: "I found 5 journal entries about stress..."
- Show highlights with dates and snippets
- Provide links to view full items
- Offer to narrow/expand search

**Chat widget enhancements:**
- Render clickable result cards
- "View more" pagination for large result sets
- Quick action buttons (view, edit, etc.)

---

### Sub-Task 9.6: Testing & Refinement
**Status:** Pending
**Scope:** Comprehensive testing of search and filtering

**Test cases:**
- Search queries across all modules
- Date range parsing (relative: "last week", absolute: "January 15")
- Multi-module searches ("search everything for vacation")
- Inappropriate content handling
- Edge cases (empty results, very large results)
- Performance with large datasets

---

## Implementation Order

1. **9.1 Search Infrastructure** - Foundation for all searches
2. **9.3 Values Guardrails** - Safety first
3. **9.2 Intent Detection** - Route queries correctly
4. **9.4 Message Processing** - Wire it all together
5. **9.5 Result Presentation** - Polish the UX
6. **9.6 Testing** - Ensure quality

---

## Technical Notes

### Existing Code to Leverage
- `PersonalAssistant._get_*_state()` methods already query each module
- `HelpChatService.search_articles()` pattern for full-text search
- `NotificationService` patterns for cross-module queries

### Database Indexes Needed
- Journal: `body` full-text, `created_at`
- Health models: metric + `recorded_at`
- Tasks: `title`, `description`, `due_date`
- Prayers: `title`, `content`, `status`

### Performance Considerations
- Limit results per module (default 10)
- Use Django's `SearchVector` for full-text where available
- Cache common searches briefly
- Consider background indexing for large datasets

---

## Progress Log

### 2026-01-20
- Created design document
- Defined 6 sub-tasks
- Established implementation order
- Completed Sub-Task 9.1: Search Service Infrastructure
  - Created `apps/ai/search_service.py` with SearchService class
  - Implemented search methods for all 7 modules (Journal, Health, Goals, Faith, Organize, Finance, Capture)
  - Created comprehensive test suite (21 tests passing)
  - Standardized result format with id, title, snippet, date, url, metadata
- Next: Sub-Task 9.3 (WLJ Values Guardrails)

---

## Files Modified/Created

| File | Purpose | Sub-Task |
|------|---------|----------|
| `apps/ai/search_service.py` | Module search methods | 9.1 ✅ |
| `apps/ai/tests/test_search_service.py` | Search service tests | 9.1 ✅ |
| `apps/ai/intent_service.py` | Intent detection & parsing | 9.2 |
| `apps/ai/values_filter.py` | WLJ culture guardrails | 9.3 |
| `apps/ai/personal_assistant.py` | Enhanced message flow | 9.4 |
| `templates/components/chat_widget.html` | Result rendering | 9.5 |
| `apps/ai/tests/test_values_filter.py` | Filter tests | 9.6 |
