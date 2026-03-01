# WLJ UI Test Failure — Fix Required

## Environment
- **Module:** admin
- **Run ID:** f7ab3196
- **Base URL:** http://localhost:8000
- **Timestamp:** 2026-02-26T22:27:37.618+00:00
- **Total failures:** 2

## Failure 1 of 2

### Case: AC-ANN-CANCEL-001
**Name:** AC-ANN-CANCEL-001

### What Failed
- **Step:** 2 (CLICK)
- **Action:** CLICK on [data-testid="ac-announcement-cancel-button"]
- **Error:** Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"ac-announcement-cancel-button\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** ac-announcement-cancel-button
- **Resolved to:** [data-testid="ac-announcement-cancel-button"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/admin/artifacts/admin_AC-ANN-CANCEL-001_20260226T224219.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/admin/artifacts/admin_AC-ANN-CANCEL-001_20260226T224219.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module admin --headed
```

### Required Fix
1. Check if the element with `data-testid="ac-announcement-cancel-button"` exists in the admin templates
2. If missing, add `data-testid="ac-announcement-cancel-button"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the CLICK action
5. Run the test again to confirm the fix

---

## Failure 2 of 2

### Case: AC-INTAKE-001
**Name:** AC-INTAKE-001

### What Failed
- **Step:** 2 (ASSERT)
- **Action:** ASSERT on N/A
- **Error:** url_contains: expected '/admin-console/projects/intake/' in 'http://localhost:8000/accounts/login/?next=/dashboard/'

### Selector Details
- **Strategy:** none
- **Value:** N/A
- **Resolved to:** N/A

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/admin/artifacts/admin_AC-INTAKE-001_20260226T224223.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/admin/artifacts/admin_AC-INTAKE-001_20260226T224223.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module admin --headed
```

### Required Fix
1. If present, check if the element is conditionally rendered or hidden
2. Verify the page has fully loaded before the ASSERT action
3. Run the test again to confirm the fix

---
