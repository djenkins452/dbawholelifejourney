# WLJ UI Test Failure — Fix Required

## Environment
- **Module:** faith
- **Run ID:** a620dc1f
- **Base URL:** http://localhost:8000
- **Timestamp:** 2026-02-26T18:07:22.507+00:00
- **Total failures:** 1

## Failure 1 of 1

### Case: FAITH-CLEANUP-002
**Name:** FAITH-CLEANUP-002

### What Failed
- **Step:** 2 (CLICK)
- **Action:** CLICK on [data-testid="prayer-card-link"]
- **Error:** Locator.click: Error: strict mode violation: locator("[data-testid=\"prayer-card-link\"]") resolved to 4 elements:
    1) <a href="/faith/prayers/6/" data-testid="prayer-card-link">AUTOTEST|faith|a620dc1f|Prayer Edited</a> aka get_by_role("link", name="AUTOTEST|faith|a620dc1f|")
    2) <a href="/faith/prayers/4/" data-testid="prayer-card-link">AUTOTEST|faith|4acddffb|Prayer Edited</a> aka get_by_role("link", name="AUTOTEST|faith|4acddffb|")
    3) <a href="/faith/prayers/2/" data-testid="prayer-card-link">AUTOTEST|faith|9a3b45d0|Prayer Two</a> aka get_by_role("link", name="AUTOTEST|faith|9a3b45d0|Prayer Two")
    4) <a href="/faith/prayers/1/" data-testid="prayer-card-link">AUTOTEST|faith|9a3b45d0|Prayer One</a> aka get_by_role("link", name="AUTOTEST|faith|9a3b45d0|Prayer One")

Call log:
  - waiting for locator("[data-testid=\"prayer-card-link\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** prayer-card-link
- **Resolved to:** [data-testid="prayer-card-link"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/faith/artifacts/faith_FAITH-CLEANUP-002_20260226T180907.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/faith/artifacts/faith_FAITH-CLEANUP-002_20260226T180907.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module faith --headed
```

### Required Fix
1. Check if the element with `data-testid="prayer-card-link"` exists in the faith templates
2. If missing, add `data-testid="prayer-card-link"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the CLICK action
5. Run the test again to confirm the fix

---
