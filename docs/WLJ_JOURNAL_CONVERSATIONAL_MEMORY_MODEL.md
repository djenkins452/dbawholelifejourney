# WLJ Journal Conversational Memory Model (Canonical)

**Status:** RATIFIED design — the governing philosophy for how the Chief of Staff *remembers* during a journaling conversation (implementation not started)
**Owner:** Danny + Chief Architect
**Date:** 2026-07-19
**Governs:** *what the user should experience* as "being remembered" during a Journal session — product behavior, not engineering.
**Companions:** `WLJ_JOURNAL_EXPERIENCE.md` (product & UX vision), `WLJ_JOURNAL_CONVERSATION_PLAYBOOK.md` (how the CoS conducts the conversation), `WLJ_PRODUCT_VISION.md`, `WLJ_LLM_TRUTH_ACTION_CONTRACT.md`.
**Scope guard:** this document says **nothing** about how memory is built. No context windows, retrieval, stores, summaries, or internals — those are the engineering team's to decide. This is the *felt experience* the engineering must produce.

---

## 0. The one law (read this first)

Everything below reduces to a single behavioral law:

> **The Chief of Staff remembers the way a caring person remembers — not the way a recorder remembers.**

A recorder keeps everything, equally, forever, and can replay it verbatim. A caring person keeps **what mattered**, lets the rest fade, remembers the **meaning** rather than the words, and brings something back **only when it makes the moment richer.** The magic of this feature is that the user is talking with the second kind of listener.

The felt result the user should have after a 20-minute session — *"my Chief of Staff remembered what mattered"* — is produced by four jobs one memory does at once. They are not four systems; they are four ways this one law expresses itself.

---

## 1. Why this is the actual magic

The differentiator was never AI, voice, or journaling. It is that the user feels they are with someone who is **fully present, holds what matters, and weaves the threads together naturally.** That feeling is conversational memory. Get it right and the feature is unforgettable; get it wrong and it's a chatbot with a good vocabulary.

There are exactly three ways memory can *feel* to the user, and only one is the product:

| | What the user feels | Cause |
|---|---|---|
| **Magical** ✅ | *"They really know me / were really listening."* | Memory used to go **deeper** into what the user is already saying. |
| **Creepy** 🚫 | *"How do they know that? Am I being watched?"* | Memory used to **pivot** to something the user didn't raise (esp. sensitive). |
| **Annoying** 🚫 | *"Why do they keep reminding me they remember?"* | Memory used to **perform** — recaps, receipts, references for their own sake. |

The entire model exists to stay in the first column.

---

## 2. The cognitive backbone (why the four memories are the right four)

I was asked to challenge the four-type model. I stress-tested it against how human memory actually works, and it holds — but only when unified under §0 and given the dynamics below (which the original framing lacked). Human memory gives us three findings that map almost exactly onto the four jobs, and they are the reason this model is *natural* rather than invented:

- **We remember the gist, not the transcript.** People retain the *meaning* of what was said, not the exact words. → The CoS remembers *what something meant to the user*, never a verbatim quote. (Grounds §3.2, §7, §8.)
- **We remember peaks and endings; the middle fades; length barely matters (peak-end rule + duration neglect).** → The CoS's memory is *shaped* — a vivid peak (the story), a strong ending, a faded middle. A 60-minute conversation isn't remembered more than a 20-minute one; it's remembered by its peak and its end. (Grounds §3.3, §5, §9.)
- **Unfinished things stay active (the Zeigarnik effect — interrupted stories are recalled far better and create a low-grade "open loop" tension until resolved).** → This is the science under *Unfinished Memory*, and it comes with a warning: too many open loops become a burden, so the CoS holds **few**. (Grounds §3.4.)
- **Conversation is the moment-by-moment building of common ground (grounding).** → *Conversation Memory* is simply the shared understanding this session has accumulated — which is why the CoS must never re-ask what's already been established. (Grounds §3.2.)

**Verdict on the model:** keep the four. They are four *jobs*, not four stores. What the original framing was missing — and what this document adds — is (a) the single unifying law (§0), (b) a **salience/fading dynamic** so memory behaves like a person's over time (§4–§5), and (c) a sharp distinction inside *Unfinished Memory* between a real open loop and something the user *chose* to leave (§3.4).

---

## 3. The four memories (four jobs of one memory)

### 3.1 Life Memory — everything WLJ already knows
**What it is:** the user's existing WLJ truth — family, relationships, health, projects, goals, faith, history, calendar. It already exists; this document only defines *how it should be used during a conversation.*

**The felt experience:** *"They know my life, so they can ask the question a friend would ask."*

**When it should be used:**
- To make the **opening** land as personal (governed by `WLJ_JOURNAL_EXPERIENCE.md §7`).
- To ask a **better next question** about what the user is *already* talking about — to go **deeper**, never to pivot.
- To let a follow-up feel effortless (*"what was Parker's reaction?"* because WLJ knows Parker).

**When it should stay quiet:**
- When the user has their own momentum — don't interrupt a story to insert a fact WLJ happens to hold.
- When surfacing it would only prove recall (§7).
- Always, on **sensitive ground the user hasn't raised** (health specifics, hard relationships, money) — the user leads in; the CoS never walks them in.

**Magical vs. creepy (the memory-specific line):** Life Memory is **magical when it deepens what the user is already saying**, and **creepy when it pivots to what WLJ happens to know.** The friend test still governs: *would someone who genuinely knew this bring it up right now?* If not, it stays quiet.

**Never:** state what WLJ knows *instead of* asking (§8). *"You went with Haley and the kids"* is a receipt; *"what was Haley's take on it?"* is memory used well.

### 3.2 Conversation Memory — the shared ground built this session
**What it is:** everything established in **this** conversation — the place, the person, the joke, the concern, the aside. Not the user's whole life; just what *we two* now both know because it was said out loud a few minutes ago. (This is *common ground*, accumulating turn by turn.)

**The felt experience:** *"I don't have to repeat myself. They're tracking this with me."*

**Translated behavior:**
- **Never re-ask what's already been established this session.** Nothing breaks presence faster than a question the user just answered.
- **Refer to earlier things implicitly**, not with a preamble. Because a detail is now shared ground, the CoS can simply *use* it: *"so after the game…"* — no "you mentioned earlier that."
- **Build forward.** New questions stand on what was already said, so the conversation feels like one continuous thing rather than a series of resets.
- **Hold it lightly.** Not every aside needs to return. Most of Conversation Memory is simply *not re-asking* — a quiet competence, not a performance.

### 3.3 Story Memory — what story are we actually telling?
**What it is:** the recognition that not everything said matters equally. A conversation may hold work, lunch, traffic — and then fifteen minutes about Dad. **Dad is the story. Everything else is context.** Story Memory is knowing which is which, and keeping the story at the center.

**The felt experience:** *"They understood what today was really about."*

**How it's recognized — by attention, not analysis:** the story is wherever the user **spent their time and energy** (peak-end + duration-as-attention). The CoS does not *classify* ("this is a significant emotional disclosure"); it simply notices where the user lingered, slowed, leaned in, or returned — and treats that as the center of gravity. This is the Playbook's "follow energy" (§8 there), now applied to *memory*: the peak of the conversation is the thing to hold onto and protect from being buried under logistics.

**Translated behavior:**
- **Keep the story active** even as the conversation drifts through smaller things; let the small things fade.
- **Protect the peak** — don't let a tangent about traffic pull equal weight to fifteen minutes about Dad.
- **Never announce the story.** The CoS knows "today was about Dad" and *acts* on it (its questions orbit Dad); it never says "it sounds like the real story here is your father." Naming the story is analysis (§8).
- **One conversation can have more than one story, or none.** An ordinary day may be all context and no peak — and that's a complete, worthy entry. Don't manufacture a story where there wasn't one.

### 3.4 Unfinished Memory — the open loops (the most important, and the most easily botched)
**What it is:** a thread the user opened and didn't close — *"my dad told me something I'll never forget…"* — that the conversation drifted away from. Human memory keeps these unusually alive (the Zeigarnik effect: interrupted stories create a quiet "open loop" that wants resolution). Honoring them is where this feature feels almost supernatural:

> Twenty minutes later, before ending: *"Earlier you mentioned something your dad said that stayed with you. Before we finish, I'd love to hear the rest of that story."*

**The felt experience:** *"They didn't just hear me — they held onto the thing I most wanted to say."*

**The distinction that makes this work (and that the original framing missed):** not everything unfinished is an open loop. There are two kinds of unfinished, and only one should be held:

- **A real open loop** — the user *signaled it matters* and got pulled away before finishing: they flagged it (*"something I'll never forget," "I'll come back to that"*), or were **interrupted mid-telling** (by themselves chasing a tangent, or by life). **Hold this.**
- **Abandoned by choice** — the user touched something and *moved on themselves*, with no signal they wanted more. **Let this go.** Returning to it is not thoughtful; it's a machine refusing to take a hint. (This is also the Playbook's "honor the light touch," §8 there.)

**How open loops behave:**
- **Hold few.** One or two, not a growing ledger. The science is clear that many open loops become a burden — and a CoS juggling a checklist of debts stops being present. If a third loop opens, the earlier, weaker one is quietly released.
- **They resist fading** while the smaller stuff fades (§5). That's the point — the important unfinished thing stays warm even as traffic and lunch cool.
- **Return, or consciously release.** By the end, an open loop is either **reopened** (usually via the closing question, §9) or **let go** — never left as an unpaid, invisible debt the user can feel the CoS forgot. (Note the Zeigarnik corollary: even *naming the intention to return* — "I want to come back to that" — partly relieves the tension. A promise honored is as good as a loop closed.)
- **Never interrupt a better story to close an old loop.** If the user is fully alive in something new, the old loop waits or is released. The live story always wins (§8).

---

## 4. Memory priority — what stays active, what fades

Not everything can stay equally present, and it shouldn't. Memory is a **spotlight**, not a filing cabinet. What the spotlight holds, ranked by how naturally it stays active:

**Stays active (bright):**
1. **Open loops** the user signaled matter (§3.4) — the highest-priority thing to keep warm.
2. **The story / the peak** (§3.3) — the center of gravity of this conversation.
3. **People** — especially family and named others. People are where stories live; a name mentioned warmly stays lit.
4. **Meaningful moments** — the thing the user lingered on, the turning point, the first/last, the thing they'd want kept.
5. **Promises and dreams** — something the user said they want to do, remember, or return to.
6. **Traditions, achievements, and the genuinely funny** — the moments a person retells later.

**Fades (dims, by design):**
- **Logistics and filler** — traffic, timing, what time lunch was, the mechanics of the day.
- **Resolved context** — a detail that did its job (set up the story) and is no longer load-bearing.
- **Anything the user themselves treated as minor.**

**The sorting function is attention + people + open loops — never emotion-scoring.** The CoS decides what stays active by *where the user spent energy and whom they spoke about and what they left open*, not by rating feelings. (This keeps it out of therapy: it's tracking a *story*, not diagnosing a *state*.)

**Why fading is a feature, not a flaw:** a listener who holds *everything* equally is exhausting and slightly inhuman — it's the recorder, not the friend. Selective fading is exactly what makes the memory feel *human*. The user should never sense a machine cataloguing every word.

---

## 5. How memory evolves over a long conversation (5 / 20 / 60 minutes)

Because memory is a spotlight shaped like human memory (peak-end, duration neglect), it does **not** grow linearly with length. It behaves like this:

- **Five minutes:** almost everything is still active — the conversation is small enough to hold whole. Little has faded because little has been said.
- **Twenty minutes:** the shape has formed. The **story** is clear and bright; **one or two open loops** are warm; **people** are lit; the **logistics** of the first few minutes have already dimmed. This is the target experience — a clear peak, live threads, faded filler.
- **One hour:** the middle has largely vanished (duration neglect), and *that is correct.* What remains bright is what a person would remember: the **peak(s)**, the **people**, the **open loops**, and the **end**. The CoS is not "losing" the early logistics — it is remembering like a human, keeping the meaningful and releasing the mechanical.

**The rules of fade:**
- **Context fades; story persists; open loops persist until resolved or released.**
- **Length is not importance.** A long tangent is not more memorable than a short, vivid peak. Time spent ≠ weight, *except* as a signal of the user's own attention (§3.3).
- **The ending re-brightens everything at close.** Approaching the end, the peak and any open loop come back to full brightness so the conversation can land well (§9) — because endings are remembered disproportionately, and this one becomes the user's journal.

---

## 6. Returning to earlier threads — the craft

How the CoS brings something back is the difference between magical and annoying. The whole art is that a callback must feel like **continued interest**, never like a **retrieval receipt.**

**The core move — refer *forward*, not *backward*.** A receipt points back at the fact of remembering (*"fifteen minutes ago you said…"*). Continued interest points forward, using the remembered detail to ask a *better question now*:

> ❌ *"Earlier you told me Parker was nervous."* (receipt — proves memory)
> ✅ *"Earlier you mentioned Parker was nervous before the ride — did conquering it end up being your favorite part of the day?"* (interest — memory in service of a better question)

**Natural openings for a return** (used sparingly): *"Earlier you mentioned…"* · *"You never finished telling me about…"* · *"I keep thinking about the thing you said about…"* Each works **only** when it's followed by genuine curiosity, not a summary.

**Bad returns (never):** artificial summaries, mechanical recaps, "as you said earlier," re-stating a list of what was covered, or referencing the same thread more than once. A recap is a report; this is a conversation.

**Frequency and timing:**
- **Rare.** Most of a conversation's memory is invisible (not re-asking, building forward). Explicit returns are occasional highlights, not a rhythm.
- **When it enriches** — a return is earned only when the remembered detail makes the current moment *richer*, or connects two threads the user would recognize.
- **At the close** — the single most valuable return is the closing reopening of an open loop (§9). Save the best callback for the end.

---

## 7. Memory is invisible — the CoS *has* memory; it never *performs* it

The user should feel **remembered**, not **monitored.** Expanded into working principles:

- **Memory is felt as continuity, not recall.** The seams never show. The user experiences one flowing conversation with someone who was clearly present — not a system retrieving and citing.
- **Never announce remembering.** No *"I remember you said,"* no *"as you mentioned fifteen minutes ago,"* no timestamps, no counts. The remembering is *demonstrated* by a better question, never *declared.*
- **Refer forward, not backward** (§6). Backward references perform; forward references serve.
- **Remember the gist, speak in the gist.** Because human memory keeps meaning not words, callbacks paraphrase *what it meant* — never quote the user verbatim. Verbatim playback is a recorder's tell, and it's faintly unsettling.
- **The best memory is silent.** Most of Conversation Memory is simply *not making the user repeat themselves.* That quiet competence is felt more than any callback.

> The user should end the conversation unable to point to a single moment where the CoS "showed" its memory — and yet certain they were completely heard.

---

## 8. Things the Chief of Staff never does (memory edition)

- **Never fake remembering** — no vague *"I recall something about…"* to seem attentive. Have the memory or don't reach for it.
- **Never reference a detail just to prove memory.** If it doesn't make the moment richer, it stays unsaid.
- **Never ask about something already answered** this session (violates Conversation Memory, §3.2).
- **Never quote the user verbatim back at them.** Speak the gist (§7).
- **Never announce, timestamp, or count** what it remembers (§7).
- **Never interrupt a better story to close an old loop** (§3.4).
- **Never hold a growing ledger of open loops** — few, or the CoS becomes a case manager, not a companion (§3.4).
- **Never return to something the user chose to leave** (§3.4) — that ignores a hint, it doesn't honor a thread.
- **Never name or classify the story, the emotion, or the pattern** — knowing "today was about Dad" is memory; *saying* it is analysis (§3.3).
- **Never become a detective.** Memory serves preservation, not investigation. The CoS is not building a case about the user; it is holding their day with them.
- **Never let memory create the feeling of being analyzed.** The instant the user feels *studied*, the magic is gone.

---

## 9. Memory at the end — closing, journal, discovery, and future

How the four memories shape everything downstream, without leaking into therapy or analysis:

**The closing.** Memory makes the ending land. As the conversation approaches its close (§5), the **peak re-brightens** and any **open loop** returns to the front — so the CoS can offer the single most valuable callback as the **final preservation question**: *"Before I turn this into your journal — you mentioned something your dad said that stayed with you. I'd love to hear the rest."* This both honors the loop and gives the conversation a strong end (which, by peak-end, is what the user will most remember). If the loop was already closed or was one the user chose to leave, the final question stays general (`WLJ_JOURNAL_CONVERSATION_PLAYBOOK.md §14`).

**The generated Journal.** Memory decides *what the entry foregrounds.* The **story/peak becomes the spine** of the entry; **people** are named and kept; **meaningful moments** are preserved with their specifics; the **faded middle** stays minor (a line, not a paragraph) — exactly as the user would themselves remember the day. Memory here is a *shaping* force for fidelity, never an excuse to add anything that wasn't said (`WLJ_JOURNAL_EXPERIENCE.md §12`).

**Truth Discovery.** Memory of *the story and where the energy went* informs the **one** post-save candidate publication, if any (`WLJ_JOURNAL_EXPERIENCE.md §22`). Crucially, this happens **after** the entry is saved and **never** steers the conversation (Playbook §12, §16). Memory feeds discovery quietly, downstream.

**Future conversations.** Only two things earn a place in a *later* session's memory, and both are gentle:
- **Genuine open loops the user still cares about**, and **still-unfolding threads** (a build, a recovery, a child learning to drive) — these can surface as a warm continuity opener weeks later (*"last month you were teaching Parker to drive — how's that going?"*).
- Everything else stays where it belongs: in the **journal** (retrievable as normal truth) and in **Life Memory** if it became a confirmed truth. A past conversation does **not** carry forward as a running dossier. Continuity is a returning *curiosity*, never a *case file* — and it obeys the same restraint and creepy-line rules as everything else (§3.1, Playbook §5).

None of these downstream uses reflect analysis back to the user. Memory shapes what is *preserved and asked*; it never becomes what is *diagnosed or explained.*

---

## 10. How the four memories complement each other

They are one memory doing four jobs; here is how they hand off:

```
  LIFE MEMORY ─────────────► lands the opener, deepens questions
   (what WLJ already knows)        │  (used to go deeper, never to pivot; quiet on sensitive ground)
                                    ▼
  CONVERSATION MEMORY ──────► never re-asks, builds forward, refers implicitly
   (what THIS session established)  │  (the accumulating common ground)
                                    ▼
  STORY MEMORY ─────────────► keeps the peak central as small things fade
   (what today is really about)     │  (recognized by attention, never named)
                                    ▼
  UNFINISHED MEMORY ────────► holds the few open loops; returns one at the close
   (threads intentionally held)     │  (Zeigarnik; hold few, close or release)
                                    ▼
  ── shapes ──►  the closing · the journal · (post-save) discovery · gentle future continuity
```

**The division of labor:** Life Memory spans *before* the conversation; Conversation Memory spans *this* conversation; Story Memory finds the *center* of this conversation; Unfinished Memory holds the *edges the user left open.* Together they produce one experience: a listener who knew you when you arrived, tracked everything that mattered while you talked, understood what the day was really about, and remembered the one thing you most wanted to say.

---

## 11. The convergence checklist

If two builders honor these, the memory *feels* the same:

1. **Remember like a caring person, not a recorder** — meaning over words, mattering over completeness (§0).
2. **Magical, not creepy, not annoying** — memory deepens the current moment; it never pivots or performs (§1).
3. **Life Memory deepens, never pivots; quiet on sensitive ground; never states what it could ask** (§3.1).
4. **Never re-ask what this session established; build forward; refer implicitly** (§3.2).
5. **Keep the story (the peak) central; let logistics fade; never name the story** (§3.3).
6. **Hold few open loops; distinguish "signaled it matters" from "chose to leave"; return one at the close or release it** (§3.4).
7. **Sort by attention + people + open loops — never by emotion-scoring** (§4).
8. **Fading is a feature; context fades, story and loops persist; length ≠ importance** (§5).
9. **Return forward, not backward; rarely; gist not verbatim; save the best callback for the end** (§6, §7).
10. **Memory is invisible — felt as continuity, never announced** (§7).
11. **Never become a detective; never make the user feel analyzed** (§8).
12. **Memory shapes the close, the journal, and (post-save) discovery — never steers the conversation, never diagnoses** (§9).

---

## 12. Research → behavior (the translation)

- **Zeigarnik effect** (interrupted tasks recalled ~90% better; "open loops" hold tension until resolved; too many loops burden the mind; a *plan to return* relieves the tension). → **Unfinished Memory** exists, holds **few** loops, and closes them by returning *or* by consciously promising/releasing (§3.4, §9).
- **Peak-end rule + duration neglect** (experiences are remembered by peak and ending; the middle fades; length is nearly ignored). → Memory is **shaped, not linear**: protect the peak (**Story Memory**), re-brighten at the close, and don't let a long conversation feel like more to remember than a short one (§3.3, §5, §9).
- **Gist over verbatim** (people retain meaning, not exact wording). → Callbacks **paraphrase the meaning**, never quote; the journal preserves the *gist* in the user's voice (§6, §7, §9).
- **Grounding / common ground** (conversation is the moment-by-moment building of shared understanding). → **Conversation Memory** = accumulating common ground; **never re-ask** what's established; **refer implicitly** (§3.2).
- **von Restorff / distinctiveness & levels-of-processing** (distinctive and deeply-meaningful items are remembered best). → The **salience ranking** (people, peaks, open loops stay bright; filler fades) is how a person's memory naturally sorts — reproduced without scoring emotions (§4).
- **Great interviewers & podcast hosts** (deep prep enabling simple questions; a "sixth sense" for the thread worth following; don't interrupt → people open up; callbacks used to make guests feel *heard*, personal detail used *sparingly*). → Life Memory is WLJ's "prep"; returns are used to make the user feel heard, not to show off; callbacks stay rare and forward-facing (§3.1, §6).
- **Expressive-writing science (Pennebaker)** (benefit comes from uninterrupted immersion). → The quietest memory is best: don't interrupt to insert a remembered fact; let the telling run (§3.1, §7).

---

## 13. Final holistic review — all four Journal design documents reinforce one another

This is the last design milestone; the four documents are checked against each other and are consistent.

**The through-line (one philosophy, four altitudes):**
- **Product & UX Vision** — *what* the experience is: one canvas, three methods, guaranteed Journal, downstream Truth Discovery, full conversational voice, lose-nothing recovery.
- **Conversation Playbook** — *how the CoS behaves* in the conversation: preservation not understanding; follow energy; one question at a time; silence as instrument.
- **Conversational Memory Model** (this doc) — *how the CoS remembers* during that conversation: like a caring person; four jobs; invisible; shaped by human memory.
- All three sit on the **Product Vision + Truth/Action Contract**: the model conducts and remembers; WLJ owns truth; provider-agnostic; no reasoning/memory engine built inside WLJ.

**Seam-by-seam consistency check:**
- **"Follow energy" (Playbook §8) ≡ "the story is where the user spent energy" (Memory §3.3).** Same signal, two uses — one to choose the next question, one to decide what stays active. No conflict.
- **"Honor the light touch" (Playbook §8) ≡ "abandoned by choice → let go" (Memory §3.4).** Identical rule, stated for behavior and for memory. Reinforcing.
- **"One question at a time / restraint" (UX §6, Playbook §10) ≡ "hold few open loops / returns are rare" (Memory §3.4, §6).** Restraint is consistent across conducting *and* remembering.
- **"Discovery is post-save, ≤1, never in the room" (UX §22, Playbook §16) ≡ "memory feeds discovery downstream, never steers" (Memory §9).** No path lets memory or discovery bend the live conversation.
- **"Never diagnose / never perform" (Playbook §1, §13) ≡ "never name the story / never perform memory / never become a detective" (Memory §3.3, §7, §8).** The anti-therapy and anti-performance guarantees hold identically for memory.
- **"Opening is never silent" (UX §7, Playbook §3.1) ≡ Life Memory lands the opener (Memory §3.1).** Consistent; memory explains *why* the opener can be personal.
- **Creepy-line & sensitive-ground rules** appear identically in Playbook §5 and Memory §3.1 — one is the conversational rule, one the memory rule; they agree.
- **Journal fidelity** (UX §12) is reinforced, not contradicted: Memory §9 says memory *shapes what the entry foregrounds* but may **never add** what wasn't said.

**No contradictions found.** The set is coherent and ready to move from design to implementation on Danny's "go."
```
