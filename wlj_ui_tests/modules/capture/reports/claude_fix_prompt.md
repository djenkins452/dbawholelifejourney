# WLJ UI Test Failure — Fix Required

## Environment
- **Module:** capture
- **Run ID:** a75d262f
- **Base URL:** http://localhost:8000
- **Timestamp:** 2026-02-26T17:42:26.569+00:00
- **Total failures:** 1

## Failure 1 of 1

### Case: CAP-AUTH-001
**Name:** CAP-AUTH-001

### What Failed
- **Step:** 4 (CLICK)
- **Action:** CLICK on [data-testid="login-submit-button"]
- **Error:** Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"login-submit-button\"]")
    - waiting for" http://localhost:8000/dashboard/" navigation to finish...


### Selector Details
- **Strategy:** data-testid
- **Value:** login-submit-button
- **Resolved to:** [data-testid="login-submit-button"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/capture/artifacts/capture_CAP-AUTH-001_20260226T174243.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/capture/artifacts/capture_CAP-AUTH-001_20260226T174243.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module capture --headed
```

### Required Fix
1. Check if the element with `data-testid="login-submit-button"` exists in the capture templates
2. If missing, add `data-testid="login-submit-button"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the CLICK action
5. Run the test again to confirm the fix

---
