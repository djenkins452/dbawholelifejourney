# WLJ Multimodal — Production Customer-Experience Verification

**Purpose:** validate whether the Chief of Staff now *behaves the way a paying customer expects* when they hand it real files — PDFs, audio, images — and later ask about them. **This is not a code test.** Every scenario is judged by the WLJ product lens, in order:

1. **Would a paying customer trust this conversation?**
2. If not, **why — in customer terms** (it contradicted itself / forgot / answered the wrong question / made something up)?
3. **Only then**, which layer caused it (Truth → Reasoning → Action → Experience)?

North-star question for the whole run: *"If this were the only conversation a customer ever had with their assistant, would they want to use it again tomorrow?"*

**How findings are used:** measured gaps — not speculation — drive **Artifacts-as-Truth Milestone B**. Each result is tagged so we can separate *bug* from *not-built-yet* and rank by trust impact.

---

## 0. Preconditions (verify BEFORE running scenarios)

A red here invalidates everything downstream — check first.

| # | Precondition | How to confirm | Why it matters |
|---|---|---|---|
| P1 | **`wlj-worker` redeployed** to the current commit | Worker logs show recent restart; `COS_TOOL_LOOP_*` telemetry present | CoS + perception tasks run in the worker, NOT web. Stale worker = old behavior. |
| P2 | **Redis healthy** (post-deploy `circuit_open` cleared) | No sustained `redis: circuit_open`; background tasks draining | Perception + durable storage are enqueued; a dead broker = artifacts stuck `pending` forever. |
| P3 | **Cloudinary configured** | App booted (P0.3 fail-fast would have blocked boot otherwise) | Durable artifact storage; no ephemeral loss. |
| P4 | **OpenAI key on the worker** | A normal chat reply works; a Whisper transcription completes | Perception (Whisper) + reasoning need it in the worker process. |
| P5 | **Migrations applied** (`capture/0007–0009`) | `/admin` shows `storage_status`/`extracted_text`/`original_filename` columns, or a test upload resolves | Perception + retrieval read these columns. |

**Real artifacts to prepare** (use genuine files — the point is real behavior):
- **PDF-A**: a real **insurance policy / EOB** (multi-page, has a deductible + coverage %).
- **PDF-B**: a real **lab/bloodwork report** (named or containing "MRI"/"lab"/"bloodwork").
- **PDF-C**: a **second lab report** (for compare).
- **PDF-D**: a **scanned/photographed** (image-only) PDF — no selectable text.
- **AUDIO-A**: a **voice note** (~30–90s) that contains 2–3 clear action items.
- **IMG-A**: a **scale photo** showing a weight number.
- **IMG-B/IMG-C**: two **progress photos** (for a compare request).
- **IMG-D**: an **insurance card** photo (has a member ID).
- **IMG-E**: a **large iPhone HEIC** photo (tests resize/HEIC/orientation).

---

## 1. Scenario matrix

Each scenario: run it as a customer (natural language, in the real CoS chat), then record **Result** using the tags in §3. Do NOT lead the model with hints ("check the artifacts domain") — a customer wouldn't.

### A. Attachment experience — does adding a file feel like ChatGPT?
| ID | Do this (as a customer) | Expect | Watch for |
|---|---|---|---|
| A1 | Drag-and-drop **PDF-A** onto the desktop chat | Chip with a doc icon + filename appears; no error | Drop zone highlights; chip styled |
| A2 | On **mobile**, tap attach → **Take Photo** and **Photo Library** both offered | OS sheet offers camera + Photos + Browse | — |
| A3 | Attach **IMG-E** (large HEIC) | Accepted, thumbnail shows (not "file too large"; not sideways) | HEIC→JPEG on the iPhone; orientation correct |
| A4 | Attach **PDF-A + IMG-A together**, then a 3rd and 4th and 5th and 6th file | Up to 5 accepted; 6th politely refused | Mixed types coexist as chips/thumbs |
| A5 | Attach an unsupported file (e.g. a `.zip`) | Friendly "that type isn't supported yet" message | No silent failure / no crash |
| A6 | Watch the chip while a **large** file uploads | Visible progress, then "ready" | Progress bar actually moves |

### B. PDF perception — can it READ documents?
| ID | Do this | Expect | Watch for |
|---|---|---|---|
| B1 | Attach **PDF-A**, "Summarize this insurance policy." | Accurate summary grounded in the real text | Invents nothing; covers real sections |
| B2 | (same/next turn) "What's my deductible?" | The **correct** number from the doc | Right figure, not a guess |
| B3 | Attach **PDF-B**, "What does this report say?" | Faithful read of the actual report | — |
| B4 | Attach **PDF-B + PDF-C**, "Compare these two lab reports." | A real comparison of both | Uses BOTH, not one |
| B5 | Attach a **large** PDF and **immediately** ask about it | Honest "I'm still reading it — ask again in a moment" (NOT a hallucinated answer) | The `processing` window handled gracefully |
| B6 | Attach **PDF-D** (scanned/image-only), "What does this say?" | Honest "this looks like a scan I can't read as text yet" | No fabrication for an unreadable doc |

### C. Audio perception — can it UNDERSTAND recordings?
| ID | Do this | Expect | Watch for |
|---|---|---|---|
| C1 | Attach **AUDIO-A**, "Summarize this recording." | Accurate summary from the transcript | Matches what was actually said |
| C2 | (follow-up) "What are the action items?" | The 2–3 real action items | Complete, not invented |
| C3 | "Turn that recording into a journal entry." | A coherent entry from the transcript | Uses real content |
| C4 | Attach audio and **immediately** ask | Honest processing/"still transcribing" state | No hallucinated transcript |

### D. Images — can it SEE?
| ID | Do this | Expect | Watch for |
|---|---|---|---|
| D1 | Attach **IMG-A** (scale), "Log this weight." | Reads the value; logs it; confirms the real number | Correct value + a confirmation |
| D2 | (after D1) "Where did that weight come from?" | "I read it from the photo you uploaded" | Provenance is a fact, not a guess (see G) |
| D3 | Attach **IMG-D** (insurance card), "What's my member ID?" | Reads the ID off the card | Accurate read or honest low-confidence |

### E. Cross-conversation retrieval — does it REMEMBER past uploads?
> The differentiator. Upload in one conversation, ask in a **brand-new** conversation.
| ID | Do this | Expect | Watch for |
|---|---|---|---|
| E1 | (New conversation) "What did my last lab report say?" — PDF-B uploaded earlier | Retrieves PDF-B and answers from its content | Finds it WITHOUT re-attaching |
| E2 | "Show me the receipt I uploaded." (upload a receipt PDF earlier) | Finds the receipt | — |
| E3 | "When did I last upload bloodwork?" | A real date + the item | Deterministic date, not vague |
| E4 | "Find my insurance card." | Points to the uploaded card (IMG-D) | Identifies it (note image-content limits — see §2) |
| E5 | "What documents have I uploaded?" | A real list of uploaded artifacts | Grounded, owner-scoped |

### F. Multi-turn — does it HOLD the thread?
| ID | Do this | Expect | Watch for |
|---|---|---|---|
| F1 | Turn 1: attach **PDF-A**, "Summarize this." → Turn 2 (do NOT re-attach): "What's the deductible?" | Turn 2 still answers correctly | Does it silently re-retrieve the doc, or "forget" it? **Key test.** |
| F2 | Turn 1: audio summary. Turn 3 (after other chatter): "What was the first action item again?" | Still correct | Recall across turns |

### G. Provenance — can it say WHERE truth came from?
| ID | Do this | Expect | Watch for |
|---|---|---|---|
| G1 | After B2, "Where did you get the deductible?" | "From the [policy] you uploaded" | Cites the artifact, not a screen/guess |
| G2 | After D1, ask a day later "how did you know my weight?" | Attributes it to the uploaded photo | Never attributes an upload-read value to a page it happens to be viewing |

### H. Truth-Surface integration — artifacts as first-class truth
| ID | Do this | Expect | Watch for |
|---|---|---|---|
| H1 | "How many files have I uploaded?" / "…this week?" | A real count (by kind) | Deterministic |
| H2 | Ask about a retrieved doc's content, then a specific detail | Consistent, grounded across both | No drift between summary and detail |

### I. Current Context — is it aware of what I'm looking at?
| ID | Do this | Expect | **Predicted** |
|---|---|---|---|
| I1 | Open an artifact/document detail page (if one exists), then ask "what is this?" | Ideally knows you're looking at that artifact | ⚠️ **Predicted GAP** — artifact pages don't declare Current Context yet (Milestone C). Confirm + record. |

### J. Relational retrieval — the harder customer asks (predicted Milestone-B gaps)
> Run these to **measure** the gap and rank it — do not pre-judge.
| ID | Do this | **Predicted** result | Needs |
|---|---|---|---|
| J1 | "The PDF I uploaded after my doctor's appointment." | ⚠️ Likely fails (no conversation/time linkage) | B: conversation linkage |
| J2 | "Summarize every document I uploaded for my compensation project." | ⚠️ Likely partial (only if content literally says 'compensation') | B: domain/project linkage |
| J3 | "Find every attachment related to my France 2027 mission." | ⚠️ Likely fails (no mission linkage) | B: mission linkage |
| J4 | "Compare these two progress photos" (IMG-B/IMG-C uploaded earlier, cross-conversation) | ⚠️ Likely fails — retrieved image artifacts carry metadata, not re-perceivable pixels | B/decision: re-deliver image bytes on retrieval |
| J5 | "Show me the receipt from last month." | 🟡 Partial — content search works; strict time-window filter not wired | C: time `filters` in retrieval |

---

## 2. Known architectural truths that shape "expected" (read before judging)

Being honest here prevents mislabeling a *design boundary* as a *bug*:

- **Perception is background.** Right after upload there is a short `processing` window (Whisper especially). Immediate questions should get an honest "still reading/transcribing," NOT a made-up answer. Grading B5/C4 is about *honesty during processing*, not speed.
- **Same-turn vs. retrieval.** On the turn a file is attached, its extracted text rides in `current_context.attachments[i].text`. On later turns it does **not** re-ride — the model must **retrieve** it via the artifacts Truth Surface (`get_entity`). F1/F2 measure whether that retrieval actually fires. If it doesn't, that's the highest-value finding.
- **Images are not text.** PDF/audio produce `extracted_text`; **images do not** (the model perceives image *pixels* only when the bytes are in the turn). So cross-conversation image tasks (E4 partial, J4) can identify/locate an image by metadata but **cannot re-see its contents** unless we re-deliver the bytes. This is a real capability boundary — J4 measures how much it hurts.
- **No linkage yet.** Conversation/domain/mission/person links (J1–J3) are Milestone B, not built. Expect failure; the value is *how a customer reacts* to that failure (graceful "I can't find that" vs. confident wrong answer).
- **No Current Context on artifact pages** (I1) — Milestone C.
- **Retrieval routing depends on semantics.** The model must choose the `artifacts` domain by meaning. If it answers generically instead of retrieving, that's a **truth-accessibility/routing** finding (fixable), not a missing capability.

---

## 3. Recording results — the tag set

For every scenario record: the **verbatim CoS reply**, then a tag + one-line *customer-terms* note.

- **✅ TRUSTWORTHY** — a customer would trust it and want more.
- **🟨 ROUGH** — right answer, poor experience (slow, clumsy, over-hedged, ugly).
- **🟥 TRUST-BREAK** — wrong, contradicted itself, forgot, or **made something up**. (Highest priority — one of these can sink the whole feature.)
- **⛔ NOT-BUILT** — failed because a capability isn't built yet (expected: J1–J4, I1). A graceful "I can't do that yet" is acceptable; a *confident wrong answer* here is a 🟥, not a ⛔.

For each non-✅, note the **first failing layer**: Truth (didn't retrieve / wrong content) · Reasoning (had it, reasoned wrong) · Action (logged wrong) · Experience (right but bad surface).

---

## 4. From findings to Milestone B (the prioritization rule)

After the run, rank findings by **trust impact**, then:

1. **Every 🟥 first**, wherever it lives. A hallucinated document answer or a "forgot the PDF I just discussed" is a feature-sinker — fix before any new capability. Ask the eliminate-the-class question: *what condition made this possible; can we remove it?*
2. **Then the ⛔ gaps a customer actually hit**, ranked by how often the run showed a real customer would ask that. If J1/J2/J3 rarely mattered but F1 (multi-turn recall) broke trust, Milestone B leads with recall/retrieval robustness, not mission linkage.
3. **🟨 ROUGH** items batched by theme (e.g. processing UX) — cheap trust wins.
4. **Milestone B scope is then written from this ranked list** — not from the speculative B outline. If the run shows linkage is what customers reach for, B = linkage; if it shows retrieval doesn't reliably fire, B = retrieval reliability + image-bytes-on-recall.

**Deliverable of the run:** this doc, filled in, with a one-paragraph verdict against the north-star question and a ranked Milestone-B backlog derived from measured experience.

---

## 5. Who runs it

Executing these means sending real files + real chat turns in production (authenticated as the customer, real OpenAI cost). That's Danny's session to drive. Claude can: (a) help prepare/point at real artifacts, (b) read back the resulting transcripts and worker logs to classify each result and assign the first-failing-layer, and (c) turn the filled-in findings into the ranked Milestone-B backlog. Share transcripts (and the artifact + question) per scenario and Claude will grade them against §3 and §4.
