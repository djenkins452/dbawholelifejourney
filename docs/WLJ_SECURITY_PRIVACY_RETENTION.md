# WLJ Security, Privacy & Retention

**Status:** CURRENT · Milestone artifact (2026-07-11)
**Scope:** Artifact ownership, retention, audit, confirmation, provenance, conversation attachments. Complements the security suite (`wlj_security_*`, `CISO_SECURITY_PROJECT_MASTER_PROMPT`, `account_deletion.md`, `key_rotation_schedule.md`).

---

## 1. Ownership & isolation

- All user data is owned by a single `User` (email-based auth). Models are `UserOwnedModel` with per-user scoping as the ownership boundary.
- **Truth providers are user-scoped by their own query** — the query *is* the boundary (Current Context page summaries, mission link, execution truth). No provider returns another user's data.
- **Soft deletes:** models use `soft_delete()` (SoftDeleteManager), not hard deletes. Hard deletion is reserved for explicit account-deletion flows (`account_deletion.md`).

## 2. Conversation attachments & image retention (LOCKED)

**Policy: chat images are retained for 72 hours, then expire.** This is the platform-wide chat-image retention policy and is **not changing** (milestone directive).

- Implementation: `apps/ai/multimodal.py` and `apps/ai/personal_assistant.py` set `image_expires_at = now + timedelta(hours=72)` on `Message` / `MessageImage` rows when an image is attached to the transcript.
- The image is persisted on the transcript so the conversation stays coherent (a follow-up turn can still refer to "the photo I sent"), but the raw image data is transient — it expires at 72h while the deterministic facts extracted from it (e.g. a logged weight) persist as normal user truth with provenance.
- **Rationale:** minimize retention of raw personal images while preserving the *truth* they produced. The fact is durable; the image is ephemeral.

*Note: the capture/audio subsystem has its own separate retention (audio expiry + reminders) — see the capture module; do not conflate it with the 72h chat-image policy.*

## 3. Provenance

- Every fact WLJ records carries provenance (source, timestamp, and — for multimodal — that it originated from a perceived upload). A multimodal-derived log is auditable back to its arrival.
- The model may **reason** from facts but may **never invent** a WLJ fact (Constitution I.4 / IV.1). Fabrication is forbidden; provenance is how that's verifiable after the fact.

## 4. Audit

- Every action request WLJ receives is audited. Actions produce a DecisionRecord in the live feed with the decision, inputs, and outcome.
- Audit is deterministic and WLJ-owned (Constitution I.7). The audit trail is the record of *what actually happened* (results, not intentions).

## 5. Confirmation & safe action path

- Data-changing actions run through the safe deterministic path: validate → (optional) confirm → execute → audit.
- Confirmation stores a pending action with an expiry; a bare "yes" completes it; a missing/expired/wrong id **fails honestly** and never executes a stale or guessed action.
- Safety gates fail **closed** — a gate that errors does not silently bypass the check.

## 6. Request-path safety (privacy + availability)

- Interactive requests never block on Celery/Redis and never live-compute heavy analytics; they read pre-computed snapshots or return "pending" (`docs/WLJ_REQUEST_PATH_SAFETY.md`). This protects availability (no 524s) and keeps expensive cross-user computation off the request path.

## 7. Keys & secrets

- No secret is committed. `sigtest_settings.py` and similar local scratch are gitignored. A historically-committed key incident led to deleting `wlj_claude_original_backup.md` and rotating (see `key_rotation_schedule.md`).
- Each Railway service carries its own environment (`OPENAI_API_KEY`, Stripe keys, `DJSTRIPE_WEBHOOK_SECRET`, etc.). A missing key degrades that service's feature honestly (logged), never silently.

## 8. What this milestone did NOT change

- The 72h image retention policy (kept, documented, locked).
- Soft-delete semantics.
- The safe action path, confirmation model, or audit pipeline.

Any change to §2 (retention), §4 (audit), or §5 (confirmation/safe path) touches Constitution Article I.6/I.7 and requires Constitutional Review.
