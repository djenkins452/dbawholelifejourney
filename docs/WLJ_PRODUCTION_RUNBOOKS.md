# WLJ Production Runbooks

**Status:** CURRENT · Milestone artifact (2026-07-11)
**Environment:** Railway (Nixpacks + Gunicorn), PostgreSQL, Redis, Celery worker/beat (+ optional chatworker `-Q chat`), OpenAI.
**Ops constraint (CRITICAL):** There is **no prod CLI/SSH**. Run code against prod only via a `RunPython` data migration (the Procfile runs `migrate` every deploy). Never standalone management commands for one-offs.

This complements `docs/wlj_claude_deploy.md`, `docs/wlj_claude_troubleshoot.md`, `docs/wlj_backup.md`, and the historical `BETH_ROLLBACK_AND_RECOVERY.md` (retired framing — process still informative).

---

## 0. First moves for ANY production incident

1. Check the Ops Wall: `/admin-console/ops/`. Note which sections are Degraded/Failed and their freshness.
2. Check infra liveness: `/_health/` (DB `SELECT 1`, Redis probe, scheduler).
3. Classify the failing **layer** before touching code: **Truth (WLJ) → Reasoning (model) → Action (WLJ) → Experience**. Fix the first that failed.
4. For "shows X, should show Y": follow `docs/WLJ_RUNTIME_TRACE_DEBUGGING.md` — **prove the runtime path before editing.**

---

## 1. Deploy & rollback

**Deploy:** push `main` to the deploy remote:
```bash
GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:djenkins452/dbawholelifejourney.git main
```
Railway auto-builds and runs `migrate` (+ `load_initial_data`, `recalculate_task_priorities`) on deploy.

**Rollback (code):** the milestone recovery point is the annotated tag `milestone-cos-architecture-v1` at the verified SHA. To roll back:
```bash
git checkout milestone-cos-architecture-v1     # inspect
git revert <bad-sha>..HEAD                      # preferred — preserves history
# or, deliberate hard reset of main to the tag, then force-push (last resort, announce first)
```
Prefer `revert` over force-push. Never force-push `main` without explicit intent.

**Rollback (data/migration):** if a migration caused the problem, ship a **new forward migration** that corrects state. Do not attempt to "un-migrate" prod. Each migration must be reversible in code where feasible.

## 2. Streaming generation degraded

- Symptom: chat hangs, no first token, or stream aborts.
- Check: `chat_latency` (TTFT) on Ops Wall; `chat` queue depth (note gap OPS-3 — not currently surfaced, inspect Redis `LLEN` for the chat queue directly via a diagnostic migration if needed); chatworker liveness.
- Both chat paths must behave the same: `/api/chat/` (non-streaming) and `/api/chat/stream/` (SSE). A fix to one must be verified on the other.
- If OpenAI is the cause (see §3), streaming degrades first — treat as upstream.

## 3. OpenAI / Model Interface outage

- Symptom: AI features unavailable; `OpenAI client NOT created` warnings; action/answer failures.
- **No upstream OpenAI health card exists yet (gap OPS-4).** Confirm via: `aafr` action-failure spike, `chat_latency` climb, error logs.
- Verify `OPENAI_API_KEY` is set on the failing service's environment (each Railway service has its own env).
- The provider sits behind the single Model Interface seam — a provider outage must **fail honestly** to the user ("I can't reach my reasoning right now"), never fabricate. WLJ truth (dashboards, deterministic pages) stays fully functional during an LLM outage.

## 4. Celery workers / beat

- **Worker down:** Ops Wall Celery card → DOWN/CRITICAL. Railway restarts the `worker` service; confirm `inspect().ping()` recovers. Backlogged tasks drain (acks_late re-queues in-flight).
- **Beat drift / missed runs:** Ops Wall scheduler card → `drift_seconds`, MISSED_RUN, ENGINE_STARVATION. Beat liveness is *inferred* from ISE+SAME heartbeats (gap OPS-10) — a non-engine Beat task can die silently (gap OPS-1). If a scheduled job's output is stale, check whether it's a registered engine; if not, verify it via its data freshness.
- Enqueues are fire-and-forget (`CELERY_TASK_IGNORE_RESULT=True`, 0.5s socket timeouts) — a degraded Redis never blocks a request. Always enqueue via `safe_enqueue`.

## 5. Redis

- Broker+cache. Circuit breaker in `/_health/`.
- If Redis is down: requests stay up (non-blocking enqueue), but background intelligence stops and cache reads miss → pages return "pending" states, never live-compute (request-path safety). Restore Redis; heartbeats resume.

## 6. PostgreSQL

- Liveness at `/_health/` (`SELECT 1`). No depth telemetry on the wall yet (gap OPS-5).
- Connection saturation / slow queries: inspect via Railway metrics + a read-only diagnostic migration if needed. Remember SQLite (dev) hides N+1 blowups that are 5–20s on prod Postgres — profile query counts.

## 7. Multimodal / ingestion

- Uploaded image/PDF → model perceives → WLJ runs candidates through validate→dedup→confirm→execute→audit+provenance. No OCR/parser in WLJ.
- Image persistence: `MessageImage` + `image_expires_at` = now + 72h (`apps/ai/multimodal.py`). See `docs/WLJ_SECURITY_PRIVACY_RETENTION.md`.
- Same-image duplicate writes are guarded (dedup by hash). If duplicates appear, check the artifact-store dedup path.

## 8. Audit & confirmations

- Every action is audited (DecisionRecord in the live feed). Audit-pipeline lag has no health metric yet (gap OPS-8) — verify by spot-checking recent DecisionRecords.
- Confirmation: a pending action is stored with an expiry; a bare "yes" confirms; a wrong/expired id **fails honestly** (never executes "whatever is stored"). If confirmations misfire, check `confirmation_detector` + the CRUD confirmation bridge.

## 9. Escalation ladder

1. Ops Wall + `/_health/` → identify failing component & layer.
2. Reproduce with runtime-trace debugging (glass-box endpoint via migration if ownership is unclear).
3. Fix the first failing layer; forward-only for data.
4. Deploy via `main` push; verify on Ops Wall + the actual user surface.
5. Log to changelog; if user-visible, follow the release policy.
