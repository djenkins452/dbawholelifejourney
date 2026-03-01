# WLJ UI Test Failure — Fix Required

## Environment
- **Module:** health
- **Run ID:** 0ffd48d8
- **Base URL:** http://localhost:8000
- **Timestamp:** 2026-02-26T18:22:47.320+00:00
- **Total failures:** 18

## Failure 1 of 18

### Case: HEALTH-AUTH-001
**Name:** HEALTH-AUTH-001

### What Failed
- **Step:** 1 (TYPE)
- **Action:** TYPE on id:id_login
- **Error:** Locator.fill: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'id:id_login' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("id:id_login")


### Selector Details
- **Strategy:** css/xpath
- **Value:** id:id_login
- **Resolved to:** id:id_login

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-AUTH-001_20260226T182249.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-AUTH-001_20260226T182249.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `id:id_login` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the TYPE action
4. Run the test again to confirm the fix

---

## Failure 2 of 18

### Case: HEALTH-WEIGHT-003
**Name:** HEALTH-WEIGHT-003

### What Failed
- **Step:** 1 (CLICK)
- **Action:** CLICK on data-testid:health-add-weight-button
- **Error:** Locator.click: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'data-testid:health-add-weight-button' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("data-testid:health-add-weight-button")


### Selector Details
- **Strategy:** css/xpath
- **Value:** data-testid:health-add-weight-button
- **Resolved to:** data-testid:health-add-weight-button

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WEIGHT-003_20260226T182250.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WEIGHT-003_20260226T182250.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `data-testid:health-add-weight-button` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---

## Failure 3 of 18

### Case: HEALTH-WEIGHT-005
**Name:** HEALTH-WEIGHT-005

### What Failed
- **Step:** 1 (TYPE)
- **Action:** TYPE on id:id_value
- **Error:** Locator.fill: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'id:id_value' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("id:id_value")


### Selector Details
- **Strategy:** css/xpath
- **Value:** id:id_value
- **Resolved to:** id:id_value

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WEIGHT-005_20260226T182252.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WEIGHT-005_20260226T182252.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `id:id_value` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the TYPE action
4. Run the test again to confirm the fix

---

## Failure 4 of 18

### Case: HEALTH-WEIGHT-006
**Name:** HEALTH-WEIGHT-006

### What Failed
- **Step:** 1 (CLICK)
- **Action:** CLICK on data-testid:weight-cancel-button
- **Error:** Locator.click: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'data-testid:weight-cancel-button' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("data-testid:weight-cancel-button")


### Selector Details
- **Strategy:** css/xpath
- **Value:** data-testid:weight-cancel-button
- **Resolved to:** data-testid:weight-cancel-button

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WEIGHT-006_20260226T182254.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WEIGHT-006_20260226T182254.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `data-testid:weight-cancel-button` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---

## Failure 5 of 18

### Case: HEALTH-WEIGHT-007
**Name:** HEALTH-WEIGHT-007

### What Failed
- **Step:** 1 (CLICK)
- **Action:** CLICK on data-testid:health-back-link
- **Error:** Locator.click: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'data-testid:health-back-link' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("data-testid:health-back-link")


### Selector Details
- **Strategy:** css/xpath
- **Value:** data-testid:health-back-link
- **Resolved to:** data-testid:health-back-link

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WEIGHT-007_20260226T182255.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WEIGHT-007_20260226T182255.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `data-testid:health-back-link` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---

## Failure 6 of 18

### Case: HEALTH-SLEEP-003
**Name:** HEALTH-SLEEP-003

### What Failed
- **Step:** 1 (CLICK)
- **Action:** CLICK on data-testid:health-add-sleep-button
- **Error:** Locator.click: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'data-testid:health-add-sleep-button' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("data-testid:health-add-sleep-button")


### Selector Details
- **Strategy:** css/xpath
- **Value:** data-testid:health-add-sleep-button
- **Resolved to:** data-testid:health-add-sleep-button

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-SLEEP-003_20260226T182257.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-SLEEP-003_20260226T182257.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `data-testid:health-add-sleep-button` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---

## Failure 7 of 18

### Case: HEALTH-SLEEP-005
**Name:** HEALTH-SLEEP-005

### What Failed
- **Step:** 1 (CLICK)
- **Action:** CLICK on data-testid:sleep-cancel-button
- **Error:** Locator.click: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'data-testid:sleep-cancel-button' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("data-testid:sleep-cancel-button")


### Selector Details
- **Strategy:** css/xpath
- **Value:** data-testid:sleep-cancel-button
- **Resolved to:** data-testid:sleep-cancel-button

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-SLEEP-005_20260226T182259.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-SLEEP-005_20260226T182259.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `data-testid:sleep-cancel-button` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---

## Failure 8 of 18

### Case: HEALTH-SLEEP-006
**Name:** HEALTH-SLEEP-006

### What Failed
- **Step:** 1 (CLICK)
- **Action:** CLICK on data-testid:health-back-link
- **Error:** Locator.click: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'data-testid:health-back-link' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("data-testid:health-back-link")


### Selector Details
- **Strategy:** css/xpath
- **Value:** data-testid:health-back-link
- **Resolved to:** data-testid:health-back-link

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-SLEEP-006_20260226T182300.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-SLEEP-006_20260226T182300.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `data-testid:health-back-link` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---

## Failure 9 of 18

### Case: HEALTH-STEPS-003
**Name:** HEALTH-STEPS-003

### What Failed
- **Step:** 1 (CLICK)
- **Action:** CLICK on data-testid:health-add-steps-button
- **Error:** Locator.click: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'data-testid:health-add-steps-button' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("data-testid:health-add-steps-button")


### Selector Details
- **Strategy:** css/xpath
- **Value:** data-testid:health-add-steps-button
- **Resolved to:** data-testid:health-add-steps-button

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-STEPS-003_20260226T182302.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-STEPS-003_20260226T182302.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `data-testid:health-add-steps-button` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---

## Failure 10 of 18

### Case: HEALTH-STEPS-005
**Name:** HEALTH-STEPS-005

### What Failed
- **Step:** 1 (TYPE)
- **Action:** TYPE on id:id_count
- **Error:** Locator.fill: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'id:id_count' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("id:id_count")


### Selector Details
- **Strategy:** css/xpath
- **Value:** id:id_count
- **Resolved to:** id:id_count

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-STEPS-005_20260226T182304.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-STEPS-005_20260226T182304.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `id:id_count` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the TYPE action
4. Run the test again to confirm the fix

---

## Failure 11 of 18

### Case: HEALTH-STEPS-006
**Name:** HEALTH-STEPS-006

### What Failed
- **Step:** 1 (CLICK)
- **Action:** CLICK on data-testid:steps-cancel-button
- **Error:** Locator.click: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'data-testid:steps-cancel-button' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("data-testid:steps-cancel-button")


### Selector Details
- **Strategy:** css/xpath
- **Value:** data-testid:steps-cancel-button
- **Resolved to:** data-testid:steps-cancel-button

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-STEPS-006_20260226T182305.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-STEPS-006_20260226T182305.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `data-testid:steps-cancel-button` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---

## Failure 12 of 18

### Case: HEALTH-STEPS-007
**Name:** HEALTH-STEPS-007

### What Failed
- **Step:** 1 (CLICK)
- **Action:** CLICK on data-testid:health-back-link
- **Error:** Locator.click: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'data-testid:health-back-link' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("data-testid:health-back-link")


### Selector Details
- **Strategy:** css/xpath
- **Value:** data-testid:health-back-link
- **Resolved to:** data-testid:health-back-link

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-STEPS-007_20260226T182307.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-STEPS-007_20260226T182307.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `data-testid:health-back-link` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---

## Failure 13 of 18

### Case: HEALTH-WATER-003
**Name:** HEALTH-WATER-003

### What Failed
- **Step:** 1 (CLICK)
- **Action:** CLICK on data-testid:health-add-water-button
- **Error:** Locator.click: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'data-testid:health-add-water-button' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("data-testid:health-add-water-button")


### Selector Details
- **Strategy:** css/xpath
- **Value:** data-testid:health-add-water-button
- **Resolved to:** data-testid:health-add-water-button

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WATER-003_20260226T182309.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WATER-003_20260226T182309.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `data-testid:health-add-water-button` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---

## Failure 14 of 18

### Case: HEALTH-WATER-005
**Name:** HEALTH-WATER-005

### What Failed
- **Step:** 1 (TYPE)
- **Action:** TYPE on id:id_amount
- **Error:** Locator.fill: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'id:id_amount' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("id:id_amount")


### Selector Details
- **Strategy:** css/xpath
- **Value:** id:id_amount
- **Resolved to:** id:id_amount

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WATER-005_20260226T182310.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WATER-005_20260226T182310.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `id:id_amount` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the TYPE action
4. Run the test again to confirm the fix

---

## Failure 15 of 18

### Case: HEALTH-WATER-006
**Name:** HEALTH-WATER-006

### What Failed
- **Step:** 1 (CLICK)
- **Action:** CLICK on data-testid:water-cancel-button
- **Error:** Locator.click: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'data-testid:water-cancel-button' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("data-testid:water-cancel-button")


### Selector Details
- **Strategy:** css/xpath
- **Value:** data-testid:water-cancel-button
- **Resolved to:** data-testid:water-cancel-button

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WATER-006_20260226T182312.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WATER-006_20260226T182312.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `data-testid:water-cancel-button` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---

## Failure 16 of 18

### Case: HEALTH-WATER-007
**Name:** HEALTH-WATER-007

### What Failed
- **Step:** 1 (CLICK)
- **Action:** CLICK on data-testid:health-back-link
- **Error:** Locator.click: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'data-testid:health-back-link' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("data-testid:health-back-link")


### Selector Details
- **Strategy:** css/xpath
- **Value:** data-testid:health-back-link
- **Resolved to:** data-testid:health-back-link

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WATER-007_20260226T182314.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-WATER-007_20260226T182314.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `data-testid:health-back-link` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---

## Failure 17 of 18

### Case: HEALTH-NAV-001
**Name:** HEALTH-NAV-001

### What Failed
- **Step:** 1 (CLICK)
- **Action:** CLICK on text_contains:Physical Health
- **Error:** Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("text_contains:Physical Health")


### Selector Details
- **Strategy:** css/xpath
- **Value:** text_contains:Physical Health
- **Resolved to:** text_contains:Physical Health

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-NAV-001_20260226T182330.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-NAV-001_20260226T182330.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `text_contains:Physical Health` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---

## Failure 18 of 18

### Case: HEALTH-NAV-002
**Name:** HEALTH-NAV-002

### What Failed
- **Step:** 1 (CLICK)
- **Action:** CLICK on data-testid:health-back-link
- **Error:** Locator.click: SyntaxError: Failed to execute 'querySelectorAll' on 'Document': 'data-testid:health-back-link' is not a valid selector.
    at query (<anonymous>:5288:41)
    at <anonymous>:5298:7
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl._queryCSS (<anonymous>:5285:17)
    at SelectorEvaluatorImpl._querySimple (<anonymous>:5165:19)
    at <anonymous>:5113:29
    at SelectorEvaluatorImpl._cached (<anonymous>:5075:20)
    at SelectorEvaluatorImpl.query (<anonymous>:5106:19)
    at Object.query (<anonymous>:5320:44)
    at <anonymous>:5278:21
Call log:
  - waiting for locator("data-testid:health-back-link")


### Selector Details
- **Strategy:** css/xpath
- **Value:** data-testid:health-back-link
- **Resolved to:** data-testid:health-back-link

### Artifacts
- **Screenshot:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-NAV-002_20260226T182332.png
- **HTML Dump:** /Users/dannyjenkins/Projects/dbawholelifejourney/wlj_ui_tests/modules/health/artifacts/health_HEALTH-NAV-002_20260226T182332.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module health --headed
```

### Required Fix
1. Check if the element matching `data-testid:health-back-link` exists in the health templates
2. If present, check if the element is conditionally rendered or hidden
3. Verify the page has fully loaded before the CLICK action
4. Run the test again to confirm the fix

---
