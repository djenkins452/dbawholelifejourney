# Universal Arbitration Layer — Future Refinements

**Status:** Deferred — capability-first implementation complete. These items are for future calibration after production observation.

---

## 1. Rate Limiting

- **Signal collection throttle:** Cache ArbitrationInput for N seconds to avoid redundant queries within rapid message bursts
- **Decision log pruning:** Auto-prune logs older than 90 days (or archive to cold storage)
- **Per-user arbitration frequency:** Optionally skip arbitration for mid-conversation messages where context hasn't changed

## 2. Mood-Confidence Thresholds

- **Mood scoring model:** Replace simple great/good/okay/bad/terrible mapping with NLP-derived sentiment scores from journal content
- **Mood confidence decay:** Reduce mood signal weight when last journal entry is >3 days old
- **Cross-validate mood:** Compare journal mood with CycleDailyLog mood/energy for consistency

## 3. Social Suggestion Safeguards

- **Memorial sensitivity:** Auto-detect memorial events and suppress celebratory framing
- **Relationship suggestion cooldown:** Don't re-surface the same person within 48h if user dismissed
- **Cadence learning:** Track when user actually reaches out and adjust drift thresholds accordingly
- **Relationship fatigue:** If user dismisses 3+ relationship suggestions in a row, temporarily suppress category

## 4. Escalation Calibration

- **Severity ramp:** HEALTH_CRITICAL should escalate from PROTECTIVE to DIRECTIVE if medication remains missed after 2 conversation turns
- **Drift escalation:** DRIFT_CRITICAL should escalate from ACCOUNTABILITY to DIRECTIVE if drift score increases across 3 consecutive sessions
- **Session persistence:** Track whether surfaced items were acknowledged across turns within a session

## 5. Interruption Cost Modeling

- **Flow state detection:** If user is in a focused conversation about a specific topic, increase the threshold for scenario switching
- **Conversation momentum:** Weight recent conversation topic when deciding whether to inject arbitration context
- **User override memory:** If user says "I know, moving on" — record that signal was addressed and suppress for session

## 6. Composite Refinement

- **Temporal composites:** Detect patterns across days (e.g., 3 consecutive LOW_CAPACITY_DAYs → BURNOUT_RISK)
- **Seasonal awareness:** Adjust baseline signal thresholds for known seasonal patterns (holiday stress, etc.)
- **Composite confidence:** Add confidence scoring to composites based on historical accuracy

## 7. Feedback Loop

- **Outcome tracking:** After each arbitration, track whether user's next actions aligned with the surfaced items
- **Narrative effectiveness:** A/B test different narrative framings and track engagement
- **User preference learning:** Some users prefer DIRECTIVE even in MOOD_CRITICAL — learn from dismissal patterns
- **Outcome scoring API:** Expose an endpoint to retroactively score arbitration decisions

## 8. Performance Optimization

- **Signal caching:** Cache expensive queries (drift summary, relationship drift) with short TTL
- **Lazy signal loading:** Only collect signals relevant to the most likely scenarios based on SAE state
- **Batch user processing:** For scheduled runs, batch-process multiple users efficiently

## 9. Token Impact Mitigation

- **Narrative compression:** If system prompt is already near token limit, generate shorter narrative
- **Adaptive detail level:** In stable execution, minimize injection size; in critical scenarios, include full context
- **Injection budget:** Set a hard cap on narrative injection token count (e.g., 300 tokens max)

---

*Created: 2026-02-21 — UAL v1.0 initial release*
