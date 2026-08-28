# WLJ CoS Action Safety — the Stuffed Peppers arc

**Status:** ✅ **CLOSED 2026-08-28.** Production verified. New problems start a NEW
production-friction investigation — do not extend this arc.
**Milestones:** M1 `62ada0e3` · M2 `4f3854dc` · M3 `e8f21274` · M4 `08d6274b` ·
identity + cleanup `a3de41d6` · food correction `2544408d` · authorization values `b183ab99`.

---

## 1. The original trust failure

A user asked the Chief of Staff to log a dinner with explicit nutrition. Over the next
eight minutes it created **two Tasks**, then **two weight records of 534 lb** — the meal's
calorie count, written into a body-weight series that had run 268–278 lb — narrated a meal
log that never happened, could not reverse what it had created, and finally offered to
"correct" the bad weight by substituting **275.1 lb**, a real reading from nine days earlier.

## 2. Six defects, one cascade

The single most important finding is that these were **not independent bugs**. One missing
capability produced a substitution, and every subsequent safety layer that should have
stopped it was itself defective — each only visible once the one before it was removed.

| # | Layer | What was actually wrong |
|---|---|---|
| 1 | **Action — capability** | The certified runtime had **no nutrition write at all**. `log_food` existed with a handler but was absent from the write set, so the CoS could READ nutrition truth and not WRITE it. Facing an explicit, confirmed request it could not satisfy, the model reached for the nearest available numeric writes. |
| 2 | **Action — authorization presentation** | The confirmation the user read was **model prose**, not the bound action. They were told *"I've prepared to log Stuffed Peppers for dinner"* while the persisted confirmation was bound to `create_task`. |
| 3 | **Action — exactly-once** | Single-use was enforced by a **cache write that fails open** (`SafeRedisCache.set` returns False and swallows). One `log_weight` confirmation executed **twice**, 38 s apart. |
| 4 | **Action — validation placement** | Measurement validation lived **inside the handler, downstream of the confirmation gate**, so the user authorized a value WLJ had never compared to its own history. The only check that did run was an **absolute** range (40–1000 lb), which 534 passes. |
| 5 | **Action — correction** | No corrective action existed. `complete_execution_item(source_type='weight', source_id=None)` returned *"No completion write is wired for '' yet."* |
| 6 | **Reasoning — invented truth** | Unable to correct, the model proposed replacing the bad value with an unrelated historical one. |

**The through-line:** *a missing capability became a wrong write, and four separate safety
layers each failed to catch it for a different reason.* Fixing only the visible symptom at
any point would have left a confident, unauthorized, unremovable write in place.

## 3. Final architecture

```
CAPABILITY      log_food exposed in BOTH allowlists; user-supplied nutrition is
                authoritative and is never replaced by lookup or estimation
VALIDATION      measurement writes classify NORMAL / INVALID / EXCEPTIONAL from
                canonical history BEFORE authorization; invalid mints no confirmation
AUTHORIZATION   ActionConfirmation (DB) is authoritative; the presented line is rendered
                from the bound action AND the values it will write; model prose may
                introduce it but never redefine it
EXACTLY-ONCE    atomic compare-and-swap pending → executing; retries replay the stored
                result; a stuck claim blocks rather than races
CORRECTION      delete_record binds to an exact retrievable record_id, soft-deletes via
                the domain's own mechanism, is idempotent, and can never write a
                replacement value
AUDIT           every proposal, validation outcome, authorization and execution is
                reconstructable from ToolCallLog + the ActionConfirmation row
```

## 4. Definition of done — verified

| guarantee | evidence |
|---|---|
| logs explicitly supplied dinner nutrition through the canonical path | acceptance run: `log_food` with all 8 nutrients + meal type |
| the user sees exactly what they authorize | authorization line renders action + every value written |
| authorization executes at most once | atomic CAS; 3 confirms → 1 row |
| validation happens before authorization | invalid mints no confirmation at all |
| no unrelated domain receives the values | nutrition write creates no Task and no Weight |
| success reported only from actual execution | failed write cannot be narrated as success |
| an erroneous record is targetable by exact identity | `record_id` retrievable → bound removal, no invented replacement |

## 5. Durable lessons

- **A missing capability is a safety problem, not a feature gap.** A model told to be useful,
  holding an explicit confirmed instruction it cannot satisfy, will reach for the nearest
  available write. Truth that is readable but not writable is an asymmetry with teeth.
- **A read-then-write guard over a best-effort cache is not a safety control.** If the
  mechanism that enforces "at most once" can silently no-op, it enforces nothing.
- **Validation downstream of authorization cannot protect an authorization.** Placement is
  the property that matters, not existence.
- **An absolute range gate cannot catch a value implausible only for THIS series.** Personal
  history is the comparison that matters.
- **Exposure requires every allowlist to agree.** Adding a capability to one leaves it
  advertised but undispatchable.
- **What the user authorizes must be rendered from the bound payload — including the values.**
  Naming the action is not enough; the numbers are what gets stored.

## 6. Explicitly deferred / unrelated (kept separate)

Medication-reference M2 (generic/NDC) · the `test_medicine` adherence-context failure · the
`apps.medical` LabEducation/Mapper failures · concurrent Finance work · `log_body_measurements`
as a second consumer of the measurement-validation seam.

**No Constitutional Review occurred in this arc and nothing was added to the Amendment Log.**
