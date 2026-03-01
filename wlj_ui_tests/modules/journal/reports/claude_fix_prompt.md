# WLJ UI Test Failure — Fix Required

## Environment
- **Module:** journal
- **Run ID:** c3c736d5
- **Base URL:** http://localhost:8000
- **Timestamp:** 2026-02-26T17:46:08.505+00:00
- **Total failures:** 33

## Failure 1 of 33

### Case: JRN-LIST-002
**Name:** JRN-LIST-002

### What Failed
- **Step:** 2 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-empty-state"]
- **Error:** element_visible: '[data-testid="journal-empty-state"]' is not visible

### Selector Details
- **Strategy:** data-testid
- **Value:** journal-empty-state
- **Resolved to:** [data-testid="journal-empty-state"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-LIST-002_20260226T174617.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-LIST-002_20260226T174617.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-empty-state"` exists in the journal templates
2. If missing, add `data-testid="journal-empty-state"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 2 of 33

### Case: JRN-LIST-007
**Name:** JRN-LIST-007

### What Failed
- **Step:** 2 (CLICK)
- **Action:** CLICK on [data-testid="journal-new-entry-button"]
- **Error:** Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-new-entry-button\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-new-entry-button
- **Resolved to:** [data-testid="journal-new-entry-button"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-LIST-007_20260226T174635.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-LIST-007_20260226T174635.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-new-entry-button"` exists in the journal templates
2. If missing, add `data-testid="journal-new-entry-button"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the CLICK action
5. Run the test again to confirm the fix

---

## Failure 3 of 33

### Case: JRN-CREATE-001
**Name:** JRN-CREATE-001

### What Failed
- **Step:** 3 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-entry-form"]
- **Error:** element_visible: '[data-testid="journal-entry-form"]' is not visible

### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-form
- **Resolved to:** [data-testid="journal-entry-form"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-001_20260226T174639.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-001_20260226T174639.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-form"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-form"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 4 of 33

### Case: JRN-CREATE-006
**Name:** JRN-CREATE-006

### What Failed
- **Step:** 2 (TYPE)
- **Action:** TYPE on [data-testid="journal-entry-title-input"]
- **Error:** Locator.fill: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-title-input\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-title-input
- **Resolved to:** [data-testid="journal-entry-title-input"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-006_20260226T174656.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-006_20260226T174656.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-title-input"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-title-input"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the TYPE action
5. Run the test again to confirm the fix

---

## Failure 5 of 33

### Case: JRN-CREATE-007
**Name:** JRN-CREATE-007

### What Failed
- **Step:** 2 (CLICK)
- **Action:** CLICK on [data-testid="journal-cancel-button"]
- **Error:** Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-cancel-button\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-cancel-button
- **Resolved to:** [data-testid="journal-cancel-button"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-007_20260226T174714.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-007_20260226T174714.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-cancel-button"` exists in the journal templates
2. If missing, add `data-testid="journal-cancel-button"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the CLICK action
5. Run the test again to confirm the fix

---

## Failure 6 of 33

### Case: JRN-CREATE-002
**Name:** JRN-CREATE-002

### What Failed
- **Step:** 2 (TYPE)
- **Action:** TYPE on [data-testid="journal-entry-title-input"]
- **Error:** Locator.fill: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-title-input\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-title-input
- **Resolved to:** [data-testid="journal-entry-title-input"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-002_20260226T174733.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-002_20260226T174733.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-title-input"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-title-input"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the TYPE action
5. Run the test again to confirm the fix

---

## Failure 7 of 33

### Case: JRN-CREATE-003
**Name:** JRN-CREATE-003

### What Failed
- **Step:** 2 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-entry-detail"]
- **Error:** element_visible: '[data-testid="journal-entry-detail"]' is not visible

### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-detail
- **Resolved to:** [data-testid="journal-entry-detail"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-003_20260226T174735.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-003_20260226T174735.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-detail"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-detail"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 8 of 33

### Case: JRN-CREATE-004
**Name:** JRN-CREATE-004

### What Failed
- **Step:** 1 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-entry-detail-title"]
- **Error:** Locator.text_content: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-detail-title\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-detail-title
- **Resolved to:** [data-testid="journal-entry-detail-title"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-004_20260226T174752.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-004_20260226T174752.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-detail-title"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-detail-title"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 9 of 33

### Case: JRN-CREATE-005
**Name:** JRN-CREATE-005

### What Failed
- **Step:** 1 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-entry-detail-body"]
- **Error:** Locator.text_content: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-detail-body\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-detail-body
- **Resolved to:** [data-testid="journal-entry-detail-body"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-005_20260226T174809.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-005_20260226T174809.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-detail-body"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-detail-body"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 10 of 33

### Case: JRN-DETAIL-001
**Name:** JRN-DETAIL-001

### What Failed
- **Step:** 1 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-entry-detail"]
- **Error:** element_visible: '[data-testid="journal-entry-detail"]' is not visible

### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-detail
- **Resolved to:** [data-testid="journal-entry-detail"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DETAIL-001_20260226T174811.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DETAIL-001_20260226T174811.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-detail"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-detail"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 11 of 33

### Case: JRN-DETAIL-002
**Name:** JRN-DETAIL-002

### What Failed
- **Step:** 1 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-entry-detail-title"]
- **Error:** Locator.text_content: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-detail-title\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-detail-title
- **Resolved to:** [data-testid="journal-entry-detail-title"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DETAIL-002_20260226T174828.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DETAIL-002_20260226T174828.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-detail-title"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-detail-title"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 12 of 33

### Case: JRN-DETAIL-003
**Name:** JRN-DETAIL-003

### What Failed
- **Step:** 1 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-entry-detail-body"]
- **Error:** Locator.text_content: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-detail-body\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-detail-body
- **Resolved to:** [data-testid="journal-entry-detail-body"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DETAIL-003_20260226T174846.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DETAIL-003_20260226T174846.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-detail-body"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-detail-body"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 13 of 33

### Case: JRN-DETAIL-004
**Name:** JRN-DETAIL-004

### What Failed
- **Step:** 1 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-edit-button"]
- **Error:** element_visible: '[data-testid="journal-edit-button"]' is not visible

### Selector Details
- **Strategy:** data-testid
- **Value:** journal-edit-button
- **Resolved to:** [data-testid="journal-edit-button"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DETAIL-004_20260226T174848.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DETAIL-004_20260226T174848.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-edit-button"` exists in the journal templates
2. If missing, add `data-testid="journal-edit-button"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 14 of 33

### Case: JRN-DETAIL-005
**Name:** JRN-DETAIL-005

### What Failed
- **Step:** 1 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-entry-delete-button"]
- **Error:** element_visible: '[data-testid="journal-entry-delete-button"]' is not visible

### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-delete-button
- **Resolved to:** [data-testid="journal-entry-delete-button"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DETAIL-005_20260226T174850.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DETAIL-005_20260226T174850.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-delete-button"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-delete-button"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 15 of 33

### Case: JRN-DETAIL-006
**Name:** JRN-DETAIL-006

### What Failed
- **Step:** 0 (CLICK)
- **Action:** CLICK on [data-testid="journal-back-button"]
- **Error:** Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-back-button\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-back-button
- **Resolved to:** [data-testid="journal-back-button"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DETAIL-006_20260226T174907.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DETAIL-006_20260226T174907.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-back-button"` exists in the journal templates
2. If missing, add `data-testid="journal-back-button"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the CLICK action
5. Run the test again to confirm the fix

---

## Failure 16 of 33

### Case: JRN-LIST-003
**Name:** JRN-LIST-003

### What Failed
- **Step:** 2 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-entry-list"]
- **Error:** element_visible: '[data-testid="journal-entry-list"]' is not visible

### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-list
- **Resolved to:** [data-testid="journal-entry-list"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-LIST-003_20260226T174910.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-LIST-003_20260226T174910.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-list"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-list"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 17 of 33

### Case: JRN-LIST-004
**Name:** JRN-LIST-004

### What Failed
- **Step:** 1 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-entry-list"]
- **Error:** Locator.text_content: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-list\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-list
- **Resolved to:** [data-testid="journal-entry-list"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-LIST-004_20260226T174927.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-LIST-004_20260226T174927.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-list"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-list"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 18 of 33

### Case: JRN-LIST-005
**Name:** JRN-LIST-005

### What Failed
- **Step:** 1 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-entry-list"]
- **Error:** Locator.text_content: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-list\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-list
- **Resolved to:** [data-testid="journal-entry-list"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-LIST-005_20260226T174945.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-LIST-005_20260226T174945.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-list"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-list"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 19 of 33

### Case: JRN-LIST-006
**Name:** JRN-LIST-006

### What Failed
- **Step:** 2 (CLICK)
- **Action:** CLICK on [data-testid="journal-entry-link"]
- **Error:** Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-link\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-link
- **Resolved to:** [data-testid="journal-entry-link"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-LIST-006_20260226T175003.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-LIST-006_20260226T175003.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-link"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-link"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the CLICK action
5. Run the test again to confirm the fix

---

## Failure 20 of 33

### Case: JRN-EDIT-001
**Name:** JRN-EDIT-001

### What Failed
- **Step:** 0 (CLICK)
- **Action:** CLICK on [data-testid="journal-edit-button"]
- **Error:** Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-edit-button\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-edit-button
- **Resolved to:** [data-testid="journal-edit-button"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-EDIT-001_20260226T175020.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-EDIT-001_20260226T175020.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-edit-button"` exists in the journal templates
2. If missing, add `data-testid="journal-edit-button"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the CLICK action
5. Run the test again to confirm the fix

---

## Failure 21 of 33

### Case: JRN-EDIT-005
**Name:** JRN-EDIT-005

### What Failed
- **Step:** 0 (CLICK)
- **Action:** CLICK on [data-testid="journal-cancel-button"]
- **Error:** Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-cancel-button\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-cancel-button
- **Resolved to:** [data-testid="journal-cancel-button"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-EDIT-005_20260226T175037.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-EDIT-005_20260226T175037.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-cancel-button"` exists in the journal templates
2. If missing, add `data-testid="journal-cancel-button"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the CLICK action
5. Run the test again to confirm the fix

---

## Failure 22 of 33

### Case: JRN-EDIT-002
**Name:** JRN-EDIT-002

### What Failed
- **Step:** 0 (CLICK)
- **Action:** CLICK on [data-testid="journal-edit-button"]
- **Error:** Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-edit-button\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-edit-button
- **Resolved to:** [data-testid="journal-edit-button"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-EDIT-002_20260226T175053.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-EDIT-002_20260226T175053.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-edit-button"` exists in the journal templates
2. If missing, add `data-testid="journal-edit-button"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the CLICK action
5. Run the test again to confirm the fix

---

## Failure 23 of 33

### Case: JRN-EDIT-003
**Name:** JRN-EDIT-003

### What Failed
- **Step:** 1 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-entry-detail-title"]
- **Error:** Locator.text_content: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-detail-title\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-detail-title
- **Resolved to:** [data-testid="journal-entry-detail-title"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-EDIT-003_20260226T175110.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-EDIT-003_20260226T175110.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-detail-title"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-detail-title"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 24 of 33

### Case: JRN-EDIT-004
**Name:** JRN-EDIT-004

### What Failed
- **Step:** 2 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-entry-detail"]
- **Error:** element_visible: '[data-testid="journal-entry-detail"]' is not visible

### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-detail
- **Resolved to:** [data-testid="journal-entry-detail"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-EDIT-004_20260226T175113.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-EDIT-004_20260226T175113.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-detail"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-detail"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 25 of 33

### Case: JRN-EDIT-006
**Name:** JRN-EDIT-006

### What Failed
- **Step:** 0 (CLICK)
- **Action:** CLICK on [data-testid="journal-edit-button"]
- **Error:** Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-edit-button\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-edit-button
- **Resolved to:** [data-testid="journal-edit-button"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-EDIT-006_20260226T175129.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-EDIT-006_20260226T175129.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-edit-button"` exists in the journal templates
2. If missing, add `data-testid="journal-edit-button"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the CLICK action
5. Run the test again to confirm the fix

---

## Failure 26 of 33

### Case: JRN-CREATE-008
**Name:** JRN-CREATE-008

### What Failed
- **Step:** 2 (TYPE)
- **Action:** TYPE on [data-testid="journal-entry-title-input"]
- **Error:** Locator.fill: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-title-input\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-title-input
- **Resolved to:** [data-testid="journal-entry-title-input"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-008_20260226T175148.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-CREATE-008_20260226T175148.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-title-input"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-title-input"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the TYPE action
5. Run the test again to confirm the fix

---

## Failure 27 of 33

### Case: JRN-DELETE-001
**Name:** JRN-DELETE-001

### What Failed
- **Step:** 2 (TYPE)
- **Action:** TYPE on [data-testid="journal-entry-title-input"]
- **Error:** Locator.fill: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-title-input\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-title-input
- **Resolved to:** [data-testid="journal-entry-title-input"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DELETE-001_20260226T175207.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DELETE-001_20260226T175207.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-title-input"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-title-input"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the TYPE action
5. Run the test again to confirm the fix

---

## Failure 28 of 33

### Case: JRN-DELETE-002
**Name:** JRN-DELETE-002

### What Failed
- **Step:** 0 (CLICK)
- **Action:** CLICK on [data-testid="journal-entry-delete-button"]
- **Error:** Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-delete-button\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-delete-button
- **Resolved to:** [data-testid="journal-entry-delete-button"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DELETE-002_20260226T175223.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DELETE-002_20260226T175223.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-delete-button"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-delete-button"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the CLICK action
5. Run the test again to confirm the fix

---

## Failure 29 of 33

### Case: JRN-DELETE-004
**Name:** JRN-DELETE-004

### What Failed
- **Step:** 2 (ASSERT)
- **Action:** ASSERT on [data-testid="journal-empty-state"]
- **Error:** element_visible: '[data-testid="journal-empty-state"]' is not visible

### Selector Details
- **Strategy:** data-testid
- **Value:** journal-empty-state
- **Resolved to:** [data-testid="journal-empty-state"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DELETE-004_20260226T175227.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-DELETE-004_20260226T175227.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-empty-state"` exists in the journal templates
2. If missing, add `data-testid="journal-empty-state"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the ASSERT action
5. Run the test again to confirm the fix

---

## Failure 30 of 33

### Case: JRN-NAV-001
**Name:** JRN-NAV-001

### What Failed
- **Step:** 2 (CLICK)
- **Action:** CLICK on [data-testid="journal-new-entry-button"]
- **Error:** Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-new-entry-button\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-new-entry-button
- **Resolved to:** [data-testid="journal-new-entry-button"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-NAV-001_20260226T175245.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-NAV-001_20260226T175245.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-new-entry-button"` exists in the journal templates
2. If missing, add `data-testid="journal-new-entry-button"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the CLICK action
5. Run the test again to confirm the fix

---

## Failure 31 of 33

### Case: JRN-NAV-002
**Name:** JRN-NAV-002

### What Failed
- **Step:** 2 (CLICK)
- **Action:** CLICK on [data-testid="journal-entry-link"]
- **Error:** Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-link\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-link
- **Resolved to:** [data-testid="journal-entry-link"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-NAV-002_20260226T175304.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-NAV-002_20260226T175304.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-link"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-link"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the CLICK action
5. Run the test again to confirm the fix

---

## Failure 32 of 33

### Case: JRN-NAV-003
**Name:** JRN-NAV-003

### What Failed
- **Step:** 2 (CLICK)
- **Action:** CLICK on [data-testid="journal-entry-link"]
- **Error:** Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-link\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-link
- **Resolved to:** [data-testid="journal-entry-link"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-NAV-003_20260226T175322.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-NAV-003_20260226T175322.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-link"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-link"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the CLICK action
5. Run the test again to confirm the fix

---

## Failure 33 of 33

### Case: JRN-NAV-004
**Name:** JRN-NAV-004

### What Failed
- **Step:** 2 (TYPE)
- **Action:** TYPE on [data-testid="journal-entry-title-input"]
- **Error:** Locator.fill: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[data-testid=\"journal-entry-title-input\"]")


### Selector Details
- **Strategy:** data-testid
- **Value:** journal-entry-title-input
- **Resolved to:** [data-testid="journal-entry-title-input"]

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-NAV-004_20260226T175341.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/journal/artifacts/journal_JRN-NAV-004_20260226T175341.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-entry-title-input"` exists in the journal templates
2. If missing, add `data-testid="journal-entry-title-input"` to the target element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the TYPE action
5. Run the test again to confirm the fix

---
