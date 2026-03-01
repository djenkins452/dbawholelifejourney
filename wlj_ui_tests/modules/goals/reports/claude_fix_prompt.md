# WLJ UI Test Failure — Fix Required

## Environment
- **Module:** goals
- **Run ID:** 95cdcfdb
- **Base URL:** http://localhost:8000
- **Timestamp:** 2026-02-26T17:28:07.919+00:00
- **Total failures:** 2

## Failure 1 of 2

### Case: GOAL-NAV-002
**Name:** GOAL-NAV-002

### What Failed
- **Step:** 2 (CLICK)
- **Action:** CLICK on text=AUTOTEST|goals|95cdcfdb|Full Goal
- **Error:** Locator.click: Error: strict mode violation: locator("text=AUTOTEST|goals|95cdcfdb|Full Goal") resolved to 2 elements:
    1) <a href="/purpose/goals/3/" class="nav-dropdown-item">…</a> aka locator("#nav-menu").get_by_text("AUTOTEST|goals|95cdcfdb|Full")
    2) <a href="/purpose/goals/3/" data-testid="goal-card-link">AUTOTEST|goals|95cdcfdb|Full Goal</a> aka get_by_role("link", name="AUTOTEST|goals|95cdcfdb|Full")

Call log:
  - waiting for locator("text=AUTOTEST|goals|95cdcfdb|Full Goal")


### Selector Details
- **Strategy:** text_contains
- **Value:** AUTOTEST|goals|95cdcfdb|Full Goal
- **Resolved to:** text=AUTOTEST|goals|95cdcfdb|Full Goal

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/goals/artifacts/goals_GOAL-NAV-002_20260226T172923.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/goals/artifacts/goals_GOAL-NAV-002_20260226T172923.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module goals --headed
```

### Required Fix
1. Check if the element matching `text=AUTOTEST|goals|95cdcfdb|Full Goal` exists in the goals templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---

## Failure 2 of 2

### Case: GOAL-NAV-003
**Name:** GOAL-NAV-003

### What Failed
- **Step:** 2 (CLICK)
- **Action:** CLICK on text=AUTOTEST|goals|95cdcfdb|Minimal Goal
- **Error:** Locator.click: Error: strict mode violation: locator("text=AUTOTEST|goals|95cdcfdb|Minimal Goal") resolved to 2 elements:
    1) <a href="/purpose/goals/2/" class="nav-dropdown-item">…</a> aka locator("#nav-menu").get_by_text("AUTOTEST|goals|95cdcfdb|Minimal Goal")
    2) <a href="/purpose/goals/2/" data-testid="goal-card-link">AUTOTEST|goals|95cdcfdb|Minimal Goal</a> aka get_by_role("link", name="AUTOTEST|goals|95cdcfdb|Minimal Goal")

Call log:
  - waiting for locator("text=AUTOTEST|goals|95cdcfdb|Minimal Goal")


### Selector Details
- **Strategy:** text_contains
- **Value:** AUTOTEST|goals|95cdcfdb|Minimal Goal
- **Resolved to:** text=AUTOTEST|goals|95cdcfdb|Minimal Goal

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/goals/artifacts/goals_GOAL-NAV-003_20260226T172926.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/goals/artifacts/goals_GOAL-NAV-003_20260226T172926.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module goals --headed
```

### Required Fix
1. Check if the element matching `text=AUTOTEST|goals|95cdcfdb|Minimal Goal` exists in the goals templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---
