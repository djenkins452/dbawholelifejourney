# WLJ Legacy Domain — User Experience Architecture

> **Status:** Canonical product-design reference (baseline v1). Developers build screens from this; this document defines how every surface should *behave and feel* before implementation begins.
> **Companion to:** `WLJ_LEGACY_DOMAIN_ARCHITECTURE.md` (the frozen architecture baseline — Canonical Truth, the Attestation → Assertion → Projection model, the knowledge graph, Significance, Loss-Risk, Succession). This document does **not** redesign the architecture; it designs the experience of living inside it.
> **Established:** 2026-07-01
> **Scope:** No assistant integration. Legacy must stand entirely on its own. Where the future assistant (internally "Beth") would plug in, this document marks the *seam* and stops (§16).

---

## 0. How to read this document

The architecture baseline answered *what is true*. This document answers *what it feels like*. They are two halves of one thing: the baseline is a provenance-first graph of attestations, assertions, conflict sets, promotion gates, significance, and loss-risk — and **the single hardest product problem in all of Legacy is that none of that may ever be visible to the person using it.**

A grieving daughter recording her mother's voice must not encounter the word "attestation." A grandfather telling a fishing story must not see a "confidence envelope." The machinery is real, load-bearing, and must run silently underneath an experience that feels like **sitting at the family table, telling stories.**

So this document is organized as a translation layer. For every architectural concept, there is a human-facing feeling it must become:

| Architecture (baseline) | What the user experiences |
|---|---|
| Attestation | "I remembered something" |
| Provenance | "who told this, and when" |
| Confidence / corroboration | "how sure we are" — shown gently, rarely |
| Conflict set | "your sister remembers it differently — both are kept" |
| Assertion graph | "one thing always leads to the next" |
| Promotion gate | a warm "yes, that's right" |
| Significance | how prominent something feels |
| Loss-Risk | a gentle nudge about *people*, never a number |
| Projection / output | "make something to share" |
| Succession | "this is yours, forever, and theirs after you" |

If a screen ever makes the user feel the left column, that screen has failed.

---

## 1. The central design problem, and the reframe

### 1.1 The problem

Preserving a life is *enormous* — thousands of people, decades of events, tens of thousands of photos. Every instinct of software design (dashboards, forms, folders, tags, completion bars) turns that enormity into **administration**, and administration is the death of preservation. Nobody wants to spend their evenings doing data entry about their own life.

### 1.2 The reframe

**The user only ever does two things: they *remember*, and they *wander*.**

- **Remember** = give the system a memory, in whatever half-formed shape it arrives — a spoken ramble, a typed paragraph, a photo with three words, a saying.
- **Wander** = move through the life that has accumulated, following association wherever it leads.

Everything else — extraction, connection, deduplication, conflict-handling, significance, organization — is **the system's job, done invisibly, and surfaced only as optional, human-framed moments the user can accept, ignore, or return to later.**

This is the whole design. Two verbs for the user; everything else hidden. The rest of this document is the disciplined application of that single idea.

---

## 2. The UX Laws (the spine every screen obeys)

These are to the experience what Laws 0–5 are to the architecture. When a design decision is unclear, it is resolved against these, in order.

1. **Never feel like software; never feel like a database.** No jargon, no schema-shaped screens, no "records." If a surface looks like an admin panel, redesign it.
2. **Zero friction from impulse to captured memory.** The path from "I want to say this" to "it's safely kept" must be one tap and no required fields. Memory is fleeting; friction loses it forever.
3. **Capture is never gated.** No mandatory titles, no required tagging, no forced confirmation step. A memory is complete the instant it's spoken, even if nothing is connected to it yet.
4. **The system organizes; the user only remembers and wanders.** Never ask the user to file, sort, fold, or maintain. Organization is a background service, not a chore.
5. **Voice is first-class.** Say it, don't type it. Talking is how humans tell stories, and it captures the irreplaceable thing — the voice itself.
6. **Nothing is ever lost; nothing is ever forced into your face.** Infinite storage, curated attention. The mundane recedes but is never deleted; the meaningful rises.
7. **Revisiting is deepening, not correcting.** Returning to a memory adds a layer; it never overwrites (append-only, felt as "I remember more now").
8. **Prioritize the irreplaceable and the fragile.** Living elders, voices, and the small identity-defining details come first, because they are the things that vanish and can never be recovered.
9. **Emotional safety above all.** Private by default, forgiving (undo everything), unhurried (no deadlines), and **never gamified**. A life is not a score.
10. **It is one living web, seen through lenses — never separate databases.** People, places, moments, and media are ways *into* the same life, not silos.
11. **Your life is portable and yours forever.** The promise that it can never be locked away or lost is visible and central, not buried in settings.

---

## 3. Mental model & navigation

### 3.1 Challenging the seven-noun navigation

The brief proposes top-level nav of Stories / People / Places / Media / Timeline / Collections / Dashboard. **This is the object model leaking into the interface, and it should be rejected.** Seven database tables shown as seven tabs is exactly the "feels like software" failure (Law 1). It also fights the architecture's own thesis — the baseline insists a life is *one graph*, and that Timeline is a *lens*, not a store (baseline §3.5, §4).

### 3.2 The model: one place, two verbs, a few lenses

Legacy is **one space — your life** — with a very small, verb-forward surface:

- **Remember** — the front door to capture. Always one tap away, from everywhere, on every screen. This is the most important control in the entire product.
- **Wander** — enter the web of your life and follow it (the browse/explore experience, §9).
- **Home** — the warm return surface (§4), where you land.

And a small set of **lenses** — not tabs, but *ways of entering the same web*, offered inside Wander and Home: **People, Places, Moments, Photos, Threads.** People earns the most prominence because humans index memory by person first ("tell me about Grandpa"). Time is present as a lens but never primary, because memory is associative, not chronological (baseline §4.1).

The mental model we want the user to hold: *"This is my whole life, and I can walk into it from any door."* Not *"This is a set of folders I maintain."*

---

## 4. Home — the Hearth (not a dashboard)

### 4.1 Challenging the dashboard and the preservation score

The brief asks whether there should be a preservation score and a stats dashboard. **Both should be rejected in their proposed form**, for reasons that go to the heart of the mission:

- **A preservation score is actively harmful.** A life can never be "100% preserved," so the number is either permanently low (discouraging, implying failure at an impossible task) or falsely near-complete (a lie, and a violation of the Regret Test's spirit — baseline §12). Worse, it *gamifies grief*. Turning "have you preserved your dead mother yet?" into a progress bar is exactly the emotional failure Law 9 forbids.
- **A stats dashboard** (Total Entries, Draft Entries, Contributors, Media Count) is an admin console. It makes the user the *operator of a database* rather than the *keeper of a life* (Law 1).

But the legitimate need underneath both — *"help me know where to spend my limited time"* — is real and important (it is the loss-risk triage of baseline §7/§12). We serve that need far better without a number.

### 4.2 The Hearth

Home is a **warm, living surface that shows you your life and quietly invites you deeper** — think *walking into a room full of framed photographs*, not *opening a control panel*. It holds, in descending prominence:

- **A resurfaced memory** — "On this day, twelve years ago…" / "Remember this?" A photo, a story, a saying brought back up. This is the emotional hook and the engine of rediscovery (§14).
- **A gentle, specific invitation** — the loss-risk triage, humanized: *"You've mentioned your grandfather often, but never told a story just about him."* / *"Your mom is your oldest storyteller."* One at a time, warm, dismissible, never a checklist. (This is where the fragile-source priority lives — as an invitation about *people*, never a gauge.)
- **An open thread** — something you started and can continue ("You were telling the story of the move…").
- **The ever-present Remember button.**

### 4.3 On progress and milestones

We replace *measurement* with *celebration and richness*. No bars, no percentages. Occasionally, soft, life-shaped acknowledgments are welcome — *"You've now preserved a memory from every decade of your life"* / *"A hundred memories about your children."* These are milestones as *warmth*, never as completion pressure. The felt sense of progress comes from the visibly *growing web* when you wander, not from a metric.

---

## 5. Capture — the heart of Legacy

Everything else can be merely good; capture must be extraordinary. This is where a life is either preserved or lost.

### 5.1 One button, one open space, no setup

**Remember** drops you instantly into a calm, nearly empty space where you can *immediately* talk or type — no title, no category, no fields, no "new entry" form (Law 2, Law 3). Autosave from the first word or first second of speech. You can stop mid-sentence, get up, and it is already safe. The blank space is warm and unintimidating, closer to a journal page or a voice-memo screen than a document editor.

### 5.2 Voice-first, always

Talking is how stories are actually told, and it captures the single most irreplaceable thing — **the voice** (the #1 item in the Regret Test, baseline §12). So voice is not a feature tucked in a corner; it is the *primary* capture mode, offered first, especially important for older users for whom typing is a barrier and for whom the sound of their voice is a gift to descendants. Speech becomes text automatically for connection and search, **but the original audio is always kept** as evidence (baseline §2.3) — the grandchild should be able to *hear* the story, not just read it.

### 5.3 Doorways, not forms

The brief's entry types — Share a memory, Tell a story, Meet someone important, Describe a place, Talk about an event, Preserve an object, Family tradition, Lesson learned, Favorite saying, Brain dump — **should exist, but strictly as optional doorways that defeat the blank page, never as templates that constrain what follows.** Picking "Meet someone important" simply offers a gentle first prompt ("Who comes to mind?"); it never forces a structured form. The default door is always the most open one: *just start talking.* This honors the architecture's rule that users are never forced into a rigid template (baseline §5.1).

### 5.4 Riding the associative wave

The deepest discovery in the baseline is that **one memory unlocks five more** (§4.1). Capture must exploit this while the wave is live. When you finish a memory, the gentlest possible, *entirely optional* invitation to continue: *"…and that reminds you of?"* — one soft prompt, never a nag, easy to dismiss. This is the single highest-leverage moment in the product, because stories #2–#5 are only capturable in the sixty seconds after story #1, and only if the friction is near zero. (When the assistant arrives, this seam becomes true elicitation — §16 — but even without it, a plain "keep going?" preserves far more than a save-and-exit flow.)

### 5.5 Capture from anywhere, anytime

A life is remembered in fragments at odd moments. Remember must be reachable in one tap from every surface, and must accept the smallest possible unit — a single sentence, a single saying, one photo with three words. Small fragments are first-class (baseline §11), because the smell of eucalyptus and a childhood nickname preserve identity as powerfully as any full story, and they only get captured if capturing them is trivial.

---

## 6. The Editor — a journal, not a word processor

### 6.1 What it should *not* become

The brief's list (rich text, version history, side panels) drifts toward a book-writing tool. **Legacy is not for writing books** (guiding philosophy), so the editor must resist becoming Google Docs. No word count, no formatting toolbar demanding attention, no "publish" button implying the memory isn't real until polished.

### 6.2 What it should feel like

**Calm, private, unhurried, forgiving.** A single generous writing/speaking area. Minimal formatting (paragraphs and emphasis — the *story* matters, not typography). Media dropped *inline*, where it belongs in the telling (a photo in the middle of the memory it illustrates). Autosave always; undo everything; **nothing is ever lost** (Law 6). Version history exists as an invisible safety net (append-only per the architecture), not as a feature the user thinks about — surfaced only if they ask "what did I say before?"

The emotional target: the editor should feel like the moment *after* someone says "tell me about it" — safe, open, no pressure, all the time in the world.

---

## 7. Recognition & connection (reframing "smart analysis")

This is the most dangerous screen in the product, because reviewing extracted entities is *precisely* database data-entry, and doing it wrong reintroduces everything Law 1 forbids.

### 7.1 The design laws for this feature

- **It never blocks capture.** You can remember a hundred things and confirm nothing. Connection is *enrichment available anytime*, never a required step (Law 3). The product is fully valuable to a user who ignores this feature forever — their memories are still preserved (as attestations), just less connected.
- **It never interrupts the emotional flow.** Analysis runs silently in the background. It does **not** ambush the user with "please tag six people" the moment they finish pouring out a hard memory. Right after a painful story is not the time for a test.
- **It is framed as recognition, not validation.** Suggestions appear as warm, conversational noticing — *"It sounds like Uncle Joe and Soddy Daisy are part of this — want me to connect them?"* — not a checklist of extracted rows. The architecture's **promotion gate** (baseline §2.7) becomes a single friendly *"Yes, that's right"* / *"Not quite"* / *"Let me fix that."*

### 7.2 The connecting mode

Connection is best done in a distinct, *pleasant* mood — a light "tidying" mode the user enters when they *want* to, akin to sorting a shoebox of photos on a rainy afternoon. Batched, gentle, satisfying, stoppable at any point. The system proposes; the human confirms; nothing becomes canonical without that human "yes" (baseline §2.7). New people, places, sayings, and traditions quietly become nodes the user can later wander to — but the *feeling* is "I'm connecting my memories," never "I'm populating a schema."

### 7.3 Duplicates and conflicts, humanized

When the system suspects two "Joe"s are one person, it asks *"Is this the same Joe?"* — never "merge these records." When two accounts disagree, it never presents a merge-conflict dialog; it says *"You remembered this as 1954 before — keep both?"* and preserves both (baseline §2.6 — conflict is data, never resolved away). The word "conflict" never appears.

---

## 8. Keeping & revisiting (reframing the draft workflow)

### 8.1 Challenging the vocabulary

"Draft → Approved → Archived" is bureaucratic and implies a memory isn't *real* until approved. **Reject "approved."** The user-facing states should be human:

- **Just for me** — private, unfinished, a note-to-self. (Draft, internally.)
- **Kept** — this is part of my story. (Canonical, internally — but the felt meaning is "this is real and safe.")
- **Shared** — visible to chosen family.
- **Set aside** — tucked away, never deleted. (Archived.)

Crucially, **a memory is preserved the instant it's captured** — "keeping" is not a gate to preservation, it's a signal of intent to *finish and connect*. A three-sentence memory that's never "finished" is still fully preserved. This matches the architecture (attestations exist from capture; assertions compose from them) while removing the anxiety that unfinished = unpreserved.

### 8.2 Editing years later = deepening, not correcting

The architecture is append-only: attestations are never overwritten (baseline §2.2). The experience makes this a *gift*, not a limitation. Returning to an old memory feels like **adding a layer** — *"I remember more now"* or *"Actually, it was the summer before"* — and the earlier telling is quietly preserved beneath, never destroyed. The user thinks *"I added to this,"* not *"I edited version 3."* If they ever want it, "how I told this before" is available, but it is never in the way. This also means a person's *changing understanding of their own life over decades* is itself preserved — which is precious.

---

## 9. Wandering — how you explore a life

This is, alongside capture, the most important experience, and the brief is right to flag it.

### 9.1 Challenging the graph explorer

The brief asks whether a graph explorer / relationship map would be better than folders and lists. **A raw node-graph visualization should be rejected as the primary experience.** It demos beautifully and collapses in reality: 5,000 people and 10,000 stories render as an unreadable hairball, and "here is a diagram of your life" is cold and abstract — the opposite of the family table. The graph is the *engine* (baseline §4); it must not be the *interface*.

### 9.2 The model: association as contextual rails

Instead, associativity is expressed as **"this leads to that" everywhere you look.** When you're with Grandpa, you naturally see — ranked by connection strength (the graph's evocation weight, baseline §4.2) and significance — the **people** around him, the **places** he lived, the **stories** he's in, the **photos** of him, the **sayings** that were his. Tap any of them and you're now *there*, with *its* surroundings. You wander person → place → moment → person exactly as memory itself moves. No diagram; just an endless, gentle "…and that reminds you of…" made navigable.

### 9.3 The lenses (doors into the web)

- **People** — a wall of faces; the primary index of a life. Each person is a small living portrait: who they were, their sayings, the stories, the photos, their relationships.
- **Places** — a map and/or place-cards; spatial memory is powerful, and a childhood home is a doorway to a decade.
- **Moments** — a *soft* timeline lens (available, never the default), useful for "what was happening around then" and for outputs, but never the organizing spine.
- **Photos** — images as entry points; a single photograph unlocks a memory better than any menu.
- **Threads** — meaningful groupings, either user-made ("the lake house years") or gently suggested by the system. This absorbs the brief's "Collections."

### 9.4 Resurfacing is part of wandering

The system continuously and gently brings the forgotten back up — *"On this day,"* *"You haven't visited these memories of your father in a while,"* *"Three photos we've never connected to a story."* At small scale this is delightful; at large scale (§14) it becomes the *primary* way a life stays alive rather than buried.

---

## 10. Media — doorways, not files

### 10.1 The reframe

A photo is not a file to be managed; it is **a doorway to a memory** (baseline §2.3 — media are evidence carriers, and a photo with no attested meaning is unpreserved). So Legacy must never feel like photo-management software.

- **Uploading invites remembering.** Adding a photo gently asks *"Who's in this? What was happening?"* — optional, never nagging. The point of a photo is the story it unlocks.
- **The system organizes media; the user never sorts folders** (Law 4). A photo automatically *lives everywhere it's connected* — with the people in it, at the place, in the moment, inside the relevant thread — because the graph places it. There is no "which folder does this go in?" because there are no folders.
- **Media relate to stories, people, and places by connection, not by filing.** One photo can belong to many memories at once; that's the graph working invisibly.

### 10.2 The box-of-100,000-photos problem

Bulk import of a lifetime of photos is a real, brutal scenario, and per-photo tagging is impossible at that scale. The design answer is a **gentle, batched "help me understand these"** experience — the system clusters by time/face/place and asks a few high-value questions ("Is this your wedding?" "Is this the lake house?") that illuminate hundreds of photos at once — always optional, always resumable, never a 100,000-item to-do list. Undigitized and at-risk media (the shoebox, the decaying VHS) are surfaced first, because they are the most fragile (Law 8).

### 10.3 Recording with, and preserving, voices and video

Because voice and video are the most irreplaceable evidence (Regret Test), media capture includes an easy, dignified **record-together** experience for sitting with a living elder (see §11.3). The felt promise: *your grandchildren will hear your actual laugh.*

---

## 11. Contributors — a gift, not administration

A life is co-authored (baseline §14). The experience must make family contribution feel like *being asked to help remember*, not like being granted database permissions.

### 11.1 Inviting feels like asking for help

Inviting your daughter is framed as *"Ask Sarah to add her memories,"* not *"Manage collaborators."* She receives a warm, personal invitation, taps a link, and can **immediately just talk or type a memory** with the least possible account friction. The security underneath — secure expiring links, bot protection, verification (baseline §14) — is real but invisible to the good-faith family member.

### 11.2 Contributions arrive as gifts

A contribution lands to the owner framed warmly — *"Sarah added a memory about the lake house"* — as something to receive and cherish, then optionally review. It enters as a draft attestation with **permanent, automatic attribution** (baseline §2.4, §14 — never lose attribution), and the contributor's authorship is preserved forever, even after the owner polishes wording. Permission levels stay human and few: *can see* / *can add* / *can help manage*.

### 11.3 Record-together (the fragile-source experience)

The highest-value contributor flow, and the one that most directly answers the Regret Test: **sitting down with a living elder and recording their memories while you still can.** A calm "record together" mode — you ask, they talk, the audio/video and the story are captured and attributed to *them*. This is the loss-risk triage made tangible and human, and it works fully without any assistant (the family member drives the questions). The product should actively, gently encourage this while the oldest voices are still here.

### 11.4 Posthumous contribution

The architecture supports adding memories *about* someone after they're gone (baseline §14). The experience frames this with care — a family continuing to remember a parent together — with posthumous accounts clearly (but gently) marked as remembered-by-others, never laundered into the departed's own voice.

---

## 12. Search — reaching for a memory

Without the assistant, search must still feel like *reaching for a memory*, not querying a database.

### 12.1 One box, everything

A single search accepts a name, a place, a half-remembered phrase, a year, an object, an emotion — and returns results grouped by kind (people, places, moments, photos, sayings). Faceted filters exist as a fallback for the deliberate searcher, but the primary experience is one warm box.

### 12.2 Searching the way people actually recall

Humans recall by *fragment*: "that thing Dad always said about rain," "the summer we had the blue car." So search must be excellent at **sayings, quotes, and fragments** (the Utterance and Fragment nodes, baseline §3.1, §11), not just proper nouns. Being able to type a half-remembered phrase and *find the exact saying in your father's recorded voice* is one of the most emotionally powerful moments the product can deliver.

### 12.3 The seam

Natural-language question-answering ("What was my grandfather like?") is deferred to the assistant (§16). Deterministic search must be genuinely great on its own so the product never *depends* on that future — but the seam is left open.

---

## 13. Outputs — born from where you are

Outputs are **projections, never canonical, always regenerable** (baseline §8). The experience must reflect all three.

### 13.1 Generation is contextual, not a separate tool

You don't go to an "Export" module. You make things **from wherever you're standing**: looking at Grandpa → *"Make a book about him";* inside the lake-house thread → *"Make a photo album";* viewing your whole life → *"Make my memoir."* Outputs are born from a selection or a lens, because that's how intention actually forms.

### 13.2 "For whom" is a first-class choice

Because audience is a projection parameter (baseline §8.4), the flow always asks *who it's for* — a children's book for a five-year-old grandchild reads utterly differently from a family history for adults, from the *same* underlying life. One life, many tellings.

### 13.3 Disposable and honest

The experience makes clear that **any output can be regenerated, differently, forever** — so no output feels precious, final, or risky to make. Outputs honor uncertainty and conflict gently (a contested memory is never rendered as settled fact — baseline §8.2), but in warm human language, never with "confidence: 0.4" showing through. The memoir is a *telling* of the life, not the life; the life stays in the web.

### 13.4 The most important output is the life itself

A subtle but critical stance: the primary artifact of Legacy is **not** the memoir. A book flattens a web into a line. The primary preserved thing is the **wanderable, voice-carrying web** that a grandchild can walk through and *meet* the person. Outputs are wonderful gifts derived from it — but the experience should never imply that "finishing the book" is the goal. The goal is the living record.

---

## 14. Living with Legacy for decades

Assume twenty years: 10,000 stories, 100,000 photos, 5,000 people. The failure mode is feeling **buried**. The design answers:

- **You never face the pile.** You always enter through a small, warm, curated surface — a resurfaced memory, a person, a recent thread (§4). "Here are your 10,000 items" is a screen that must never exist.
- **Rediscovery becomes the primary joy.** At scale, resurfacing (§9.4) turns the vast accumulation into a *well of delight* — the system keeps handing you back the right memory at the right moment. Depth becomes a feature, not a weight.
- **Significance curates attention.** The meaningful rises in prominence; the mundane recedes but is never deleted (Law 6, baseline §7). Scale does not flatten the important, because the graph weights it.
- **The user ages too.** Over twenty years the keeper themselves grows older; the experience must stay usable for an eighty-year-old — large type, voice-first, radical simplicity — and must never require re-learning. The simplest possible product also ages the best.
- **Nothing is a maintenance burden.** There is no upkeep, no re-tagging, no "clean up your library" — the system tends the record; the human just keeps remembering and wandering.

---

## 15. The emotional architecture (answering the final questions)

The brief poses three questions and asks me to critique the design against them. I take them as the true acceptance test.

### 15.1 Opening Legacy after twenty years — what should they feel?

**Like walking into a home full of their life.** Warmth, recognition, a little awe at how much is here, and above all *safety* — "this is all still here, and it's mine." Not the flat efficiency of opening a database.

*Self-critique it forced:* a stats dashboard and a preservation score make you feel like an *operator*, not a *keeper* — this is why §4 rejects both and replaces Home with the Hearth. If opening the app after twenty years should feel like coming home, the home screen cannot be an admin panel.

### 15.2 Grandchildren using it after you're gone — what should they experience?

**Meeting you.** Hearing your actual voice and laugh, encountering your sayings, understanding *why* you were who you were, and coming to *know* a person they never met. Not "browsing an archive."

*Self-critique it forced:* if the goal is *meeting* the person, then (a) the memoir is the wrong primary artifact — a book can't be met, so §13.4 demotes outputs beneath the living, wanderable, voice-carrying web; and (b) **voice and the small identity-fragments are non-negotiable** — which is why §5.2 makes voice the primary capture mode and §11.3 pushes recording living elders *now*. A grandchild who can only read tidy paragraphs has not met their grandmother; one who can hear her laugh and her sayings has.

### 15.3 If Legacy disappeared tomorrow — what would users miss most?

**The voices and the small things** — the irreplaceable testimony of people now gone, the laugh, the saying, the *why*. This is the Regret Test (baseline §12), and it reshapes priorities twice over:

*Self-critique it forced:* (a) The product must relentlessly prioritize capturing the *irreplaceable and fragile first* — living elders, voices, the identity-fragments — which is Law 8, the Hearth's people-invitations (§4.2), and record-together (§11.3). Any design that treats capture as "sit and type your memoir someday" fails this test. (b) The fear behind "if it disappeared tomorrow" must be *answered directly*: the promise that **your life is portable and yours forever** (Law 11, baseline §10 export-as-a-right) must be visible and trustworthy, not buried — the user should *feel*, at all times, that this can never be locked away or lost, even if the company vanishes. Preservation software that could itself be lost is a contradiction.

### 15.4 The one-line test

Every screen, every flow, every word is measured against one sentence:

> **Does this feel like sitting around the family table telling stories — or like using software?**

If the latter, it is wrong, no matter how correct it is underneath.

---

## 16. Extension points for the assistant (deferred — seams only)

Per the mission, there is **no assistant integration** in Legacy's standalone product. But the experience is designed with clean seams so that, when the assistant (internally "Beth") arrives as a *consumer* of Canonical Truth (baseline §9, §13, §16-of-architecture), it deepens the experience without redesigning it. The seams already built:

- **Elicitation** — the optional "…and that reminds you of?" (§5.4) becomes true associative, sensory, meaning-seeking interviewing (baseline §5). The seam is the same continue-the-thread moment.
- **Gentle invitations** — the Hearth's people-nudges (§4.2) become proactive, loss-risk-aware preservation coaching driven by the composed Preservation Briefing (baseline §6.4, §9).
- **Natural-language search** — the search box (§12.3) gains "ask about your life" question-answering.
- **Connection** — background recognition (§7) gains an assistant that proposes richer connections, themes, and gaps.
- **Cross-domain** — a value or belief preserved in Legacy can, later, gently inform Faith or reflection elsewhere in WLJ.

Until then, every one of these works in a simpler, fully-standalone form. The product is complete without the assistant; the assistant only makes it *deeper*.

---

## Appendix — Surface behavior quick reference

For implementers: how each primary surface should behave, at a glance.

| Surface | Purpose | Must do | Must never do |
|---|---|---|---|
| **Remember (capture)** | Get a memory in, instantly | One tap from anywhere; voice-first; autosave; no required fields; offer "keep going?" | Require a title/category; block on any field; lose an in-progress thought |
| **Editor** | Hold and deepen a memory | Calm, distraction-free; inline media; undo everything; invisible version safety-net | Show word count / publish pressure; feel like a word processor |
| **Home (Hearth)** | Warm return + gentle direction | Resurface a memory; one humane invitation; continue an open thread | Show stats, a preservation score, or an admin panel |
| **Connect (recognition)** | Turn memories into connections | Background, optional, batched, conversational, warm; human "yes/no" | Block capture; interrupt emotion; show a list of extracted "records" |
| **Wander (explore)** | Move through the life associatively | "This leads to that" rails ranked by connection + significance; lenses as doors | Render a raw node-graph hairball; force a chronological spine |
| **People / Places / Photos / Moments / Threads** | Lenses into one web | Be doors into the same graph; feel alive and portrait-like | Feel like separate databases or folder trees |
| **Search** | Reach for a memory | One box; names, places, sayings, fragments, years, emotions | Require query syntax; feel like a database query |
| **Contributors** | Family co-authorship | "Ask them to help remember"; frictionless contribution; permanent attribution; record-together | Feel like permission management; ever drop attribution |
| **Media** | Doorways to memory | Auto-organize by connection; invite the story; batch-illuminate bulk imports; prioritize fragile media | Present as folders; demand per-photo filing |
| **Outputs** | Make gifts from the life | Born from context; ask "for whom"; regenerable; honor conflict gently | Feel like a separate export tool; imply a "finished book" is the goal |
| **Everywhere** | The promise | Make "yours, portable, forever" felt and trustworthy | Hide portability; imply lock-in |

---

*This is the definitive product-design reference for the WLJ Legacy Domain. It defines how every surface should feel and behave before implementation begins. It is built on the frozen architecture baseline and is designed to remain timeless: simple enough for anyone, powerful enough to preserve an entire lifetime — and, above all, to never feel like software, but like sitting around the family table telling stories.*
