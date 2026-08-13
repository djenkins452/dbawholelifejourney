# WLJ Chief of Staff — Durable Turn Lifecycle

**Type:** Investigate → prove first failing layer → smallest correction → certify. No parallel conversation system, no timeout increase, no new reasoning architecture — turn durability only.
**Date:** 2026-08-13
**Governing rule:** *Once Danny says something to his Chief of Staff, the conversation owns that turn — not the browser tab. Navigation can interrupt the VIEW; it must never interrupt or erase the WORK.*

---

## 1. Reported failure

Danny submitted a normal CoS question, switched browser tabs, returned to find it still processing, then saw *"That's taking longer than expected. Please try again."* After navigating away and back again, **the submitted turn had disappeared entirely.**

## 2. Root cause — proven by runtime code trace (first failing layer = Layer 1, persistence/truth ownership)

For Danny (`use_model_interface=True`) the streaming submit path is
`AssistantChatStreamView → CoSGateway.respond(stream=True) → ModelInterfaceRuntime.respond` (streaming branch). Traced end to end:

- The streaming branch **wrote only a Redis bus snapshot and enqueued a Celery task** (`run_model_interface_generation.delay`). It did **NOT** persist the user message or any durable turn. (`cos_gateway/runtime.py`, streaming branch.)
- **Both `AssistantMessage` rows were created inside the worker** (`model_interface/tasks.py`): the user message and a `content=""`, `status="processing"` assistant turn.
- Generation itself IS server-owned (the worker is independent of the HTTP connection — that part was already correct, via the `chat_stream_bus`).

Consequences, all confirmed in code:

1. **Pre-pickup window / dropped enqueue** — between the HTTP submit and the worker actually picking up the job (post-deploy `redis: circuit_open ~30–60s`, queue backlog, or a dropped enqueue), **no durable row exists**. A reload hits `ConversationHistoryView`, finds nothing, and the submitted turn **disappears entirely** — the exact symptom.
2. **Invisible pending turn** — even once the worker creates the pending turn, it has `content=""`, and both frontends omit empty-content messages on hydration (`if (!msg.content...) return;`), so a persisted pending turn renders as nothing.
3. **"Taking longer… try again" is a UI timeout, not a failure** — it is emitted by the client history-poller after ~120s (40×3s), which then **clears the sessionStorage pending marker**. The pending indicator lived **only** in sessionStorage; once cleared, the turn vanished from the view too.

The browser + bus owned the turn's existence until the worker rescued it. The turn was not owned by the submit.

## 3. What already existed (reused, not rebuilt)

The durability scaffolding was substantially present and is reused unchanged: the Redis `chat_stream_bus` (cross-process web↔worker, 10-min TTL), the server-owned Celery worker, the resume endpoint (`/assistant/api/chat/stream/resume/<job_id>/`, 410→load-from-history), `ConversationHistoryView` surfacing `lifecycle` (`request_id`, `status`, `stream_interrupted`), navigation telemetry via `sendBeacon`, and (in the widget) resume-by-job_id + `duplicate_pending`. **The recovery machinery was recovering into a void — because nothing was persisted at submit.** The fix gives it durable truth to recover into.

## 4. Smallest correction (implemented) — persist synchronously at submit; worker updates, never creates

**`apps/ai/cos_gateway/runtime.py` (streaming branch):** persist the **user message** and a **PENDING assistant turn** (`status="processing"`, `request_id=job_id`) **synchronously, before the enqueue** — mirroring the non-streaming branch, which already did this. Hand the worker the two message ids. The instant Danny hits send, the turn exists in durable truth; navigation, a tab switch, a refresh, a client timeout, a pre-pickup delay, or a dropped enqueue can no longer erase it.

**`apps/ai/model_interface/tasks.py`:** when the ids are provided, the worker **reuses** the pre-persisted rows (PENDING → RUNNING → COMPLETED/FAILED) instead of creating them, and loads prior history **excluding the current turn** (`exclude_ids`). A genuine failure marks the same turn `failed` with visible error content (survives reload). Legacy path (no ids) unchanged. The in-flight marker is cleared on every terminal state.

**Duplicate protection** (the responsible complement to synchronous persistence): a genuine double-submit of the same text while in flight no longer mints a second durable turn — it emits the existing turn's `duplicate_pending` (reusing `apps/ai/idempotency.py`). Reload/navigation never re-submits, so it only guards true resubmits.

**`apps/ai/model_interface/service.py`:** `load_conversation_history` gains `exclude_ids` so the worker excludes the already-persisted current turn from the model's history.

State authority after the fix: **the durable `AssistantMessage` turn is the source of truth** (`status` processing/completed/failed); the bus is the live relay; the client renders/reconciles from server truth on load.

## 5. Certification — 7 deterministic end-to-end tests through the REAL path

`apps/ai/tests/test_chat_background.py::ModelInterfaceDurableLifecycleTests` (routes through the real gateway→runtime→worker-task→`/assistant/api/history/`, `use_model_interface=True`):

| Case | Assertion | Result |
|---|---|---|
| Submit persists synchronously **before** the worker runs | user msg + PENDING turn durable at submit; worker handed the ids | ✓ |
| Worker reuses the pending turn | exactly ONE assistant row, advanced to completed — no duplicate on completion | ✓ |
| History excludes the current turn | model history does not feed back the current user message | ✓ |
| Genuine backend failure | same turn marked `failed`, **visible** error content, terminal snapshot | ✓ |
| Duplicate resubmit while in flight | no second turn; `duplicate_pending` emitted | ✓ |
| Hydration surfaces pending lifecycle | `/api/history/` returns user msg + pending turn with server-authoritative `status:processing` + `request_id` | ✓ |
| Reload idempotency | repeated hydration renders the same rows — no duplication | ✓ |

Full affected-suite regression (`test_chat_background`, `test_cos_gateway`, `test_model_interface_runtime`, `test_multimodal_wiring`): **94 tests OK.** Request-path safety contract: OK. `manage.py check` clean. No migrations.

## 6. Deployment topology

CoS generation runs in the separate `wlj-worker` Celery service; the streaming submit + hydration run in the web service. Both must carry the new commit — worker verified on the deployed commit before sign-off.

## 7. Honest scope + residual

- **Certified deterministically through the real runtime**, not by driving Danny's authenticated browser in production — I did not inject test turns into his real conversation, and the persistence invariant (ORM ordering of user + pending rows before enqueue) does not depend on production Redis/Postgres; identical code is deployed and the worker commit is verified.
- **Frontend pending indicator is now BACKED by a durable server turn** but the two chat templates still render the pending bubble primarily from the sessionStorage marker (which survives navigation/refresh within the tab). Making the client render/reconcile pending strictly from the server `status:processing` turn (so a *different* tab/window also shows it) is a clean follow-up that needs browser-level verification — flagged, not shipped blind.
- **Sibling runtime residual:** `ChatGPTCoSRuntime` streaming + `run_chatgpt_cos_generation` have the identical latent gap (turn created in the worker). Danny is exclusively on `model_interface`, so his certified path is fixed; the sibling is contained + logged here with the same fix pattern, to avoid destabilizing a second runtime unverified (eliminate-the-class: contain narrowly + LOG residual).
