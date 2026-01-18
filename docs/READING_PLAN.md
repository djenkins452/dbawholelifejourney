# Reading Plan Creation Guide

This document provides instructions for Claude to create Reading Plans from sermon content.

---

## Overview

Reading Plans are multi-day devotional journeys based on sermon series. They include:
- Daily scripture references (clickable links to Bible lookup)
- Devotional text (humanized, no markdown formatting)
- Reflection prompts
- Optional interactive assessments with scoring

---

## Hierarchy Structure

Reading Plans follow this organizational hierarchy:

```
Church/Source (e.g., "Seymour Heights Christian Church")
  └── Series (e.g., "Blind Spots")
        └── Week 1: "The Control Issue"
        └── Week 2: "Surrendering My Blind Spots"
        └── Week 3: ...
```

**Current Implementation:**
- Each week is a separate `ReadingPlanTemplate` with its own slug
- The `description` field should reference the series and week number
- Use `topics` field to group plans from the same series (e.g., `["blind-spots-series", "control", "trust"]`)

**Naming Convention:**
- Title: "[Theme/Topic Name]" (e.g., "Surrendering My Blind Spots")
- Slug: `[series]-[topic]` (e.g., `blind-spots-control`, `blind-spots-surrender`)
- Description: "Week X of [Series Name] at [Church]. [Brief description]."

---

## Input Requirements

To create a reading plan, provide:

1. **Sermon Summary** (optional but helpful)
   - Key themes and main points
   - Scripture references mentioned

2. **Sermon Transcript** (preferred)
   - Full text of the sermon
   - Claude will extract scriptures, key quotes, and teaching points

3. **Metadata**
   - Church/Source name
   - Series name
   - Week number in series
   - Sermon title (if different from week theme)

---

## Processing Instructions

### Step 1: Extract Key Elements

From the transcript/summary, identify:

1. **All Scripture References**
   - Note the exact verses read or referenced
   - Capture the full passage range (e.g., Matthew 6:25-32, not just "Matthew 6")
   - These become clickable links in the reading plan

2. **Main Teaching Points**
   - The core message/theme
   - Supporting sub-points
   - These structure the daily devotionals

3. **Memorable Quotes**
   - Direct quotes from the pastor
   - Use these naturally in devotional text (no `**` formatting)

4. **Practical Applications**
   - Action items or challenges given
   - These inform reflection prompts

5. **Assessment Questions** (if applicable)
   - Self-evaluation questions from the sermon
   - Scoring criteria if mentioned

### Step 2: Structure the Reading Plan

**Duration:** Typically 5-7 days based on content depth

**Day Structure Pattern:**
- Day 1: Introduction/Awareness (often includes assessment if applicable)
- Days 2-4: Deep dive into main teaching points
- Day 5-6: Application and practical steps
- Final Day: Commitment/Response

**For Each Day, Create:**

1. **Title** - Short, descriptive (e.g., "The Root of Control - Worry")

2. **Scripture References** (JSON array)
   - List all passages to read that day
   - Use standard format: "Book Chapter:Verse-Verse"
   - Examples: `["Matthew 6:25-27"]`, `["Genesis 2:15-25", "Genesis 3:1-7"]`

3. **Devotional Text**
   - 200-400 words
   - **NO MARKDOWN FORMATTING** - no `**`, `*`, `#`, etc.
   - Write in plain, conversational prose
   - Include relevant quotes naturally (use quotation marks)
   - Structure with paragraph breaks for readability
   - End with "Prayer Focus:" section

4. **Reflection Prompt**
   - 2-4 questions for personal reflection
   - Make them specific and actionable
   - Connect to the day's scripture and teaching

### Step 3: Create Assessment (If Applicable)

If the sermon includes a self-assessment or quiz:

**Assessment Structure:**
```json
{
  "title": "Assessment Name",
  "description": "Instructions for taking the assessment",
  "questions": [
    {
      "id": "1",
      "text": "Question text here?",
      "min_label": "Never",
      "mid_label": "Sometimes",
      "max_label": "Always/That's me"
    }
  ],
  "score_ranges": [
    {
      "min": 40,
      "max": 50,
      "label": "Category Label",
      "description": "What this score means..."
    }
  ]
}
```

- Link assessment to Day 1 (or appropriate day)
- Use 1-5 scale unless sermon specifies otherwise
- Include 3-4 score interpretation ranges

---

## Technical Implementation

### Files to Create/Update

1. **Fixture File:** `apps/faith/fixtures/[series]_[week]_reading_plan.json`

2. **Add to Loader:** Update `apps/core/management/commands/load_initial_data.py`:
   ```python
   {
       'name': '[fixture_name]',
       'display': '[Display Name]',
       'description': '[Brief description]',
   },
   ```

3. **Migration (if updating existing):** Create data migration to update database

### Fixture Structure

```json
[
  {
    "model": "faith.readingplantemplate",
    "pk": [unique_id],
    "fields": {
      "title": "Plan Title",
      "slug": "plan-slug",
      "description": "Full description with series/week context",
      "category": "devotional",
      "difficulty": "beginner",
      "duration_days": 6,
      "image_url": "",
      "topics": ["topic1", "topic2", "series-name"],
      "is_active": true,
      "is_featured": true,
      "created_at": "2026-01-18T00:00:00Z",
      "updated_at": "2026-01-18T00:00:00Z"
    }
  },
  {
    "model": "faith.readingplanday",
    "pk": [unique_id],
    "fields": {
      "plan": [template_pk],
      "day_number": 1,
      "title": "Day Title",
      "scripture_references": ["Reference 1", "Reference 2"],
      "reflection_prompt": "Reflection questions here",
      "devotional_text": "Full devotional text with proper line breaks..."
    }
  }
]
```

### Primary Key Conventions

To avoid conflicts:
- ReadingPlanTemplate: Start at 100, increment by 1 per plan
- ReadingPlanDay: Use [template_pk * 10 + day_number] pattern
  - Template 100: Days 1001-1006
  - Template 101: Days 1011-1016
  - Template 102: Days 1021-1026
- ReadingPlanAssessment: Increment from 1

---

## Quality Checklist

Before finalizing a reading plan:

- [ ] All scripture references are complete and accurate
- [ ] No markdown formatting (`**`, `*`, `#`) in devotional text
- [ ] Devotional text uses proper paragraph breaks (`\n\n`)
- [ ] Reflection prompts are specific and actionable
- [ ] Prayer Focus included at end of each devotional
- [ ] Series/week context included in description
- [ ] Topics include series identifier for grouping
- [ ] Assessment questions match sermon content (if applicable)
- [ ] Score interpretations are encouraging and actionable

---

## Example Prompt for New Plan

```
Read CLAUDE.md and docs/READING_PLAN.md

Create a reading plan from this sermon:

**Church:** Seymour Heights Christian Church
**Series:** Blind Spots
**Week:** 1
**Title:** The Control Issue

[Paste sermon summary and/or transcript here]
```

---

## Existing Plans Reference

| Series | Week | Title | Slug | Template PK |
|--------|------|-------|------|-------------|
| Blind Spots | 2 | Surrendering My Blind Spots | surrendering-blind-spots | 100 |

---

## Future Enhancements (Ideas)

1. **Series Model** - Create `ReadingPlanSeries` to formally group plans
2. **Church/Source Model** - Track content sources
3. **Progress Across Series** - Show completion of full series
4. **Series Landing Page** - Browse all weeks in a series together

---

*Last Updated: 2026-01-18*
