# Improvement Tasks - Prioritized Backlog

**Created:** 2026-01-20
**Status:** Active - Working through with user dialog

---

## Task List (Priority Order)

### Task 1: Add Sleep Tracking to Health Module
**Status:** ✅ Complete
**Impact:** High - Sleep is a fundamental health metric
**Completed:** 2026-01-20

### Task 2: Add Goal Progress/Milestones to Purpose Module
**Status:** ✅ Complete
**Impact:** High - Goals feel abandoned without visible progress
**Completed:** 2026-01-20

**Scope (completed):**
- **2A:** Core milestone model + progress visuals + encouragement stat + auto-complete prompt + celebration modal + SMS reminders
- **2B:** Dashboard goal progress widget with visual treatment + Quarterly Review dismissible tile
- **2C:** AI integration - journal/milestone cross-referencing and proactive coaching

**Deferred to Future Task:**
- **Year in Review Feature** - Comprehensive annual review appearing Dec 31/Jan 1 with:
  - In-depth analysis of the year's accomplishments across all modules
  - Goals completed, milestones achieved, journal insights
  - Health trends, faith journey, purpose progress
  - Prompts user for next year's planning and annual direction
  - Should be a rich, celebratory, reflective experience
  - Consider: exportable summary, shareable achievements, goal-setting wizard for new year

### Task 3: Add Recurring Transactions to Finance Module
**Status:** ✅ Complete
**Impact:** High - All finance entry is manual
**Completed:** 2026-01-20

**Scope (completed):**
- **3A:** RecurringTransaction model + RecurringTransactionService for generating instances
- **3B:** Forms + Views + Templates for managing recurring transactions
- **3C:** Management command + Dashboard widget for upcoming recurring

### Task 4: Implement Daily Reminders for Faith Module
**Status:** ✅ Complete
**Impact:** High - Model fields exist but aren't being used
**Completed:** 2026-01-20

**Scope (completed):**
- Added `generate_faith_reminders` scheduled job to wsgi.py (daily at 6 AM UTC)
- Job calls existing `generate_daily_reminders` management command
- Creates in-app/email notifications for prayers with `remind_daily=True`
- Creates notifications for active reading plans not yet completed
- Respects all user preference toggles

### Task 5: Add Quick-Capture Journal Mode
**Status:** ⏸️ On Hold (revisit after 2026-01-27)
**Impact:** High - Current entry flow has too much friction

### Task 6: Customizable Dashboard
**Status:** ✅ Complete
**Impact:** Medium - User controls their dashboard experience
**Completed:** 2026-01-20

**Scope (completed):**
- Drag-and-drop tile reordering
- Show/hide toggles for each tile (AI Insights mandatory)
- Tile sizing (small/medium/large)
- Setup banner for new/existing users
- 19 configurable tiles with module dependencies

### Task 7: Add Deadline Badges for Goals
**Status:** ✅ Complete
**Impact:** Medium - Creates urgency for approaching deadlines
**Completed:** 2026-01-20

**Scope (completed):**
- Deadline properties on LifeGoal model (is_overdue, days_until_due, deadline_urgency, deadline_badge_text)
- User preference toggle (show_goal_deadline_badges, default: True)
- Encouraging badge language: "Due in X days", "Past target date", "🎉 Completed!"
- Badges on goal_list, home, goal_detail, dashboard widget

### Task 8: Add Bill Due Date Reminders to Finance
**Status:** ⏸️ On Hold (revisit after 2026-02-03)
**Impact:** Medium - Proactive financial guidance

### Task 9: Enhanced AI Assistant - Intelligent Search & Query Gateway
**Status:** ⚪ Pending
**Impact:** HIGH - Core feature that makes the Assistant the single search tool for all of WLJ

**Vision:** The AI Assistant becomes the intelligent gateway to everything - personal data first, external APIs second, general knowledge third - all filtered through WLJ values.

**Query Resolution Hierarchy:**
1. **Personal Data (WLJ)** - Journal, Health, Goals, Faith, Organize, Finance, Capture
2. **External APIs** - Connected data sources (future: calendar, fitness trackers, etc.)
3. **OpenAI with Context** - General questions answered within WLJ culture/values

**WLJ Culture Filter:**
- Faith-positive, wellness-focused, encouraging tone
- Refuse inappropriate content (pornography, harmful content, crude humor)
- Redirect to positive alternatives: "Have you explored our Faith module or Reading Plans?"
- Protect user privacy and dignity

**Technical Components:**
1. Intent detection - Is this a search? What type?
2. Query parsing - Extract module, keywords, date ranges
3. Search execution - Query appropriate models/APIs
4. Result injection - Feed results into AI context
5. Values guardrails - Filter requests and responses through WLJ culture

### Task 10: Add Real-Time Processing Status for Capture
**Status:** ⚪ Pending
**Impact:** Medium - Users don't know when transcription completes

### Task 11: Add Wearable Sync (Fitbit/Apple Health)
**Status:** ⚪ Pending
**Impact:** High but complex - Reduces manual health data entry

### Task 12: Connect Prayers/Scripture/Reflections in Faith
**Status:** ⚪ Pending
**Impact:** Medium - Creates integrated spiritual journey

### Task 13: Add Proactive AI Coaching Interventions
**Status:** ⚪ Pending
**Impact:** Medium - AI should coach, not just respond

### Task 14: Add Journal Export (PDF/JSON)
**Status:** ⚪ Pending
**Impact:** Medium - Data portability

### Task 15: Add Tabbed Preferences Navigation
**Status:** ⚪ Pending
**Impact:** Medium - 60+ fields is overwhelming

### Task 16: Add Household Sharing for Life/Finance
**Status:** ⚪ Pending
**Impact:** High but complex - Enables family use

### Task 17: Add Lab Results Storage to Health
**Status:** ⚪ Pending
**Impact:** Medium - Medical continuity for provider visits

### Task 18: Add Community Features for Reading Plans
**Status:** ⚪ Pending
**Impact:** Medium - Accountability for spiritual growth

### Task 19: Build Cross-Module Integration Layer
**Status:** ⚪ Pending
**Impact:** High but complex - Links features across modules

### Task 20: Mobile-First Quick Action Redesign
**Status:** ⚪ Pending
**Impact:** Medium - Optimize for phone usage

### Task 21: Improve Bible API Translation Options
**Status:** ⚪ Pending (Requires research)
**Impact:** HIGH - Users want ESV/NIV but current API.Bible free tier blocks them
**Created:** 2026-01-22

**Problem:**
- API.Bible free tier returns 403 Forbidden for popular translations (ESV, NIV)
- Users seeing errors when expanding scripture in reading plans

**Research Needed:**
- Investigate official ESV API (api.esv.org) - free for non-commercial use
- Contact Biblica about NIV licensing options
- Evaluate API.Bible paid tier pricing
- Identify which public domain translations (KJV, ASV, WEB) work reliably

**DO NOT USE:** Bolls Bible API (bolls.life) - unclear licensing for copyrighted translations, potential copyright liability.

---

## Progress Log

### 2026-01-20
- Created initial task list from comprehensive app analysis
- Starting dialog on Task 1 (Sleep Tracking)

