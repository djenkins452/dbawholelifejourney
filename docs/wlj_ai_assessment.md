# ==============================================================================
# File: docs/wlj_ai_assessment.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: AI Usage Assessment and Optimization Recommendations
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================

# AI Assessment Report - Whole Life Journey

## Executive Summary

This assessment analyzes how the Whole Life Journey application uses AI (OpenAI API) and identifies opportunities to optimize API calls through improved caching strategies. The goal is to **reduce costs and improve performance without sacrificing any features**.

**Key Finding:** The application has a solid foundation with database-driven caching, but several opportunities exist to reduce redundant API calls and improve efficiency.

---

## Current Architecture Overview

### AI Components

| Component | File | Purpose |
|-----------|------|---------|
| **AIService** | `services.py` | Core OpenAI API wrapper with database-driven prompts |
| **DashboardAI** | `dashboard_ai.py` | Dashboard-specific insights with daily caching |
| **PersonalAssistant** | `personal_assistant.py` | Action-focused daily assistant with state tracking |
| **TrendTracker** | `trend_tracking.py` | Weekly/monthly analysis and pattern detection |

### Data Models (Caching)

| Model | Purpose | Current Cache Strategy |
|-------|---------|------------------------|
| **CoachingStyle** | AI personality styles | Django cache (1 hour TTL) |
| **AIPromptConfig** | System prompt configurations | Django cache (1 hour TTL) |
| **AIInsight** | Generated insights | Database with `valid_until` |
| **UserStateSnapshot** | Daily user state | One per user per day |
| **TrendAnalysis** | Weekly/monthly trends | One per period |
| **DailyPriority** | AI-suggested priorities | One set per user per day |
| **ReflectionPromptQueue** | Journaling prompts | Queue with shown/used tracking |

---

## Current API Call Patterns

### Call Sites Inventory

| Feature | Location | Current Caching | Estimated Calls/Day/User |
|---------|----------|-----------------|--------------------------|
| Daily Insight | `dashboard_ai.py:34` | Until end of day + coaching style | 1-2 |
| Weekly Summary | `dashboard_ai.py:76` | 24 hours + coaching style | 0-1 |
| Journal Reflection | `services.py:237` | **NONE** | 0-5 |
| Accountability Nudge | `services.py:370` | **NONE** | 0-3 |
| Celebration Message | `services.py:405` | **NONE** | 0-2 |
| Goal Progress | `services.py:438` | **NONE** | 0-2 |
| Health Encouragement | `services.py:465` | **NONE** | 0-1 |
| Prayer Encouragement | `services.py:502` | **NONE** | 0-1 |
| State Assessment | `personal_assistant.py:347` | Daily snapshot | 1-5 |
| PA Responses | `personal_assistant.py:1291` | **NONE** | 1-10 |
| Weekly Analysis | `trend_tracking.py:59` | One per week | 0-1 |
| Monthly Analysis | `trend_tracking.py:491` | One per month | 0-1 |

### Identified Issues

1. **Repeated System Prompt Building**: Every API call rebuilds the system prompt from scratch, including:
   - Database lookups for `AIPromptConfig` (cached 1hr)
   - Database lookups for `CoachingStyle` (cached 1hr)
   - Profile moderation processing
   - Faith context assembly

2. **Redundant Data Gathering**:
   - `_gather_user_data()` runs full queries each time
   - Same data gathered multiple times per request
   - No request-level caching

3. **No Caching for Per-Entry Insights**:
   - Journal reflections generated fresh each time
   - Nudges/celebrations not cached
   - Goal progress insights regenerated on every view

4. **State Assessment Overcalling**:
   - `assess_current_state()` called multiple times per session
   - Fresh task queries even when snapshot exists

---

## Optimization Recommendations

### HIGH PRIORITY - Implement These First

#### 1. Add Request-Level Caching for User Data Gathering

**Problem:** `_gather_user_data()` and `_gather_comprehensive_state()` run expensive queries that could be called multiple times per request.

**Solution:** Add `@cached_property` or request-level caching.

```python
# Before: Called multiple times, each time hitting DB
data = self._gather_user_data()  # ~10 queries

# After: Cache for the request lifecycle
@cached_property
def user_data(self):
    return self._gather_user_data()
```

**Estimated Savings:** 30-50% reduction in DB queries per request

#### 2. Cache Journal Entry Reflections

**Problem:** Every time a user views a journal entry, a new reflection is generated.

**Solution:** Store reflections with the journal entry and only regenerate if content changes.

```python
# Add to JournalEntry model or create AIInsight:
class JournalEntry:
    ai_reflection = models.TextField(blank=True)
    ai_reflection_at = models.DateTimeField(null=True)

    def get_ai_reflection(self):
        if self.ai_reflection and self.ai_reflection_at > self.updated_at:
            return self.ai_reflection  # Return cached
        # Generate new and save
```

**Estimated Savings:** 80-90% reduction in journal reflection API calls

#### 3. Batch System Prompt Components

**Problem:** System prompt is rebuilt from scratch for every call.

**Solution:** Pre-build and cache the static parts of system prompts.

```python
# Cache the base + coaching style + faith context combination
def get_cached_system_prompt(user):
    cache_key = f'system_prompt_{user.id}_{user.preferences.ai_coaching_style}'
    prompt = cache.get(cache_key)
    if not prompt:
        prompt = ai_service._get_system_prompt(
            faith_enabled=user.preferences.faith_enabled,
            coaching_style=user.preferences.ai_coaching_style
        )
        cache.set(cache_key, prompt, 3600)  # 1 hour
    return prompt
```

**Estimated Savings:** 20-30% reduction in prompt building overhead

### MEDIUM PRIORITY

#### 4. Cache Nudges and Celebrations

**Problem:** Accountability nudges and celebration messages are generated fresh each time.

**Solution:** Cache by context hash.

```python
# Create a hash of the context and cache the result
import hashlib

def get_cached_nudge(gap_data, faith_enabled, coaching_style):
    context_hash = hashlib.md5(
        f"{gap_data}{faith_enabled}{coaching_style}".encode()
    ).hexdigest()[:8]

    cache_key = f'nudge_{context_hash}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    result = ai_service.generate_accountability_nudge(...)
    cache.set(cache_key, result, 3600)  # 1 hour
    return result
```

**Estimated Savings:** 50-70% reduction in nudge/celebration calls

#### 5. Invalidate Caches Smartly on Preference Changes

**Problem:** When user changes coaching style, old cached insights should be invalidated but aren't always.

**Solution:** Add signal handler for preference changes.

```python
from django.db.models.signals import post_save

@receiver(post_save, sender=UserPreferences)
def invalidate_ai_caches(sender, instance, **kwargs):
    user = instance.user
    # Clear user-specific cached insights
    AIInsight.objects.filter(
        user=user,
        coaching_style__ne=instance.ai_coaching_style,
        valid_until__gt=timezone.now()
    ).update(valid_until=timezone.now())
```

#### 6. Add Query Optimization with select_related/prefetch_related

**Problem:** N+1 queries when loading user data.

**Solution:** Optimize view queries.

```python
# In dashboard view
user = User.objects.select_related('preferences').get(id=request.user.id)
```

### LOWER PRIORITY

#### 7. Implement Retry Logic with Fallback

**Problem:** Failed API calls return None with no retry.

**Solution:** Add exponential backoff and cache fallback.

```python
def _call_api_with_retry(self, system_prompt, user_prompt, max_tokens=300, retries=2):
    for attempt in range(retries + 1):
        try:
            result = self._call_api(system_prompt, user_prompt, max_tokens)
            if result:
                return result
        except Exception as e:
            if attempt < retries:
                time.sleep(2 ** attempt)  # Exponential backoff
    return None
```

#### 8. Token Counting Before API Calls

**Problem:** No visibility into token usage before calls.

**Solution:** Add tiktoken for pre-counting.

```python
import tiktoken

def count_tokens(text, model="gpt-4o-mini"):
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))

# Before calling API
if count_tokens(system_prompt + user_prompt) > 8000:
    # Truncate or summarize
```

---

## Implementation Plan

### Phase 1: Quick Wins (This Session)
1. ✅ Add user data caching to DashboardAI
2. ✅ Add system prompt caching
3. ✅ Cache journal entry reflections
4. ✅ Update tests

### Phase 2: Medium-Term (Future Session)
1. Add signal-based cache invalidation
2. Implement nudge/celebration caching
3. Add query optimization

### Phase 3: Long-Term (Future Session)
1. Implement retry logic
2. Add token counting
3. Add background task generation (Celery)

---

## Cost Estimate

### Current (Estimated for 100 Active Users)

| Feature | Calls/Day | Tokens/Call | Cost/Day | Cost/Month |
|---------|-----------|-------------|----------|------------|
| Daily Insights | 100 | 650 | $0.10 | $3.00 |
| PA Messages | 500 | 1100 | $0.55 | $16.50 |
| Journal Reflections | 300 | 500 | $0.15 | $4.50 |
| Weekly Summaries | 25 | 1150 | $0.03 | $0.90 |
| Nudges/Celebrations | 200 | 500 | $0.10 | $3.00 |
| Trend Analysis | 50 | 2200 | $0.11 | $3.30 |
| **TOTAL** | **1175** | - | **$1.04** | **$31.20** |

### After Optimization (Estimated)

| Feature | Reduction | New Cost/Month |
|---------|-----------|----------------|
| Daily Insights | 0% (already cached) | $3.00 |
| PA Messages | 10% (better state caching) | $14.85 |
| Journal Reflections | 80% (entry-level cache) | $0.90 |
| Weekly Summaries | 0% (already cached) | $0.90 |
| Nudges/Celebrations | 60% (context caching) | $1.20 |
| Trend Analysis | 0% (already cached) | $3.30 |
| **TOTAL** | **~25%** | **$24.15** |

**Estimated Monthly Savings: ~$7/month** (scales with user count)

---

## Appendix: Files to Modify

1. `apps/ai/services.py` - Add system prompt caching
2. `apps/ai/dashboard_ai.py` - Add request-level caching
3. `apps/ai/personal_assistant.py` - Optimize state assessment
4. `apps/journal/models.py` - Add ai_reflection field (optional)
5. `apps/ai/models.py` - No changes needed (already well-designed)

---

*Report generated: 2025-12-31*
