# WLJ Journal Experience — Product & UX Vision (Canonical)

**Status:** RATIFIED product direction — canonical design (implementation not yet started)
**Owner:** Danny + Chief Architect
**Date:** 2026-07-19
**Governs:** the reimagined Journal experience — the *how* of journaling in WLJ
**Reads from:** `WLJ_PRODUCT_VISION.md`, `WLJ_LLM_TRUTH_ACTION_CONTRACT.md`, `WLJ_CONSTITUTION.md`, `WLJ_MULTIMODAL_INTAKE_ARCHITECTURE.md`, `WLJ_REQUEST_PATH_SAFETY.md`, `WLJ_CURRENT_CONTEXT_CONTRACT.md`
**Visual spec:** `docs/journal_experience_mockups.html` (screen-by-screen wireframes for every state)
**Conversation playbook:** `docs/WLJ_JOURNAL_CONVERSATION_PLAYBOOK.md` (the governing behavioral standard for how the CoS conducts a journaling conversation)
**Conversational memory model:** `docs/WLJ_JOURNAL_CONVERSATIONAL_MEMORY_MODEL.md` (the governing standard for how the CoS *remembers* during a journaling conversation)
**Hard constraint:** zero regression of today's Journal capabilities (§18). All three methods terminate in the existing canonical `JournalEntry` truth spine — History and CoS truth-access get **richer**, never weaker.

---

## The one sentence

> **Journaling that feels like sitting down at the end of the day with someone who has known you for years.**

It is still called **Journal.** Journaling is a category people already understand; we are not renaming it. The innovation is **multiple natural ways to create an entry** — including a personal voice conversation with a Chief of Staff that already knows the user's life.

---

## Vocabulary (ratified 2026-07-20) — one consistent language across the whole experience

The user should never wonder *"am I creating, editing, publishing, saving, or drafting a journal?"* The words answer it:

- **Journal Draft** — the in-progress work. It **defaults to today but the concept is broader** (a trip, a story about a person, an old event, catching up on yesterday, a Christmas journal). Never call it "Today's Journal." One draft is shared by all three methods (§13); it is the durable `JournalConversation` (= the working-named `JournalDraftSession`, §11).
- **Resume** — return to an in-progress draft (Resume Write Together / Resume Talk It Through / Continue Writing).
- **Finish & Review** — the user decides the telling is done. Ends the conversation, generates the journal, leads into Review. It does **not** mean the journal is saved yet.
- **Review** — the user reads their own words rendered back, edits, and owns them.
- **Save Journal** — the terminal act that mints the canonical `JournalEntry` and fires everything downstream. The Journal is **saved**.
- **Publish** — **reserved exclusively for Legacy / Truth-Discovery** ("Publish to Legacy"): promoting a *saved* journal into the lifetime narrative. Never used for the Journal itself.

Lifecycle: **Journal Draft → Resume → Finish & Review → Review → Save Journal → `JournalEntry` → (post-save) Truth Discovery → Publish to Legacy.** The distinction is deliberate: the Journal is the private narrative of *today*; Legacy is the curated narrative of a *lifetime*. Saving and Publishing reinforce that difference.

---

## The deeper principle — the user is always journaling (read this first)

A reframe that makes this bigger than a Journal feature. **This is a Whole Life Journey capability that begins with journaling.**

> **The user is always journaling. The Journal is the guaranteed artifact. Everything else is optional.**
> **The conversation is the source. The Journal is one publication created from that source.** Other WLJ domains may also receive new truths discovered in the same conversation — because WLJ's founding principle is **Capture Once, Reuse Everywhere.**

The user never feels like they're updating modules. They are simply journaling. The Chief of Staff and WLJ determine whether other meaningful truths were discovered — and if so, they are *offered*, never silently created.

**Retire the old mental model:**
```
   Conversation  →  Journal  →  maybe Legacy          ✗  (wrong)
```
**Adopt this one:**
```
                     Conversation                       ← the SOURCE
                          │
                          ▼
                 Chief of Staff understands
                          │
                          ▼
                    Truth Discovery
                          │
   ┌────────────┬─────────┼─────────┬────────────┬───────────┐
   ▼            ▼         ▼         ▼            ▼           ▼
 Journal     Legacy   Memories  Timeline   Relationships  Faith  … (existing domains)
(ALWAYS)   (optional)(optional)(optional)   (optional)  (optional)
```

**Journal is always produced. Everything else is an optional, user-confirmed publication** of a truth the conversation happened to contain. Full architecture, domain mapping, restraint rules, and future-retrieval design are in **§22 — Truth Discovery & Publishing**. Nothing in that section is allowed to reduce or compete with the Journal (§22.4).

---

## Definition of Success (implementation north star)

**This governs implementation decisions.** When a technically elegant choice conflicts with this felt experience, **the felt experience wins** — unless doing so would violate the WLJ Constitution, safety, privacy, or deterministic-truth boundaries.

A successful Journal session feels like this:

- I never felt interrogated.
- I never felt analyzed.
- I never felt rushed.
- I never felt coached unless I explicitly asked for advice.
- I never felt like the Chief of Staff was trying to diagnose me.
- I talked more than the Chief of Staff did.
- The Chief of Staff listened without interrupting a story.
- The Chief of Staff remembered what mattered without performing its memory.
- The Chief of Staff asked questions that felt relevant to my actual life.
- Personal context felt natural, not forced, intrusive, or designed to prove the system remembered something.
- A simple question was used when no genuinely relevant personal question existed.
- I could journal on a blank page without the Chief of Staff interfering.
- I could invite the Chief of Staff into my writing only when I chose.
- I could speak naturally and hear the Chief of Staff respond naturally.
- The complete conversation was transcribed as it happened.
- A failure, refresh, disconnection, or microphone problem did not lose my words.
- The finished journal sounded like me.
- The finished journal was not a chat transcript, clinical summary, analysis, or AI essay.
- The finished journal preserved the details and moments I actually shared.
- Every completed session produced a normal Journal entry.
- The Journal entry remained complete even when no additional truth was discovered.
- Occasionally, the Chief of Staff recognized a story worth preserving beyond the Journal.
- Most sessions produced no additional suggestion.
- No Legacy story or other permanent truth was silently created.
- When a candidate was suggested, I could **Save it**, **Review and edit it**, **Hold it for later review**, or **Decline with "No Thanks."**
- I remained in control of what became permanent truth.
- I finished the session thinking: **"I should do this again."**

---

## 1. Product purpose and differentiator

### 1.1 Purpose
Give people the journal they'll actually keep — by removing the two things that stop people journaling: **the blank page** (nothing to say) and **the friction of writing** (too tired to type). WLJ removes both without changing what journaling *is*.

### 1.2 The differentiator
Not AI. Not voice. Every app has both. The differentiator is that **the Chief of Staff already knows the user's life** — goals, family, health, faith, projects, calendar, relationships, habits, history. A journaling app that knows nothing can only ask generic questions ("What was the best part of your day?"). WLJ can ask what a close friend would ask:

> *"You spent the afternoon with Haley and Parker. Where would you like to start?"*

### 1.3 The governing principle (refined)
> **Prefer a personal question when WLJ has a strong, genuinely relevant personal connection. Never force personalization merely to demonstrate memory. A simple, natural question is always better than an irrelevant or intrusive personal reference.**

Personal context is an **advantage, not an obligation.** Showing off memory is a failure mode; relevance is the bar. When there's no strong hook, a warm, simple invitation ("Tell me about your day — what stands out?") is exactly right.

### 1.4 What this is NOT
Not therapy, counseling, coaching, or an advice engine. The CoS is **an interested, informed journaling companion** — an interviewer who remembers your life and wants to hear the rest of the story, never a clinician. Enforced in §6 and §8, not just stated here.

---

## 2. One-canvas Journal — information architecture

There is **one Journal canvas.** The blank writing page is immediately available and is the default. The three methods are **clearly visible and understandable** — not a mandatory mode-selection gateway the user must pass through every time, and not invisible internal "stances." They are three obvious doors into one coherent room.

```
┌───────────────────────────────────────────────────────────────┐
│  Journal · Thursday, July 19                        📅  🔍  ⋯   │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│   ┌─────────────────────────────────────────────────────────┐ │
│   │  You spent time with Haley and Parker today.            │ │
│   │  Where would you like to start?                    ⤫    │ │  ← personal opener
│   └─────────────────────────────────────────────────────────┘ │    (dismissible, never generic)
│                                                               │
│   Title (optional — defaults to the date)                     │
│   ───────────────────────────────────────────────────────    │
│                                                               │
│   ▏ Start writing…                                            │  ← the blank page (default, sacred)
│                                                               │
│                                                               │
│                                                               │
│                                                               │
│   😊 Mood    🏷 Tags    🗂 Categories                          │  ← supporting metadata (unchanged)
│                                                               │
├───────────────────────────────────────────────────────────────┤
│   ✍️  Just Write        🎙️  Talk It Through     ✨ Write Together│  ← three visible methods, one bar
└───────────────────────────────────────────────────────────────┘
```

**IA rules:**
1. **The blank page is the default and is sacred.** Opening Journal = a sheet of paper. No AI, no suggestion, no chrome unless invited. Today's *Just Write* is preserved exactly.
2. **Three visible methods, one canvas.** *Just Write* is the resting state. *Talk It Through* and *Write Together* are one tap away and clearly labeled — a person always knows which of the three they're in and can move between them freely (§13).
3. **The opener is an offer, never a wall.** One personal (or simply warm) opening line, dismissible in one tap. It never blocks the page and never appears if it would be generic or intrusive.
4. **One truth spine.** Whichever door they use, the session terminates in a normal `JournalEntry` (§11, §18).

---

## 3. Detailed UX — Just Write (the default)

The blank sheet of paper. Unchanged from today, and protected.

**Behavior:**
- Opens focused on an empty rich-text body. Cursor ready. The user can write one sentence or several pages.
- **No AI interruptions. No automatic suggestions. No follow-ups.** Nothing happens that the user didn't ask for.
- All of today's affordances remain: rich text, optional title (auto-defaults to the date), `entry_date`, mood (5), emotions (multi-select), tags (user-scoped, inline-creatable), categories, prompt linkage, `?people=` prefill.
- **The one addition:** the dismissible personal opener above the page (§7), and the *Talk It Through* / *Write Together* affordances on the bar the user may ignore forever.
- Save / Save & Add Another / Cancel — unchanged. Autosave-to-draft runs quietly so a crash never costs work (§11), but the *feel* is a plain, quiet page.

**Acceptance:** a user who never taps a mic or invites the CoS has *exactly* the journal they have today — only with a better opening question when they want one.

---

## 4. Detailed UX — Talk It Through (the flagship)

A natural voice conversation with the user's Chief of Staff. The user speaks; the CoS listens and speaks back; **both sides are transcribed live**; the finished conversation becomes a **polished journal entry in the user's voice.**

### 4.1 The shape of the session
1. **Enter.** Tap *Talk It Through.* Microphone permission is requested (once) with a plain explanation (§15). The screen shifts to a calm listening surface — not a chat window.
2. **Open.** The CoS opens per the hierarchy in §7 — a strong personal opening if one exists, otherwise a simple natural invitation. **Never unexplained silence at the open.**
3. **Converse.** The user talks naturally. The CoS mostly listens (§6, §9), offering minimal presence and, when earned, **one** curious, personal, non-directive follow-up. The user may continue or interrupt at any time; the CoS yields immediately.
4. **See it captured.** A calm live transcript shows both sides as they speak (§10). A subtle indicator signals the entry is taking shape ("Your journal is taking shape · 3 moments") — never live polished prose (§8).
5. **End.** The user ends naturally ("that's it for tonight"), or taps End. The CoS closes warmly and briefly, then composes.
6. **Reveal.** The crafted entry appears — the delight moment (§12). The user reviews, edits inline, and saves. **Save Journal** → a normal `JournalEntry`.

### 4.2 What makes it *not* ChatGPT Voice
Restraint and knowledge. The CoS is comfortable with silence, doesn't reply after every sentence, and — because it knows the user's life — asks the question a friend would ask, not a generic one. It sounds like someone attentive at the end of your day, not a dictation utility or a chatty assistant. Full voice journey in §9.

### 4.3 Truth outcome
A *Talk It Through* entry is a normal `JournalEntry` (`created_via='voice'`) with the transcript linked as retrievable truth. Same model, same History, same CoS-readability, same signal extraction — and usually *richer* than a typed line because a spoken telling is longer and more detailed (§18).

---

## 5. Detailed UX — Write Together

> **REVISED 2026-07-19 (post production validation).** Write Together is **a conversation, not the editor with occasional questions.** The earlier "invite the CoS into your draft, one question at a time, return to writing" model was retired after production validation: *editors are for writing; conversations happen in conversations — and both produce the same `JournalEntry`.* The section below is the ratified model.

**Write Together is a dedicated, calm, focused *conversation* whose single purpose is to create the user's journal** — exactly like chatting with the Chief of Staff, except it runs under the Journal Conversation Playbook and ends by producing a journal. **The editor is not visible during the conversation.** The user is not writing prose while thinking; the CoS is helping them think.

**Behavior:**
1. From the Journal chooser ("How would you like to journal today?"), the user picks **💬 Write Together** and enters a dedicated conversational workspace — **not** the general CoS chat, and **not** the editor.
2. The CoS opens per the Playbook (§7 hierarchy): *"What would you like to remember today?"* or a strong personal opener.
3. **It's just a conversation.** The user types; the CoS replies; the thread continues naturally — no editor, no side panel, no "Ask another question," no buttons after each turn. One conversation, one purpose. The CoS operates under the full Playbook (§6) and Memory Model.
4. When the CoS judges it has enough (Playbook §14), it says something like *"I think I have your journal."*
5. It **generates the entry** in the user's voice (§12 fidelity rules). The **journal is revealed only now** — not built beside the conversation (§8).
6. The user **reviews, edits if desired, and saves** — **Save Journal** creates the canonical **`JournalEntry`**.

**Posture:** the full conversation behavior (§6) and memory (Conversational Memory Model) apply — preservation not understanding, follow energy, one question at a time, silence, never therapy. It never forces a topic to completion and never turns the conversation into coaching.

**Truth outcome:** a normal `JournalEntry` (`created_via='voice_together'` when produced from a text conversation), identical spine to any other entry. Truth Discovery runs **post-save** (§22), never during the conversation.

**Relationship to Talk It Through (§4):** these two are now **the same experience with a different modality** — Write Together is typed, Talk It Through is spoken. Same conversation, same Playbook, same Memory Model, same generation → review → Save Journal → `JournalEntry`. Only the input/output surface differs.

---

## 6. Full conversational behavior rules

Product principles, enforced through the shared CoS prompt contract and a small deterministic **conversation budget** — not vibes, and **not a bespoke Journal reasoning engine** (§ Architecture Boundary).

**The interviewer's posture:**
- Prefer a personal question when the connection is strong and relevant; otherwise a simple natural one (§1.3, §7).
- **Follow excitement more than chronology.** If they light up, go there.
- **One thoughtful question beats five shallow ones.** Hard budget: the CoS holds **at most one open question at a time.**
- Do not interrupt a story in motion. Wait for a genuine landing.
- **Silence mid-conversation is acceptable** and often better than a reply (§9.2). (This is distinct from the *opening*, which is never silent — §7.)
- If the user changes subject, follow them. Don't drag them back.
- Do not force a topic to completion. An unfinished thread is fine.
- Ask about **events, people, actions, expectations, sensory detail, and what it meant to them** — the interviewer's toolkit.
- Notice excitement, emphasis, or repeated topics **conversationally** ("you keep coming back to the field — sounds like that was the day"), never analytically.
- It may ask whether something brought back a memory, and what the user wants to remember.

**The bright lines (enforced in the prompt contract):**
- Never name, label, or diagnose the user's emotion. **Emotion is reflected only after the user names it first** — then the CoS may follow it ("you said that one stung — when did it tip?"), still without labeling or interpreting.
- Never say "you should" / "you need to" / "you have to."
- Never analyze the user psychologically or offer interpretations of their inner life.
- Never manufacture emotional certainty; never treat an ordinary frustration as a deep issue.
- Never be preachy, never moralize, never turn the session into coaching.
- Never try to "fix" the user. The goal is a **richer story**, not a resolved problem.

**Safety exception (single, minimal, non-clinical):** if a telling contains genuine crisis language (self-harm/harm), the CoS drops the interviewer role, responds as a caring human, and surfaces real help resources **once**, gently — it does not diagnose, does not counsel, and does not craft that moment into prose. This is the only place the curiosity posture yields. Final wording to be set with a qualified reviewer before build (§ Open decisions).

---

## 7. Personal-context selection and restraint rules

This is the differentiator made real, and it is a **truth-delivery** problem (Layer 1) — WLJ composes relevant facts deterministically and hands them to the model to *voice*. WLJ never builds a reasoning engine to decide what's meaningful.

### 7.1 Sources (all already in WLJ)
Calendar / today's events · Goals & milestones (`purpose`) · People & relationships (`apps.people`) · Health signals (non-clinical framing) · Faith journey · Recent journal themes (`content_intelligence`) · History / streaks / recurrence · curated `JournalPrompt` library (fallback only).

### 7.2 The opening hierarchy (never silence)
1. **A strong, genuinely relevant personal opening,** when one exists:
   > *"You spent time with Haley and Parker today. Where would you like to start?"*
   > *"You had the payroll training this morning. How did it go?"*
2. **A simple, natural invitation** when no strong hook exists:
   > *"Tell me about your day. What stands out?"*

Never open with unexplained silence. Never open with a *generic prompt dressed up as personal.*

### 7.3 The composition rule
A deterministic **`journal_opening` truth composer** (new, thin — reuses existing `*Queries`, adds no new aggregation) assembles ranked *candidate hooks*, each resolved to facts (who / what / when / freshness / confidence). The model **voices** the best hook; it never invents one. If WLJ hands it no strong hook, the model receives an honest "no strong hook — open with a simple, warm invitation" instruction.

### 7.4 Restraint rules (avoid forced/performative/intrusive personalization)
- **Relevance over recall.** Never surface a hook just to prove memory. If it isn't clearly worth asking about, don't.
- **Recency + specificity win.** "This afternoon with named people" beats "a goal from three weeks ago."
- **One hook, not a briefing.** The opener surfaces *one* thing. The CoS is curious, not a status report.
- **Rotate, don't nag.** Never open on the same thread two sessions running unless the user kept it alive.
- **Respect sensitivity and the closed door.** Avoid intrusive references (health specifics, hard relationships) as *openers*; if a user dismisses a hook, that subject goes quiet for a while.
- **Facts, never verdicts.** The engine surfaces things to be curious about, never a conclusion ("you seem stressed"). The CoS asks; the user concludes.

---

## 8. The therapist/advice boundary — concrete examples

The single most important guardrail. The CoS is an interested companion, not a clinician or advice engine.

**✅ Allowed (curious, personal, non-directive):**
> *"That sounds like it was a lot of fun. Which ride was your favorite?"*
> *"How did it feel being back on the softball field? Did it bring back memories from your Alabama baseball days?"*
> *"What was Parker's reaction?"*
> *"Was fixing the hot tub as satisfying as you expected after working on it all that time?"*
> *"You keep coming back to the meeting — is that the part of the day that stuck with you?"*
> *"What do you want to remember about today?"*

**🚫 Prohibited (diagnosis / advice / psychologizing):**
> *"This suggests unresolved anxiety."*
> *"You should establish better boundaries."*
> *"I can see why you're depressed."*
> *"It sounds like you have a pattern of avoidance."*
> *"You need to talk to your dad about this."*
> *"That's your inner critic talking."*

**The test:** if a sentence *names a condition, prescribes an action, or explains the user to themselves,* it is prohibited. If it *asks about the story, the people, the details, or the meaning to them,* it's allowed.

---

## 9. Full voice-session journey

The target is **natural, full conversational voice** — the canonical design, not push-to-talk. The user speaks; the CoS listens; the CoS responds aloud; the user may continue or interrupt; the whole exchange is transcribed live. It must feel like speaking with someone attentive who knows you — not operating a dictation tool or sending voice messages. (Technical delivery may be phased — §21 — but the design represents the complete intended experience and is not weakened around an easier first build.)

### 9.1 The feel
Unhurried. The CoS is comfortable with quiet, in no hurry to move the user along, and never sounds like it's waiting for its turn to talk.

### 9.2 Five kinds of silence (the core of the pacing design)
1. **Reflective silence** — after something weighty, the CoS *waits.* A beat of quiet says "I'm still with that."
2. **Facilitative silence** — when the user pauses mid-thought, the CoS holds space instead of jumping in. Most pauses are thinking, not turn-ends.
3. **Empathic silence** — after something emotional, the CoS stays present rather than analyzing or consoling; it follows softly *only if invited.*
4. **Holding space** — during a long telling, minimal backchannel ("mm," "yeah") signals presence without taking the floor.
5. **Immediate response** — reserved for genuine turn-ends and direct questions to the CoS. The exception, not the default.

**The turn-taking hazard (designed around):** within-turn pauses are typically *longer* than between-turn gaps, so naive silence detection cuts people off mid-thought. WLJ biases hard toward **not** speaking — a longer "are they really done?" threshold plus content cues (a trailing "so…" / "and yeah…" means keep listening). **Better a half-beat too long than a story cut short.**

### 9.3 Interruption
The user may talk over the CoS at any time; the CoS stops immediately and listens. The user is always the primary speaker. The CoS never insists on finishing its sentence.

### 9.4 Reflect before asking
The CoS reflects a fragment before a question (light, not parroting) to prove it was listening:
> *"The whole afternoon at the field… what was the best part?"*

### 9.5 Transitions & pace
Soft transitions, never abrupt jumps ("Can I come back to your dad for a second?"). Pace matches the user — brief when they're fast and excited, slower when they're thoughtful. Never lists or bullet-points aloud; never "summarizes back" like a meeting bot.

### 9.6 Ending
No hard stop required. The user can simply stop, say "that's it," or tap End. The CoS closes warmly and briefly — *"Thanks for telling me about today. Give me a moment and I'll write it up."* — then composes (§12). No gamified celebration in the moment.

---

## 10. Live transcript behavior

The live transcript is **essential** — it's the user's reassurance that they're being heard, and it's the durable raw material of the entry.

- **Both sides, live.** User speech and CoS speech both appear as they occur, clearly attributed, in a calm readable column.
- **Verbatim-ish and unpolished on purpose.** The transcript is raw material, not the product. It is *not* the polished entry.
- **Calm, not busy.** No animations that pull the eye; the newest line settles into place. The user can scroll back at any time.
- **Progress, not prose.** Alongside the transcript, a subtle indicator ("Your journal is taking shape · 3 moments captured") signals the entry is forming behind the scenes — **never** scrolling polished prose the user feels compelled to monitor or correct (§8).
- **Persisted incrementally** (§11): every completed segment is saved the instant it's final.

---

## 11. Incremental persistence and session recovery

**Requirement: the user loses nothing** — mic failure, refresh, network drop, provider failure, accidental navigation, dead battery. Designed before implementation.

- **Durable-first capture.** Every **completed speech segment** (user or CoS) is persisted to a durable server-side draft **the instant it's final** — not held in browser memory. The client is a *view* onto server truth, not the source of truth.
- **A resumable session object.** A `JournalDraftSession` (working name) holds: state (recording / paused / reviewing), ordered transcript segments, the structured *moments* the entry will be built from, the target `entry_date`, and the method (voice / together). It survives any client death.
- **No audio.** Transcript recovery is required; **the original audio is not retained** — no audio storage, no playback, no Legacy audio asset (§17, § Non-goals). This is journaling through voice, not a multimedia capture feature. Segments are persisted as **text**.
- **Reopen = resume.** Returning to Journal offers: *"You have a journal draft in progress — pick up where you left off?"* (whether the user left deliberately or after a crash). Reconnect mid-conversation; the transcript is intact.
- **Offline tolerance.** The client buffers locally and reconciles to the durable session on reconnect. A dropped connection *pauses*; it never destroys.
- **Explicit disposal only.** A draft is discarded only when the user saves the final journal (draft → entry) or explicitly abandons it. Idle drafts are offered back, then aged out on a long timer *with warning* — never silently deleted.
- **Request-path safe.** Persisting segments and structuring moments goes through the non-blocking write path (`safe_enqueue`), never a synchronous heavy call on the interactive request (`WLJ_REQUEST_PATH_SAFETY.md`).

---

## 12. End-session journal generation and review

The finished entry is **not a transcript, not a summary, not bullet points.** It reads like the user wrote it on a good night.

**Fidelity rules (a truth-fidelity problem governed by the Truth/Action Contract):**
- **Only what was actually said.** The entry may reorganize, smooth, and connect — it may **never invent** an event, feeling, detail, or conclusion the user didn't express. No embellishment, no inferred emotions, no "and that made you realize…"
- **Their voice.** Generation is anchored to how *this person* actually writes (from their past `body_plain`) — length, cadence, terse vs expansive. Not a generic "nice journal voice."
- **First person, past tense, theirs.** It's their diary, not a report about them.
- **Preserve the specifics.** Names, places, the exact small details that make it real survive into the prose. Generic-ization is failure.

**Review = authorship, not AI-review.** The user saves **their own words rendered back to them** — that is ownership, not reviewing a machine's guess (this is *not* the prohibited AI-Review pattern).
- Presented as *a draft of your own words*; edit inline freely (the rich-text editor is right there).
- **Approve** → saved as a normal `JournalEntry` (fires the full intelligence chain, signals, etc.). **Discard** → nothing kept.
- **Never auto-save a generated entry unseen.** The user is the author; the CoS is the scribe.

---

## 13. Switching between methods without losing content

The three methods share one canvas and one draft, so a user can move between them mid-session and **never lose a word.**

- **Write → Talk.** Tap the mic mid-entry; existing typed text stays on the page and becomes part of the same draft. The CoS reads what's there before it opens.
- **Talk → Write.** Stop speaking and type; the transcript-so-far and any structured moments remain; typed text merges into the same draft.
- **Write → Write Together → Write.** Invite the CoS, answer one question by voice or text, dismiss it, keep writing — seamless.
- **Talk ↔ Write Together.** Fluid; both are "CoS present," differing only in whether the primary channel is voice or text.
- **One draft, one entry.** All switching operates on the same `JournalDraftSession` → one `JournalEntry`. No parallel record type is created because an entry began through voice or collaboration (§ Architecture Boundary).

---

## 14. Mobile and desktop behavior

**Mobile (primary for voice):**
- Full-width calm surfaces; thumb-reachable controls; large tap targets (≥44×44px); 16px input minimum (no iOS zoom).
- *Talk It Through* is designed for the phone at the end of the day — big mic state, minimal chrome, live transcript scrollable above the controls, End button always reachable.
- Handles the phone realities: screen lock, incoming call, app backgrounding → session pauses and recovers (§15), never loses segments.
- One-hand operation; the review/edit step uses the standard mobile rich-text editor.

**Desktop:**
- The blank page can breathe (comfortable measure, generous margins) — closer to writing at a desk.
- *Talk It Through* shows the live transcript in a calm side column with the listening state centered.
- Book/page/calendar reading views (existing) remain desktop-strong.
- Keyboard-first: shortcuts for new entry, save, invite-CoS, start/stop voice.

Both: same one-canvas IA, same three visible methods, same truth spine. Layout adapts; the model does not fork.

---

## 15. Empty, loading, permission, failure, reconnect & recovery states

Every state below is a first-class part of the design (visualized in `journal_experience_mockups.html`).

| State | Behavior |
|---|---|
| **Empty (no entries yet)** | Warm first-run: the blank page + a simple invitation ("Tell me about today — write it, or talk it through"). Never an empty void. |
| **Opener loading** | The page is *immediately usable*; the personal opener resolves quietly and appears when ready, or not at all. Writing is never blocked waiting for a hook. |
| **Mic permission request** | Plain-language ask *before* the OS prompt: "To talk it through, WLJ needs your microphone. Your words become your journal entry — audio isn't stored." Then the OS prompt. |
| **Mic permission denied** | Non-punitive: "No problem — you can still journal by writing, or turn on the mic later in settings." Fall back to Just Write with the typed draft intact. |
| **Listening (idle)** | Calm "listening" state; clear that the CoS is present and attentive; nothing recording-red or alarming. |
| **User speaking** | Live waveform/level + live transcript of the user's words; CoS visibly holding space. |
| **CoS speaking** | CoS turn indicated; its words appear in the transcript; user can interrupt anytime (barge-in stops the CoS). |
| **Thinking / composing pause** | If the CoS needs a beat, a gentle "…" presence — never a spinner that feels like latency. |
| **Transcription failure (partial)** | The segment is flagged unobtrusively ("didn't catch that — say it again?"); prior segments are safe; the session continues. |
| **Transcription failure (sustained)** | Graceful degrade to Just Write with everything captured so far preserved as a draft; explain plainly. |
| **Model failure (opener)** | Silently fall back to the simple natural invitation (§7.2). The page still works. |
| **Model failure (mid-session)** | The CoS pauses; the transcript keeps persisting; "I lost my footing for a second — keep going, I'm still capturing everything." No lost words. |
| **Model failure (composition)** | The entry can't be crafted right now → offer the entry built from the user's own transcript segments (their words, lightly ordered) + retry later. Never lose the telling. |
| **Network drop / reconnecting** | Client buffers locally; a quiet "Reconnecting…" indicator; on reconnect, reconcile to the durable session. Voice pauses, doesn't die. |
| **Recovered session** | On return (deliberate or after a crash): "You have a journal draft in progress — pick up where you left off?" with the transcript restored. |
| **Saving / generating** | The reveal's compose moment (a brief, satisfying assemble) — not a bare spinner. |
| **Save success** | Lands on the finished `JournalEntry` detail (existing page), fully in the truth spine. |
| **Offline (no connection at all)** | Just Write works fully offline and syncs later; Talk It Through requires connectivity and says so plainly, preserving any typed draft. |

**Principle:** no state ever costs the user their words, and no failure is expressed in jargon. Every dead-end degrades to *"you can still write,"* with the draft intact.

---

## 16. Accessibility requirements

- **Voice is an accessibility *win* and must not become a barrier.** Everything achievable by voice is achievable by writing; nothing is voice-only.
- **Live captions by design.** The live transcript *is* real-time captioning of the CoS's speech — usable by Deaf/hard-of-hearing users as a text conversation (type instead of speak).
- **Screen-reader complete.** All states, controls, and the transcript are properly labeled and announced; turn changes and new transcript lines are announced politely (ARIA live regions), not spammed.
- **Keyboard-operable end to end** — start/stop voice, interrupt, invite CoS, end session, edit, save.
- **Motion & sensory.** Respect reduced-motion (the reveal's assemble animation degrades to a simple fade); nothing conveyed by color/animation alone; the "listening/speaking" state has a text label, not just a color.
- **Legible defaults.** ≥16px inputs, sufficient contrast in light and dark, resizable text, generous targets.
- **No time pressure.** Silence is designed-in; the UI never rushes a user to speak or penalizes a long pause.

---

## 17. Privacy boundaries

- **A journal is the most private surface in WLJ.** Everything here is user-owned, user-scoped, private by default.
- **No audio retention.** The original voice recording is **not stored** — transcript only. No playback, no permanent voice storage, no Legacy audio asset in this milestone (§ Non-goals).
- **Transcript is the user's.** Stored as their private draft/entry text; deletable; subject to the same soft-delete/hard-delete and archive controls as any entry.
- **Provider data flow is disclosed and bounded.** Speech and text pass through the single Model Interface seam to the configured provider only for transcription/conversation/composition; no third path, no naming a provider as an identity.
- **Personal context is drawn only from the user's own WLJ truth** — never external sources — and only to make *their* questions relevant.
- **Sensitive-topic restraint** (§7.4): health specifics and hard relationships are not used as *openers*; the user always leads into sensitive ground.
- **Consent is explicit for the mic**, revocable anytime, and denial degrades gracefully (§15).

---

## 18. Existing-capability preservation inventory (must not regress)

All three methods terminate in the existing canonical `JournalEntry`. These consumers keep working **unchanged** because they read the entry, not the method.

**Data model:** rich-text `body` + `body_plain` shadow; `title` (auto-dates) / `entry_date` / `word_count`; `mood` (5) **and** `emotions` M2M; `categories`, user-scoped `tags`, `prompt` FK; soft-delete (30-day) + archive + restore + hard delete; `created_via` (add `voice`, `voice_together`); `EntryLink`; `JournalSignal`.

**Reading modes:** list (filter + search), calendar, page-scroll, book, home dashboard — all retained.

**Filters/bulk:** category / tag / mood + full-text over `title`/`body_plain`; bulk archive + delete.

**Home:** total/week/month, streak, mood distribution, popular tags, daily prompt, engine insight.

**Prompts:** fixtures, faith-gating, random/daily/suggested/browse, entry→prompt linkage, `?people=` prefill; HTMX inline tag creation.

**CoS / Truth (highest-risk — preserve every one):** `JournalQueries` (canonical read service); `JournalDomainTruth` (current: days_since_entry / last_entry / themes; history: mood; describe/describe_one) + question specs (`journal.entries`, `journal.entry_by_date`, `journal.mood_history`, `journal.this_week`, `journal.themes`, `rel.journal_mentions`); `JournalCosActions` (append-don't-duplicate CRUD + reflections); `fire_intelligence` chain + `JOURNAL_ENTRY_CREATED` event; milestone-completion AI; routine auto-complete (entry_date-anchored); NLP `JournalSignal` + deterministic emotion signals; canonical people @mention recognition/reconcile; `content_intelligence` (themes / recurring concerns / sentiment trajectory → `analyze_journal_for_cos`); `get_journal_metrics` + canonical `calculate_journal_streak`; relationships→journal footprint; `import_chatgpt_journal`.

**Net effect:** History and CoS truth-access are **strictly enhanced** — voice tellings are longer and richer, yielding *more* signal, not less. New provenance (transcript as retrievable truth via the existing multimodal artifact seam) is additive. **No parallel journal record type** is introduced. Any **discovery publications** (§22) are *separate objects in their own existing domains*, each linked back to the same source conversation — they never alter, gate, or replace the `JournalEntry`, which is produced unconditionally.

**Inventory clarifications:** the declared `GratitudeEntry`/`add_gratitude` capability has *no backing model* today (nothing to preserve — a clean spot to add gratitude later); there is *no* existing attachment/voice implementation (so those are net-new, not regressions). Journal has no `page_summary` provider today — this redesign is the natural moment to ship the overdue overview `summary:` provider (`PageSummaryMixin`).

---

## 19. Product success criteria

The only real metric (per `WLJ_PRODUCT_VISION.md`): *if this were the only conversation a paying customer ever had with their assistant, would they want to do it again tomorrow?* Concretely, this design succeeds when:

1. **The question feels personal and relevant** — users say "it asked exactly what I'd want to be asked," and *not* "it name-dropped my data to show off."
2. **People journal who otherwise wouldn't** — voice removes the friction; the blank-page barrier is gone.
3. **The finished entry sounds like the user** — reading it back, it reads like *them*, not like AI. Low edit-rate on generated entries is a signal; "this is exactly what I would've written" is the target.
4. **Zero lost words, ever** — no crash, drop, or failure costs a telling. Recovery is invisible and reliable.
5. **It never feels clinical** — no user reports the CoS "diagnosed," "lectured," or "gave advice."
6. **Trust in the archive** — the journal reads back as an authentic record of the user's own voice over time; History and CoS answers about the journal stay correct.
7. **They come back** — return-to-journal rate rises; the ritual sticks.
8. **Discovery feels like a gift, not admin** — when the CoS offers to preserve something beyond today, users say "yes, exactly." Measured by a *high accept-rate at a low frequency* (rare + welcome, never noisy); and cross-domain enrichments ("this connects to your story about…") land as delight, not clutter (§22).

---

## 20. Explicit non-goals

- Not a therapist, coach, counselor, or advice engine (§8).
- Not a new category — it's **Journal.** No "Reflection" rebrand.
- Not a forced mode-selection gateway, and not invisible internal stances — three visible methods, one canvas (§2).
- Not a multimedia capture feature: **no audio retention, no playback, no Legacy audio asset** this milestone (§11, §17).
- Not a live polished-prose spectacle: the entry assembles behind the scenes and is revealed at the end; **no off-by-default live-prose toggle** this milestone (§8).
- Not a mood-tracker-first app; mood/emotions stay supporting, never the headline.
- Not a gamified streak machine; the reward is the conversation and the artifact.
- Not a generic-prompt library; if there's no strong hook, a *simple natural invitation*, never a canned prompt dressed up as personal (§7).
- Not a chatty voice assistant; restraint is the feature (§9).
- Not a Journal reasoning engine, question classifier, emotion-scoring engine, scripted branching engine, or separate Journal AI. The shared CoS + Model Interface seam does the reasoning; WLJ composes truth (§ Architecture Boundary).
- Not a parallel record type for voice/collaboration — one canonical `JournalEntry` (§13, §18).
- **Not a module the user manages.** Discovery never makes the user choose a destination, never creates anything silently, never floods (≤1 suggestion/session, usually none), and never invents a domain to hold a truth — existing owners only (§22).
- **Legacy is not a second journal** and never competes with, delays, or reduces the Journal (§22.4, §22.6).

---

## Architecture boundary (Constitutional)

Stays fully inside the WLJ Constitution and the LLM Truth/Action Contract:
- **WLJ owns** deterministic truth, persistence, incremental capture, validation, recovery, actions, and provenance.
- **The conversational model owns** conversation, curiosity, reasoning, and journal composition.
- **Do not build** a Journal reasoning engine, question classifier, emotion-scoring engine, scripted branching engine, or a separate Journal AI.
- **Use the same** Chief of Staff relationship and Model Interface seam as the rest of WLJ — provider-agnostic, never naming a provider or assistant as a system identity.
- **Use existing truth surfaces** to supply relevant personal context (§7).
- **All three methods** terminate in the canonical `JournalEntry` spine (§18); **no parallel record type.**
- **Discovery creates nothing silently.** Discovered truths become **candidate intents the user confirms**; **WLJ (not the model) creates** the deterministic object in its owning domain, audits it, and links it to the source conversation (§22). This is the **existing intake spine** (perceive → candidate named intent → validate → confirm → execute → audit → link), sourced from a conversation — **no new discovery engine, classifier, or scorer.**

---

## 21. Recommended implementation milestones (sequence only — not an implementation plan)

Smallest-magical-thing first; each milestone produces the same `JournalEntry` truth spine, so History and CoS truth-access are correct at every step. The canonical product design (full conversational voice) is fixed; only *delivery* is phased.

1. **The Curiosity Engine + personal opener** on today's Just-Write page. Ships the entire differentiator with zero voice work — questions get personal (and appropriately restrained) immediately. Also lands the overdue journal `summary:` provider.
2. **Durable draft-session substrate** (§11) — the recovery backbone everything else stands on (text segments, no audio).
3. **Write Together** (text + CoS, one question at a time) — proves the conversation philosophy and the boundary without the voice stack.
4. **Talk It Through — full conversational voice** (§9): streaming ASR + low-latency TTS through the Model Interface seam, five-silences pacing, barge-in, live transcript, structured moments → generated entry → authorship review. The flagship, built to the complete vision.
5. **Cross-method switching polish** (§13) and the full state matrix (§15) hardened across mobile + desktop.
6. **Truth Discovery & Publishing v1** (§22) — *only after the journal spine is solid, because the Journal must never depend on discovery.* Post-save single-candidate suggestion → user confirm → **WLJ** creates the object in its owning domain → audited + linked to the source conversation. **Start with Legacy Story** (the clearest existing owner), then extend to relationship milestones / achievements. Then add **cross-domain retrieval enrichment** (§22.8 — "connects to your story about…") once there are published objects to connect to.
7. **Success instrumentation** (§19) — edit-rate on generated entries, recovery reliability, return rate, "felt clinical?" guardrail signal, and discovery accept-rate-at-low-frequency.

(If real-time full-duplex voice must be staged for engineering reasons, an interim within milestone 4 may ship natural-turn voice before full barge-in — but the design target, and what we build toward, is complete conversational voice. The vision is not weakened around the easier first step.)

---

## 22. Truth Discovery & Publishing (the WLJ capability that begins with journaling)

The Journal is where this capability first appears, but it is not a Journal feature. It is a whole-platform capability: **a conversation is a source of truth, and truth can be published to more than one place.**

### 22.1 Source vs. publication
- The **conversation (its transcript) is the source of truth** for the session.
- The **`JournalEntry` is the guaranteed publication** — the user's personal narrative of the day or topic. It is produced every time, unconditionally.
- **Other publications are optional** — a Legacy story, a relationship milestone, a faith testimony, etc. Each is a *separate deterministic object in its owning domain*, derived from the same source, created only if the user confirms it.

This is exactly **Capture Once, Reuse Everywhere**: the user captures once (they talk), and WLJ reuses the captured truth wherever it legitimately belongs — without the user ever managing modules.

### 22.2 The architecture already exists — this is the intake spine, generalized
We are **not inventing a new mechanism.** Truth Discovery is the **`WLJ_MULTIMODAL_INTAKE_ARCHITECTURE` spine**, sourced from a conversation instead of an uploaded file. A journal conversation is simply **another arrival**:

```
arrival (conversation)  →  the model PERCEIVES possible truths
                        →  each becomes a candidate NAMED INTENT (+confidence, +proposed owning domain, +human "why")
                        →  ONE truth spine:  validate → dedup → confirm (user) → execute (WLJ) → audit → link
                        →  the created object is first-class truth, linked back to the source conversation
```
It reuses, unchanged: the **artifact seam** (`source_artifact_id`), per-domain **intent definitions + action handlers**, the **"AI proposes → WLJ validates → user confirms"** pattern (as in the Person consolidation program), **DomainTruth** links, and the **audit** trail. **No discovery engine, no classifier, no scoring model is built inside WLJ.** The conversational model recognizes possibilities; WLJ owns truth.

### 22.3 The Constitutional boundary — nothing is ever created silently
> **The Chief of Staff recognizes possibilities. WLJ owns truth. The CoS never silently creates a permanent object.**

The CoS surfaces a **candidate**, in the user's language:
> *"I think today's conversation captured a story that belongs in Legacy."*
> *"I think today's conversation documented an important family milestone."*
> *"I think today's conversation captured a memory worth preserving."*

The **user reviews → WLJ validates → WLJ creates** the deterministic object, audits it, and links it to the source conversation. This is fully inside the Constitution. It is **not** the prohibited "AI Review" pattern (WLJ never asks the user to bless *its interpretation of their data*) — confirming a candidate object the user wants to keep is **the user's own authorship and consent**, which is permitted and correct.

### 22.4 Journal always wins
The Journal is **never optional and never diminished.** Every session ends with a `JournalEntry`. Discovery runs **after** the entry is safely saved and never competes for the reflective moment (§22.7). If discovery fails, is declined, or finds nothing, **the Journal is exactly as complete as it would have been.** Legacy and every other domain are downstream publications — never a substitute for, and never louder than, the daily journal.

### 22.5 Where discoveries belong — map to EXISTING domains only
Think broadly, but **do not invent domains.** Each discoverable truth maps to a domain WLJ already owns. The candidate proposes the destination; **the user never chooses a module** (§22.7).

| Discovered truth | Natural owner (existing) | Mechanism | Notes / confidence |
|---|---|---|---|
| **Legacy story** ("Teaching Ashley to Drive", "Dad's Advice About Work") | **Legacy** | candidate `create_legacy_story`, linked to source | High — clearest owner; the default home for "deserves to live beyond today." |
| **Family history / family milestone** | **Legacy** (family unit / GEDCOM) | link to Person/family + Legacy story | High — reuses family-unit truth. |
| **Relationship milestone** | **People / relationships** (`apps.people`) | person milestone + canonical `PersonMention` | High — @mention + people footprint already exist. |
| **Personal achievement** | **Purpose** (goals/milestones) | milestone/achievement record | High — reuses milestone-completion path. |
| **Faith testimony** | **Faith** | faith testimony/reflection surface | Medium — *verify a testimony object exists*; else Journal + faith tag. |
| **Travel experience / place** | **Legacy Places** (canonical `Place` + map) | Place / visit, linked to source | Medium — a *trip* grouping may not exist → fall back to Place + Legacy story. |
| **Memory** (a preserved moment, lighter than a full story) | **Legacy** preservation layer *(or `life`)* | preserved moment | **Needs a home decision** — recommend Legacy preservation; do **not** invent a "Memories" domain. |
| **Timeline event** | life timeline / **Significant Event pipeline** | timeline entry | **Needs a home decision** — confirm which surface owns a life timeline. |
| **Tradition** | **Legacy** (family) / a traditions surface | Legacy story or family record | **Needs a home decision** — recommend Legacy story until a dedicated owner exists. |
| **Lesson learned** | usually **Journal** itself; if it's advice *from someone*, **Legacy** story | journal reflection or Legacy story | Rarely its own object — resist over-modeling. |

**The fallback rule (non-negotiable):** *if no existing domain cleanly owns a discovered truth, there is NO suggestion — the Journal already captured it.* We never invent a domain to hold a discovery, and we never nag the user about a truth that has nowhere legitimate to go. When in doubt, it's a Legacy story or it stays in the Journal.

### 22.6 Legacy as a publication (not another journal)
Legacy becomes **one possible publication of the conversation**, and it is deliberately *unlike* the Journal:

| | **Journal** | **Legacy** |
|---|---|---|
| Shape | Chronological, daily/topic narrative | Curated, **non-chronological** stories |
| Scope | Everything the user chose to write | Only what **deserves to live beyond today** |
| Cardinality | Guaranteed, every session | Rare, selective |
| Examples | "Thursday, July 19" | *"Teaching Ashley to Drive" · "The Day Parker Hit His First Home Run" · "My First Day at Alabama" · "Dad's Advice About Work"* |

The user may journal about these moments; the CoS may recognize them; **the user decides** whether they belong in Legacy. Legacy is not a second journal and must never feel like one.

### 22.7 Restraint — one quiet whisper, never a flood
- **After the entry is saved, never during the telling.** Discovery never interrupts the story and never blocks the Journal.
- **At most ONE suggestion per session.** One is powerful; five are annoying.
- **Most sessions produce none.** The bar is "this clearly deserves to live beyond today," not "this is mentionable." Silence is the common case.
- **Single, gentle, dismissible.** *"I think this conversation captured something worth preserving beyond your journal."* One tap to keep, one tap to decline.
- **Declining teaches quiet.** A dismissed subject/type goes quiet; the CoS does not re-pitch the same kind of thing repeatedly.
- **The user never chooses a destination.** The candidate names where it would go ("as a Legacy story"); the user only confirms or declines. They are only ever *journaling*.

### 22.8 Future retrieval & cross-linking (design for years later)
Because every publication and the `JournalEntry` share the **same `source_artifact_id`** and are cross-linked as truth, the archive becomes a connected web, not isolated records. Years later, at journal time, the CoS can retrieve *related* truth by **meaning** — using the **existing `DomainTruth` entity surfaces + the capability-semantics registry**, not a new reasoning engine — and offer an enrichment:

> Today the user journals about **Parker learning to drive.**
> The CoS recognizes: *"This connects beautifully to your Legacy story about **teaching Ashley to drive**."*

The connection **enriches both** — today's entry gains resonance; the older Legacy story gets re-surfaced and lives again. This is a **truth-retrieval + link** (a fact and a pointer), never a verdict or interpretation. It is offered with the same restraint as §22.7 — a gift, not a notification stream.

### 22.9 Discovery-specific non-goals
- Never silently create objects — candidates only, user-confirmed (§22.3).
- Never make the user pick a module — they only journal (§22.7).
- Never flood — ≤1 suggestion/session, usually none (§22.7).
- Never invent a domain to hold a discovery — existing owners only, else no suggestion (§22.5).
- Never let Legacy (or any domain) reduce, delay, or compete with the Journal (§22.4).
- Never build a discovery/classification engine inside WLJ — the model perceives; WLJ validates, creates, audits, links (§22.2).

---

## Appendix — research that shaped this

- **Expressive-writing science (Pennebaker, 40+ yrs):** benefit comes from continuous, uninterrupted immersion → protect reflection; reveal-after, don't monitor-during (§8).
- **Voice-story products (Remento *Speech-to-Story*, Reflection.app, Mindsera Call Mode):** the winning pattern is *talk now, receive a crafted written artifact after* (§4, §12).
- **Oral-history & active-listening practice:** open-ended questions, follow-ups over scripts, follow the interesting thread, **silence as the interviewer's most potent tool** (§6, §9).
- **Conversational-pacing & turn-taking research:** five silence types; within-turn pauses exceed between-turn gaps → bias hard against interrupting (§9.2).
- **Guided-prompt apps (Stoic, Reflectly, Day One):** their ceiling is *generic* prompts because they know nothing about the user — the ceiling WLJ's truth layer breaks through (§1, §7).
```
