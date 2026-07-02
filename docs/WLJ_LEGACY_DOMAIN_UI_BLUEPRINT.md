# WLJ Legacy Domain — Desktop UI Blueprint

> **Status:** Canonical UI design reference (baseline v1). This is the definitive desktop UI blueprint. Designers and engineers build screens from this; it defines layout, components, states, and behavior before implementation.
> **Companion to:** `WLJ_LEGACY_DOMAIN_ARCHITECTURE.md` (truth model) and `WLJ_LEGACY_DOMAIN_UX_ARCHITECTURE.md` (experience laws). This document is the *screen-level translation* of those two. Where it and the UX Laws disagree, the UX Laws win.
> **Established:** 2026-07-01
> **Not in scope:** code, components, CSS, implementation. No assistant integration — only marked seams (see §"Assistant seams").
> **Design north stars:** Apple (restraint, typography, calm), Notion (flexible content, no chrome), Linear (calm density, command-driven, speed), Arc (spatial warmth, a place you inhabit), Superhuman (keyboard-first, near-zero friction).

---

## 0. How to read this, and one honest challenge up front

The two prior documents are frozen. The architecture is a provenance-first assertion graph; the experience reduces to two verbs — **Remember** and **Wander** — with everything else hidden. This blueprint turns that into pixels-on-paper.

**The brief for this task contains two requests I must challenge before I design anything, because complying with them literally would break the frozen UX Laws:**

- **Screen 2 asks for an "intentionally administrative" dashboard with vanity statistics** (Total Memories, Completed, Media count…). The UX architecture explicitly rejected the stats dashboard and the preservation score because they turn the *keeper of a life* into the *operator of a database* and gamify grief (UX Law 1, Law 9).
- **Screen 3 asks for a "Memory Library" as the "primary management screen"** — a table with columns, filters, bulk actions. A spreadsheet of a human life, as the *primary* surface, is the single most "feels-like-software" thing we could build.

I am not going to refuse these — there is a *real* need underneath both. But I am going to **reframe** them, and the reframing is the most important design decision in this document:

> **Legacy has two modes. Keeping mode (99% of use) — remembering and wandering — is warm, emotional, and is the front door. Tending mode (occasional) — reviewing family contributions, finishing drafts, bulk-importing a shoebox of photos, generating a book — is deliberate, operational work that genuinely benefits from denser, more capable surfaces. The design serves tending mode fully, but never lets it colonize keeping mode.**

So the administrative dashboard and the management table both **exist and are designed here** — but they live in a deliberately-entered back-of-house called **The Studio**, never on the landing page, never with a life-completion score, and always in warm language. This is how we honor the brief's real intent (operators need control) without betraying the mission (this must not feel like software).

Everything below follows from that.

---

## 1. Design language — the calm premium system

### 1.1 The feeling

Reading and telling should feel like a **well-made book in a quiet room**; the interface around it should feel like **it isn't there**. Chrome recedes; content glows. Nothing is urgent. Nothing is gamified. Nothing blinks for attention.

### 1.2 The three-zone layout

Every screen is built from the same spatial grammar, so the product feels like one *place* (Arc), not a set of pages:

```
┌────────────┬──────────────────────────────────────────┬───────────────┐
│            │                                            │               │
│  NAV RAIL  │            THE CANVAS                       │  CONTEXT      │
│  (calm,    │   (the one thing you're doing right now:    │  PANEL        │
│   quiet,   │    reading, writing, wandering, a person)   │  (appears     │
│   ~220px,  │                                            │   only when    │
│   collaps- │                                            │   useful:      │
│   ible)    │                                            │   connections, │
│            │                                            │   details)     │
└────────────┴──────────────────────────────────────────┴───────────────┘
```

- **Nav rail** — a quiet left rail (collapsible to icons, Arc-style). Never more than a handful of destinations (§2).
- **The Canvas** — the emotional center. One focused thing at a time. Generous margins. Never cluttered.
- **Context panel** — a right-side panel that **appears only when it earns its place** (a person's connections while you read; the gentle "connections found" while you write). It is never permanently open, so the default is calm.

### 1.3 Typography — the single most important premium signal

- **Content (memories, stories, quotes, biographies): a warm serif.** Reading your grandmother's story should feel like reading a book, not a web app.
- **Chrome (nav, buttons, metadata, the Studio): a clean, quiet sans.** The UI voice is invisible; the human voice is the serif.
- Large, comfortable sizes by default (also the accessibility foundation, §Accessibility). Long-form reading measure (~66 chars). Real hierarchy, little decoration.

### 1.4 Color, light, and motion

- **Warm neutrals** — paper, ink, a single restrained accent. Light mode = daylight paper; **dark mode = evening lamplight** (not a cold black IDE — a warm, low, restful dark, because people preserve memories at night).
- **Motion is slow and calm** — gentle fades and settles, never bouncy, never celebratory-confetti. Motion should feel like turning a page, not winning a level.
- **No badges-as-pressure.** Count bubbles, streaks, and "you're behind" cues are banned (UX Law 9).

### 1.5 Speed and keyboard (Superhuman/Linear)

- **⌘K command palette** is the universal accelerator: jump to anyone, anywhere, anything; start any action; search the whole life. Power users can run Legacy almost entirely from the keyboard.
- **Remember is ⌘N from anywhere** and instant.
- The product is *fast*. Latency is an emotional signal: hesitation makes a life feel heavy; instant response makes it feel light and alive.

### 1.6 Voice as a first-class input surface

Because voice is a UX Law, a **microphone is a permanent, prominent affordance** in capture and search — not buried in a menu. Voice is offered *first* in the editor, and the command palette accepts spoken input. (Voice *navigation* — "take me to Grandpa" — is a natural later seam.)

---

## 2. Global navigation — the left rail

### 2.1 Final menu (challenging the seven-noun nav)

The nav is verb-and-few-nouns, not a table-of-contents of the database. Two groups: **Keeping** (warm, everyday) at top, **Tending** (operational, occasional) at bottom, visually separated.

```
┌────────────────────┐
│  ✦  Legacy         │   ← wordmark / space switcher
│                    │
│  ◉  Remember   ⌘N  │   ← primary action, not a page: big, warm, always here
│                    │
│  ▸ KEEPING         │
│  🔥  Home          │   ← the Hearth
│  🧭  Wander        │   ← associative rediscovery (Screen 12, reframed)
│  👤  People        │
│  📍  Places        │
│  🖼  Media          │
│                    │
│  ▸ TENDING         │
│  👪  Family        │   ← contributors (Screen 10, reframed)
│  ✶  Create         │   ← outputs (Screen 11, reframed)
│  🛠  Studio         │   ← the operational back-of-house (Screens 2 + 3 live here)
│                    │
│  ⌘K  Search        │
│  ⚙  Settings       │
│  ◐  You (account)  │
└────────────────────┘
```

**Icon intent** (concepts, not final art): Remember = a warm dot/quill; Home = hearth/flame; Wander = compass; People = two portraits; Places = map pin; Media = stacked photos; Family = linked figures; Create = a spark/quill; Studio = a drafting desk; Search = ⌘K glyph.

### 2.2 In nav vs. reached contextually

- **In nav:** Home, Wander, People, Places, Media, Family, Create, Studio, Search, Settings.
- **Contextual only (never in nav):** Person Profile, Place Profile, a Thread/Collection, the **Moments/Timeline lens** (opened *inside* Wander or a profile — because Timeline is a lens, not a store, per architecture §3.5), a Media item detail, an Output preview. You arrive at these by following the life, not by picking a menu.

### 2.3 Why "Moments/Timeline" is not top-level

Making Time a primary destination would quietly re-impose chronology as the organizing spine — the exact thing the architecture forbids. Time is available everywhere as a *lens* ("show this on a timeline") but is never the front door.

---

## 3. Global search — the command palette (⌘K)

**Purpose:** reach anything in a life instantly, and *feel like reaching for a memory*, not querying a database.

**Behavior:** ⌘K opens a centered palette (Linear/Superhuman). One field. It accepts:

- a **name** ("Walter"), a **place** ("the lake house"), a **year** ("1978"),
- a **half-remembered fragment or saying** ("measure twice…"),
- an **emotion or theme** where the graph supports it ("proud", "faith"),
- an **action** ("Remember", "Make a book about Mom", "Review family additions").

**Results** are grouped by kind — People · Places · Moments · Photos · Sayings · Memories · Actions — with the most connected/significant first (graph weight + significance). Voice input supported. Keyboard-drivable end to end.

**Empty/first-run:** shows recent people and a hint — *"Search for a name, a place, a year, or something someone used to say."*

**Assistant seam:** this palette is exactly where natural-language question-answering ("What was my grandfather like?") later lands — the field already accepts prose; the assistant simply gains the ability to *answer*, not just *find*.

---

## Screen 1 — Legacy Home (The Hearth)

**Purpose.** The warm return surface. Not a dashboard — *coming home to your life.* It shows you something worth feeling, and offers one gentle direction, and is always one tap from remembering.

**Layout (ASCII).**

```
┌───────────────────────────────────────────────────────────────┐
│                                                               │
│        Good evening.                          [ ◉ Remember ]   │
│                                                               │
│   ┌───────────────────────────────────────────────────────┐   │
│   │  ✦ On this day, 12 years ago                          │   │
│   │  ┌─────────┐                                          │   │
│   │  │  photo  │   "The morning we opened the shop…"       │   │
│   │  └─────────┘   in your voice · 2:14                    │   │
│   │                          [ Listen ]  [ Open ]          │   │
│   └───────────────────────────────────────────────────────┘   │
│                                                               │
│   Continue where you left off                                 │
│   ┌───────────────────────────────────────────────────────┐   │
│   │ ✎  "The summer we moved…"   started Tuesday   [Resume] │   │
│   └───────────────────────────────────────────────────────┘   │
│                                                               │
│   A gentle nudge                                              │
│   ┌───────────────────────────────────────────────────────┐   │
│   │ 👤 You've mentioned your grandfather often, but never   │   │
│   │    told a story just about him.        [Tell it]  [×]  │   │
│   └───────────────────────────────────────────────────────┘   │
│                                                               │
│   From your family                                            │
│   ┌───────────────────────────────────────────────────────┐   │
│   │ 👪 Sarah added a memory about the lake house  [Read it]│   │
│   └───────────────────────────────────────────────────────┘   │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

**Components.** Time-of-day greeting; **Resurfaced memory** card (photo/story/saying, with audio if it exists); **Continue** card (open threads); **Gentle nudge** (the humanized loss-risk triage — one at a time, dismissible, about *people* not metrics); **From your family** (incoming contributions as gifts).

**Buttons.** `◉ Remember` (primary, persistent); per-card `Listen / Open / Resume / Read it / Tell it`; nudge `×` to dismiss.

**No.** No statistics, no preservation score, no counts, no "completion." (Challenge to the brief: this is deliberate — see §0.)

**Empty state (brand-new user).** The Hearth is never cold. It becomes a single warm invitation:

```
        Welcome. This is where your life will live.

        Start with a memory, a photo, or someone you love.

        [ ◉ Tell your first memory ]   [ Add a photo ]   [ Add a person ]
```

**Example data.** As above (shop opening, the move, grandfather, Sarah + lake house).

**Interactions.** Cards are quiet until hovered; hover reveals actions. Dismissing a nudge never deletes anything — it just steps back. Everything here deep-links into the relevant memory/person/thread.

**Assistant seam.** The "gentle nudge" slot is where proactive, briefing-driven preservation coaching later appears — same slot, richer intelligence, no redesign.

---

## Screen 2 — The Studio Overview (the brief's "Dashboard," reframed)

**Challenge & reframe.** The brief wants an "intentionally administrative" dashboard. I keep the operational capability but (a) move it **off the landing page into the Studio**, (b) **replace vanity metrics with actionable ones**, and (c) **ban the preservation score**. Nobody should be greeted by "you are 3% done preserving your life." But someone who *chooses* to enter the Studio to do the work deserves a clear, capable control surface.

**Purpose.** The back-of-house for *tending mode*: see what needs your attention, do batch work, manage imports and outputs — calmly and efficiently.

**Layout (ASCII).**

```
┌───────────────────────────────────────────────────────────────┐
│  The Studio                                                   │
│  A quiet workshop for tending your life's record.             │
│                                                               │
│  Needs you                                                    │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐        │
│  │ 3 family      │ │ 5 unfinished  │ │ 1 import       │        │
│  │ additions to  │ │ memories      │ │ waiting to be  │        │
│  │ welcome →     │ │ to continue → │ │ sorted →       │        │
│  └───────────────┘ └───────────────┘ └───────────────┘        │
│                                                               │
│  Quick actions                                                │
│  [ ◉ New memory ]  [ ⇪ Import photos ]  [ ✶ Make something ]   │
│  [ 🗂 All memories ]                                            │
│                                                               │
│  Lately                                                       │
│  • You kept "The morning we opened the shop"      2h ago      │
│  • Sarah added a memory about the lake house      yesterday   │
│  • 214 photos imported from "Mom's box"           Sunday      │
│                                                               │
│  A quiet sense of your record        (optional, understated)  │
│  Decades touched: 1940s → 2020s   ·   Voices preserved: 6      │
│  People who have no story yet: 4   [see them →]                │
└───────────────────────────────────────────────────────────────┘
```

**Components.** **"Needs you"** actionable cards (review queue, unfinished, imports) — these replace vanity stats with *things to do*; **Quick actions**; **Lately** (recent activity, plain-language, warm); an **understated "sense of your record"** strip — *not a score*, but honest, meaningful, non-gamified facts (decades touched, voices preserved, **people with no story yet** — which is the loss-risk triage stated as an invitation, not a gauge).

**Buttons.** New memory; Import; Make something; All memories (→ Screen 3); each "Needs you" card routes to its queue.

**Empty state.** *"Nothing needs tending right now. When family adds memories or you leave something unfinished, it'll wait for you here."*

**Interactions.** Everything routes into a focused work surface (review, editor, importer, output). Studio is *calm work*, not a metrics wall.

**Why this is not a betrayal of the mission.** The user only sees this because they *chose* to enter the Studio. The emotional front door (Home) stays pure; the workshop is available when they want to roll up their sleeves.

**Assistant seam.** "Needs you" is where the assistant later prioritizes what matters most (fragile sources first) rather than just listing queues.

---

## Screen 3 — All Memories (the brief's "Memory Library," reframed)

**Challenge & reframe.** A table-of-a-life as the *primary* screen is rejected (§0). But a **powerful way to find and manage many memories at once** is a legitimate tending-mode need. So: this lives in the Studio, **defaults to a warm, browsable view, and offers an optional dense list/table "power view"** for people who genuinely want to manage in bulk. Both exist; the warm one is the default.

**Purpose.** Find, revisit, and (occasionally) manage memories in quantity — without feeling like a spreadsheet of your life.

**Layout — default (warm) view.**

```
┌───────────────────────────────────────────────────────────────┐
│  All memories        [🔎 filter]  [↕ sort]   [ ▤ list view ]    │
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │  photo   │  │  photo   │  │ 🎙 audio │  │  photo   │        │
│  │ The shop │  │ The move │  │ Grandpa… │  │ Wedding  │        │
│  │ · you    │  │ · you    │  │ · Sarah  │  │ · you    │        │
│  │ Kept     │  │ Just for │  │ Kept     │  │ Kept     │        │
│  │          │  │ me       │  │          │  │          │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│                                                               │
│  … infinite, gently paged; never "here are all 10,000"        │
└───────────────────────────────────────────────────────────────┘
```

**Layout — optional list (power) view** (`▤`): a calm, Linear-style list — not a heavy grid of DB columns. Shows Title · Teller · When · State (Just for me / Kept / Shared) · a small media glyph. **No "record ID" energy.** Multi-select enables bulk actions.

**Components.** Filter (by person, place, entry type, teller, has-media, time, state); sort; view toggle (cards ⇄ list); multi-select for bulk.

**Buttons / bulk actions.** Open, Continue, **Keep** (not "Approve"), Share, Set aside (archive), Duplicate, Connect. **Delete is deliberately demoted** and guarded (see below).

**On "Delete."** The brief lists Delete as a bulk action. Per the architecture, attestations are append-only and this app's whole premise is *nothing is lost*. So the primary destructive action is **Set aside** (archive — reversible, never gone). True deletion exists only as a rare, heavily-confirmed, single-item action ("remove permanently"), never a casual bulk button. This is both an architecture requirement and an emotional one.

**Empty state.** *"Every memory you keep will gather here. Nothing is ever lost — even the ones you set aside."*

**Interactions.** Card → opens memory. List → keyboard navigable. Filters compose. Bulk select is for genuine tending (e.g., "share all lake-house memories with the family").

**Assistant seam.** Later, "find all the memories where Dad talked about faith" becomes a natural-language filter here.

---

## Screen 4 — Memory Editor (the most important screen)

**Purpose.** Hold and deepen a single memory. Feels like a journal page after someone says *"tell me about it"* — calm, private, unhurried, forgiving. **Not a word processor.**

**Layout (ASCII).**

```
┌───────────────────────────────────────────────────────────────┐
│  ‹ Home                          Just for me ▾     ⌫ (undo)     │  ← state selector; autosave silent
│                                                               │
│        🎙  Tap to talk, or just start writing…                 │  ← voice offered FIRST, big
│                                                               │
│   The morning we opened the shop, it was raining so hard we    │  ← serif, book-like, generous
│   almost didn't go. Dad had the key in his coat pocket…        │
│                                                               │
│        [ + photo / audio / video / letter ]  (inline)          │
│                                                               │
│                                                               │
│   ───────────────────────────────────────────────────────    │
│   (nothing else competes for attention — no toolbar wall,      │
│    no word count, no "publish")                                │
│                                                               │
│                                   [ Keep memory ]              │  ← not "Approve"
└───────────────────────────────────────────────────────────────┘
```

**Right context panel — "Connections" (appears quietly, never blocks).** After you pause or finish, a soft panel *offers* what it noticed — it does **not** throw up a mandatory review wall:

```
                                    ┌───────────────────────────┐
                                    │  Noticed in this memory    │
                                    │  (optional — tidy anytime) │
                                    │                            │
                                    │  👤 Dad            [✓][✎][×]│
                                    │  📍 The shop       [✓][✎][×]│
                                    │  🗓 ~1985          [✓][✎][×]│
                                    │  🗣 "in his coat…" [✓][✎][×]│
                                    │                            │
                                    │  [ Connect these ]         │
                                    └───────────────────────────┘
```

**Components.** Voice recorder (primary) with live transcription (original audio always kept); distraction-free serif writing area; inline media insertion; **state selector** (Just for me ▾ → Kept → Shared); silent autosave; invisible version history (append-only) reachable via "…how I told this before"; the optional **Connections** panel (extraction → the promotion gate, humanized).

**Buttons.** `🎙 Talk`; `+ media`; `Keep memory`; per-connection `✓ accept / ✎ modify / × dismiss`; `Connect these`.

**Terminology.** Uses **"Keep memory,"** not "Approve" (the brief invited a better term). States are **Just for me / Kept / Shared**. "Draft" and "Approve" never appear.

**Critical behaviors (from UX Laws).**
- **Capture is never gated:** no required title, no mandatory tagging, `Keep` is optional — a memory is preserved the instant it exists.
- **Analysis never ambushes:** Connections appear *quietly, after* you're done, and are fully ignorable. Right after a hard memory, the panel stays closed.
- **Editing later = deepening:** returning adds a layer; the prior telling is preserved beneath, never overwritten.

**Empty state.** The blank editor itself is the empty state — warm, with the mic and *"…or just start writing."* A first-timer sees one optional line of guidance, then silence and space.

**Example data.** The shop-opening memory (above).

**Assistant seam.** Two seams, both already-shaped: (1) the optional "…and that reminds you of?" continue-prompt becomes true elicitation; (2) the Connections panel becomes assistant-proposed richer links, themes, and gaps.

---

## Screen 5 — People

**Purpose.** The primary index of a life — because humans recall by person first. A **gallery of faces**, alive and portrait-like, *not* a CRM contact list.

**Layout (ASCII).**

```
┌───────────────────────────────────────────────────────────────┐
│  People                         [🔎]  [ + Add someone ]         │
│                                                               │
│  ⦿ Closest        ○ Family        ○ Everyone                   │
│                                                               │
│   ◯Dad     ◯Mom     ◯Grandpa   ◯Sarah    ◯Aunt Carol           │
│   Walter   Elena    Walter Sr. (you)     Carol                 │
│   47 mem   39 mem   12 mem     8 mem      6 mem                │
│                                                               │
│   ◯Coach   ◯Uncle   ◯…                                          │
│   Ellis    Joe                                                 │
│                                                               │
│   ⚠ 4 people you've mentioned have no story yet  [see them]    │
└───────────────────────────────────────────────────────────────┘
```

**Components.** Face gallery (photo-forward; graceful monogram if no photo); segmented views (Closest / Family / Everyone); per-person a name + a *warm* count phrased gently ("47 memories," not a metric badge); a soft **"no story yet"** prompt (loss-risk, humanized).

**Buttons.** `+ Add someone`; search; view segments; card → Person Profile.

**Empty state.** *"The people who shaped you will gather here. Start with one — a parent, a friend, someone you miss."* `[ Add the first person ]`

**Interactions.** Click a face → Profile. Hover → a whisper of their essence (a saying, a favorite photo). Faces sort by connection/significance, so the most present people surface first.

**Assistant seam.** Later, "who haven't I preserved enough of?" ranking and gentle prompts.

---

## Screen 6 — Person Profile

**Purpose.** Everything connected to one person, assembled as a **living portrait** you can *meet* — the emotional heart of "wandering."

**Layout (ASCII).**

```
┌───────────────────────────────────────────────────────────────┐
│  ‹ People                                                     │
│   ┌───────┐   Walter Ellison  ("Dad")                         │
│   │ photo │   1931–2009 · your father · the shop, Soddy Daisy  │
│   └───────┘   🎙 Hear his voice   [ ◉ Remember about him ]      │
│                                                               │
│   ┌── Who he was ──────────────────────────────────────────┐  │
│   │ A quiet man who opened the hardware store in '85…       │  │
│   │ (woven from your memories — always shows where it       │  │
│   │  came from; contested details shown as "some remember…")│  │
│   └────────────────────────────────────────────────────────┘  │
│                                                               │
│   His sayings 🗣      "Measure twice, cut once."               │
│   Stories 📖 (47)     Photos 🖼 (63)     Voice 🎙 (4)           │
│   People 👥           Mom · Grandpa · Uncle Joe · you          │
│   Places 📍           The shop · Soddy Daisy · the lake house  │
│   On a timeline 🗓    [open the years of his life →]           │
│   Remembered by 👪    you · Sarah · Aunt Carol                 │
│                                                               │
│   [ ✶ Make something about Dad ]                               │
└───────────────────────────────────────────────────────────────┘
```

**Components.** Portrait header (photo, dates, relationship, a **"Hear his voice"** affordance if audio exists); a **"Who he was"** narrative woven from memories — always with quiet provenance and *gentle* handling of contested facts ("some remember it as…"); rows of everything connected — **Sayings, Stories, Photos, Voice, People, Places, Timeline lens, Remembered-by (contributors)**; contextual `Make something about [Dad]`.

**Buttons.** `Remember about him`; `Hear his voice`; `Make something`; every connected item is a doorway (tap a place → Place Profile; a person → their profile).

**Empty / thin profile.** If little exists: *"You've mentioned Dad in a few memories. Want to tell one just about him?"* — turning emptiness into invitation.

**Interactions.** This is the **wandering** engine in profile form: every element leads onward (UX §9.2). Reading "Who he was" and tapping "the lake house" carries you *there*, with the lake house's own web around you.

**Assistant seam.** "Who he was" is a *projection* — later the assistant can narrate richer biographies, always grounded, always honest about uncertainty.

---

## Screen 7 — Places

**Purpose.** Browse a life spatially — a childhood home is a doorway to a decade. Places as **warm cards and/or a map**, not a location database.

**Layout (ASCII).**

```
┌───────────────────────────────────────────────────────────────┐
│  Places                     [🗺 map]  [▦ cards]  [ + Add ]      │
│                                                               │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐                 │
│  │  photo     │ │  photo     │ │  photo     │                 │
│  │ The lake   │ │ The shop   │ │ Soddy      │                 │
│  │ house      │ │            │ │ Daisy, TN  │                 │
│  │ 31 memories│ │ 22 memories│ │ 40 memories│                 │
│  └────────────┘ └────────────┘ └────────────┘                 │
└───────────────────────────────────────────────────────────────┘
```

**Components.** Toggle between **map** (pins where memories cluster) and **cards** (photo-forward places with gentle counts); add-place; search.

**Buttons.** Map/cards toggle; `+ Add place`; card/pin → Place Profile.

**Empty state.** *"The places that mattered — homes, towns, a favorite table — will gather here."* `[ Add a place ]`

**Interactions.** Map is for spatial recall ("everywhere we lived"); cards for browsing. Both lead to Place Profiles.

---

## Screen 8 — Place Profile

**Purpose.** Everything connected to a place, assembled like a Person Profile — a doorway into a whole era.

**Layout.** Mirrors Screen 6: header (photo, name, the years it was in your life, on-a-map affordance), a **"What it was"** narrative, then connected rows — **Stories, Photos, People who were there, Moments/years, Sayings tied to it, Traditions** — and contextual `Make something about the lake house`.

**Empty / thin.** *"You've mentioned the lake house a few times — want to describe it? What did it smell like?"* (sensory prompt — the fragment layer).

**Interactions.** Same associative wandering: tap a person who was there → their profile; tap a summer → that moment.

**Assistant seam.** Sensory/place elicitation ("what did it sound like?") and richer place narratives later.

---

## Screen 9 — Media Library

**Purpose.** Media as **doorways to memory**, not files to manage. Find, view, and connect photos/video/audio/documents — with the system doing the organizing.

**Layout (ASCII).**

```
┌───────────────────────────────────────────────────────────────┐
│  Media          [⇪ Import]   filter: [All][Photos][Voice][Video]│
│                             [Letters][Docs]   [◱ needs a story] │
│                                                               │
│  ▤ 1985 — The shop opens (14)                                  │
│   [▢][▢][▢][▢][▢][▢][▢]  …                                      │
│                                                               │
│  ▤ Unsorted — "Mom's box" (214)   help me understand these →   │
│   [▢][▢][▢][▢][▢][▢][▢]  …                                      │
│                                                               │
│  ◱ 37 photos have no story yet    [add stories]                │
└───────────────────────────────────────────────────────────────┘
```

**Components.** **Import** (bulk); type filters; a **"needs a story"** filter (media with no attested meaning = unpreserved); **auto-clusters** by time/place/face (never folders the user maintains); the **"help me understand these"** batched flow for big imports; each item shows *all stories it's connected to*.

**Media item detail (contextual).** Large view of the photo/clip; **"who's in this / where / when / what was happening"** gentle prompts; a list of **every memory this appears in** (one photo lives in many memories — the graph, visible); download.

**Buttons.** `Import`; filters; `help me understand these`; per-item `add a memory`, `who's in this?`, connect.

**Bulk import (box-of-100,000).** A calm, resumable flow: the system clusters, then asks a *few* high-leverage questions ("Is this cluster your wedding?") that illuminate hundreds at once. **Never** a per-photo tagging to-do list. Fragile/undigitized media flagged first.

**Empty state.** *"Photos, voices, letters, film — bring them in, and we'll gently help you remember the stories inside them."* `[ Import your first photos ]`

**Assistant seam.** Face/scene recognition assist and auto-suggested connections later; NL "find the photo of Dad at the lake."

---

## Screen 10 — Family (the brief's "Contributors," reframed)

**Challenge & reframe.** "Contributors" and "permissions" is admin language. This is **Family** — the people who help you remember — framed as *invitation and gift*, with the security machinery invisible.

**Purpose.** Invite family to add memories, welcome their contributions, and (quietly) manage access and safety.

**Layout (ASCII).**

```
┌───────────────────────────────────────────────────────────────┐
│  Family                                   [ + Invite someone ]  │
│                                                               │
│  Waiting for you (gifts to welcome)                            │
│  ┌───────────────────────────────────────────────────────┐    │
│  │ 👤 Sarah — "The lake house summers"     [Read & keep]  │    │
│  │ 👤 Aunt Carol — a memory of Dad         [Read & keep]  │    │
│  └───────────────────────────────────────────────────────┘    │
│                                                               │
│  Your family                                                  │
│  ◯ Sarah   can add · 8 memories        ◯ Carol  can add · 6    │
│  ◯ Tom     can see                                            │
│                                                               │
│  Invite someone to help remember                              │
│  [ by email ]  [ shareable link (expires) ]                   │
└───────────────────────────────────────────────────────────────┘
```

**Components.** **"Waiting for you"** = incoming contributions framed as gifts to welcome (review = read-and-keep, with permanent attribution); **Your family** list with human roles (**can see / can add / can help manage**); **Invite** (email or expiring secure link).

**The "record together" moment.** A prominent option: *"Sitting with someone? Record a memory together."* → opens a shared recording session, attributed to the elder. This is the fragile-source experience surfaced as a first-class button.

**Buttons.** `Invite someone`; `Read & keep`; per-person role menu; `Record together`.

**Security, invisible.** Expiring links, email verification, bot/spam protection all run underneath; the good-faith family member sees only a warm invite → talk/type → done. Suspected-bot or spam contributions are quietly quarantined for the owner, never auto-published.

**Empty state.** *"A life is remembered together. Invite the people who share your stories — your kids, your siblings, old friends."* `[ Invite your first ]`

**Assistant seam.** Later: suggested people to invite (who holds memories you lack), and gentle "record with Mom while you can" nudges.

---

## Screen 11 — Create (the brief's "Output Generator," reframed)

**Challenge & reframe.** Not an "export module." **Create** is where you make *gifts* from the life — and, per the architecture, outputs are **projections: never canonical, always regenerable.** The design must make that felt: making a book should feel joyful and low-stakes, never like configuring an export.

**Purpose.** Turn the life (or a slice of it) into something shareable — a memoir, a children's book, a photo album, a timeline, a documentary outline, a digital museum.

**Layout (ASCII).**

```
┌───────────────────────────────────────────────────────────────┐
│  Create something                                             │
│                                                               │
│  1 · What?                                                    │
│  [📖 Memoir] [🧒 Children's book] [🖼 Photo album]             │
│  [🗓 Timeline] [🎬 Documentary outline] [🏛 Digital museum] …  │
│                                                               │
│  2 · About whom / what?                                       │
│  [ Your whole life ] [ A person ▾ ] [ A place ▾ ]             │
│  [ A time period ▾ ] [ A collection ▾ ]                       │
│                                                               │
│  3 · For whom?                                                │
│  [ For adults ] [ For a child ] [ For the family ]           │
│                                                               │
│                         [ Preview → ]                         │
│                                                               │
│  (You can always make another, differently. Nothing here is  │
│   final, and nothing changes your memories.)                  │
└───────────────────────────────────────────────────────────────┘
```

**Components.** Three calm choices — **What / About whom / For whom** (audience is first-class, per architecture §8.4) — then a **live preview** you can refine; export/share when happy. A persistent, reassuring line: *outputs are regenerable and never alter the life.*

**Contextual entry.** Create is *also* invoked from where you stand: `Make something about Dad` on a profile pre-fills step 2. That is the more natural path; this screen is the deliberate one.

**Honesty in outputs.** Previews render contested memories gently ("some remember…") and never present low-confidence facts as settled — but in warm prose, never "confidence: 0.4."

**Buttons.** Type chips; scope pickers; audience; `Preview`; in preview: `Refine`, `Make another`, `Export / Share`.

**Empty state.** *"When you're ready, turn your memories into something to hold or share — a book, an album, a story for the grandkids. There's no rush, and you can make as many as you like."*

**The demotion (design stance).** Create is intentionally *not* the star of the product. The star is the living, wanderable, voice-carrying web (the life itself). Outputs are wonderful, disposable gifts *from* it. The UI never implies "finish the book" is the goal.

**Assistant seam.** Drafting assistance (the assistant narrates a first draft you edit) plugs directly into Preview — grounded, cited, honest.

---

## Screen 12 — Wander (the brief's "Legacy Explorer," reframed)

**Challenge & reframe.** The brief asks to challenge the graph-explorer concept. **A raw node-graph is rejected** as the primary UI: at real scale it's an unreadable hairball, and "here's a diagram of your life" is cold. The graph is the *engine*; **Wander** is the *experience* — associative rediscovery that feels like memory itself moving.

**Purpose.** Rediscover a life by following connection, from any starting point, endlessly — "…and that reminds you of…" made navigable.

**Layout (ASCII).**

```
┌───────────────────────────────────────────────────────────────┐
│  Wander                        start anywhere: [🔎 or surprise me]│
│                                                               │
│   You're with:  Walter Ellison ("Dad")            [pin ⨀]     │
│   ┌───────┐                                                   │
│   │ photo │   "Measure twice, cut once."  🎙                   │
│   └───────┘                                                   │
│                                                               │
│   This leads to…                                              │
│   ┌── People ──┐ ┌── Places ──┐ ┌── Stories ──┐ ┌─ Photos ─┐  │
│   │ Grandpa    │ │ The shop   │ │ Opening day │ │ [▢][▢][▢] │  │
│   │ Uncle Joe  │ │ Soddy D.   │ │ The flood   │ │           │  │
│   │ you        │ │ Lake house │ │ …           │ │           │  │
│   └────────────┘ └────────────┘ └────────────┘ └──────────┘  │
│                                                               │
│   ← back      breadcrumb: Home › Dad › (tap any card to move) │
└───────────────────────────────────────────────────────────────┘
```

**Components.** A **"you're with…" focus** (a person/place/photo/saying); **connected rails** grouped by kind and ranked by connection-strength (evocation weight) + significance; a **"surprise me"** to jump somewhere resurfaced; a **breadcrumb trail** of your wander; a **pin** to hold something aside as you roam.

**On the graph visualization.** Offered only as an *optional, secondary "constellation" view* for those who enjoy it — never the default, and gracefully degrading to neighborhoods (never the full 5,000-node hairball). The default is the rails.

**Buttons.** `Surprise me`; any card = move there; `back`; `pin`; breadcrumb hops.

**Empty state.** *"Once you've added a few memories, this is where they start to connect — one leading gently to the next."* Until then, `[ Tell a memory ]`.

**Interactions.** Tapping a card re-centers Wander on that node; the trail records the path (a genuine "walk through your life"). This is where a grandchild, decades later, *meets* the person by wandering.

**Assistant seam.** Guided wandering ("walk me through Dad's life") and thematic tours later — same surface, richer guide.

---

## Notifications — should Legacy have them?

**Mostly no — and that restraint is a feature.** A life is not urgent; nagging violates emotional safety (UX Law 9). **Banned outright:** streaks, "you haven't logged in," completion pressure, count-badge anxiety.

**Permitted, gentle, opt-in, digest-style:**
- **A family gift arrived** — "Sarah added a memory" (warm, never urgent).
- **A resurfaced memory** — an occasional, opt-in "on this day" (delight, not obligation).
- **A fragile-source whisper** — *very sparingly* — "It's been a while since you recorded with your mom." (This is the loss-risk triage; it must be rare and tender, never guilt-inducing.)

**Design.** In-app first (a quiet tray, no red bubbles); email/push strictly opt-in and low-frequency (a monthly "your family added 3 memories" digest, at most). Every notification is a *gift or an invitation*, never a demand.

**Assistant seam.** Proactive preservation coaching later routes through this same gentle, opt-in channel — richer, but never louder.

---

## Empty states — the first, most important design moment

A brand-new user faces the hardest screen in software: **a blank life.** Empty states must *invite*, never *apologize* or show a sad-face-zero. Principles:

- **Never show "0."** Show a warm sentence and one clear first act.
- **Lower the blank-page terror** with the smallest possible starting move (one memory, one photo, one person).
- **Offer three doors** on first run (memory / photo / person) so the user starts where *they* feel pulled.
- Each screen's empty state is written above; all share the voice: *"This is where [X] will live. Start with one."*

**The first-run arc (no onboarding wizard — challenge to convention).** Instead of a multi-step setup, the Hearth simply *is* the onboarding: one warm welcome, three doors, and the moment they capture the first memory, the product quietly comes alive around them. No forms, no tour, no account-setup marathon.

---

## Accessibility — designed in, not bolted on

- **Older adults (a primary, not edge, user).** Large, warm type by default; high-contrast option; generous touch/click targets; plain language; radical simplicity; a UI that never needs re-learning across decades. The simplest design is also the most accessible.
- **Voice-first users.** Voice is a first-class *input* (capture, search, and later navigation), not an afterthought; everything capturable by voice; audio always preserved.
- **Large libraries.** Never render the pile; search-first, virtualized, gently paged. The user meets curated surfaces, never a 10,000-row wall (also a performance stance: read pre-computed/cached views, never live-compute on the request path — per platform observability law).
- **Long writing sessions.** Silent autosave; no timeouts; no lost work ever; distraction-free; resumable from anywhere (the Hearth's "continue" card).
- Full keyboard operability (⌘K and shortcuts); screen-reader-sound structure; respects reduced-motion and OS text-size.

---

## Assistant seams — where Beth plugs in later (do not build now)

One consolidated map. Every seam is *already shaped* by the standalone UI, so the assistant is added as a **consumer** with **no redesign** (architecture §9, UX §16):

| Surface | Standalone today | Assistant seam (later) |
|---|---|---|
| Home — "gentle nudge" slot | One deterministic invitation | Proactive, briefing-driven preservation coaching |
| Editor — continue prompt | "…and that reminds you of?" | True associative, sensory, meaning-seeking interviewing |
| Editor — Connections panel | Deterministic extraction + human confirm | Assistant-proposed richer links, themes, gaps |
| Search (⌘K) | Deterministic find | Natural-language question-answering about the life |
| Wander | Manual associative roaming | Guided tours ("walk me through Dad's life") |
| Person/Place "Who it was" | Deterministic projection | Richer grounded biography narration |
| Create — Preview | Template projection | Assistant-drafted, grounded, cited first drafts |
| Notifications | Rare gentle invitations | Prioritized (fragile-first) proactive stewardship |
| Family | Manual invite | Suggested people to invite / record-with-now |

The product is **complete without the assistant**; the assistant only makes it *deeper*.

---

## Final review — self-critique and redesign

The brief requires me to hunt down anything that still feels like software and fix it. Here is that pass, honestly.

1. **The Studio (Screen 2) is the highest residual risk.** Even reframed, a workshop with queues can drift toward an admin console. **Redesign applied:** it is off the front door, entered only deliberately; vanity metrics replaced with *"Needs you"* actions; the preservation score banned; the one "sense of your record" strip is understated, honest, and non-gamified (and even that is optional/collapsible). If usability testing shows people still feel like operators there, the fallback is to dissolve the Studio entirely and scatter its three functions (review, drafts, imports) into Home invitations and contextual actions.

2. **The "All Memories" list (Screen 3) can still read as a database table.** **Redesign applied:** the *default* is warm cards; the table is an opt-in power view; DB-column energy is removed (no IDs, human state words, teller not "created_by"); Delete is demoted to Set-aside. Guard rail: if the list view is where most people live, that's a signal the warm surfaces (Home/Wander) aren't pulling their weight — treat it as a *symptom*, not a preference to cater to.

3. **The extraction/Connections step is the classic "data-entry creeps back in" trap.** **Redesign applied:** it never blocks capture, never auto-opens after an emotional memory, is framed as recognition with warm language, and the product is fully valuable if it's ignored forever. It is enrichment, not a required workflow.

4. **People risked becoming a CRM contact list.** **Redesign applied:** photo-forward *portraits*, warm count phrasing (not metric badges), essence-on-hover, significance-ranked — you meet people, you don't manage contacts.

5. **Create risked feeling like an export wizard.** **Redesign applied:** three warm choices not a config form; audience first-class; live preview; the persistent "you can always make another, nothing is final" reassurance; and it's deliberately demoted beneath the living web.

6. **A deeper critique the pass surfaced: are there too many destinations?** Nine nav items is more than Superhuman/Linear restraint likes. **Redesign applied / stance:** the Tending group (Family/Create/Studio) is visually separated and can collapse; a first-time user effectively sees Home + Remember and grows into the rest. If testing shows overload, People/Places/Media can fold behind Wander as lenses, leaving a truly minimal rail (Home · Wander · Remember). I've kept them visible for v1 discoverability but flagged the collapse path.

7. **The truest test, applied to the whole thing:** *does opening this feel like coming home, or like opening software?* Home, Wander, the profiles, and the editor pass. The Studio and the list are where vigilance is permanently required — hence they are quarantined to tending mode and watched.

**Net:** the emotional path (Home → Remember → Wander → profiles → Create-as-gift) is a *place*, not an app. The operational path (Studio → All Memories → review/import) is honest, capable back-of-house that stays out of the emotional path. That separation is the design.

---

## Appendix — screen inventory, placement, and shortcuts

| # | Screen | Nav placement | Feels like |
|---|---|---|---|
| 1 | Home (Hearth) | Keeping · Home | Coming home |
| — | Remember (editor entry) | Persistent action · ⌘N | "Tell me about it" |
| 12 | Wander | Keeping · Wander | Memory moving |
| 5 | People | Keeping · People | A wall of faces |
| 6 | Person Profile | Contextual | Meeting someone |
| 7 | Places | Keeping · Places | Walking the map of a life |
| 8 | Place Profile | Contextual | Standing there again |
| 9 | Media | Keeping · Media | Doorways to memory |
| 10 | Family | Tending · Family | Giving & receiving gifts |
| 11 | Create | Tending · Create + contextual | Making a gift |
| 2 | Studio Overview | Tending · Studio | A quiet workshop |
| 3 | All Memories | Tending · Studio → All memories | Tidying the shelves |
| — | Search / ⌘K | Global | Reaching for a memory |

**Core shortcuts:** ⌘N Remember · ⌘K Search/command · ⌘/ back · Space to play audio · Esc to step back. Fully keyboard-drivable; voice-invokable.

---

*This is the definitive desktop UI blueprint for the WLJ Legacy Experience. It is built on the frozen architecture and UX documents and is designed to feel calm, premium, timeless, and warm — a place someone enjoys spending time, where an entire human life can be preserved, and which never feels like software, but like sitting around the family table telling stories.*
