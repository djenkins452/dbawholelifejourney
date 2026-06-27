# Medication & Supplement Intelligence v2 — Phase 3: Product Experience & UX Specification

**Status:** Phase 3 — PRODUCT DESIGN ONLY. No code, no migrations, no models, no implementation, no architecture redesign.
**Date:** 2026-06-27.
**Role:** Lead Product Designer.
**Inputs:** Phase 1 (architecture vision), Phase 2 (reconciliation + migration). This document drives UI/UX design; it does not change the architecture those phases established.

> **Canonical UX test set — note.** No reference images were attached to this session. Rather than invent what was shown, this spec adopts the *enumerated* label types as the canonical capture test set: prescription pill bottles, supplement bottles, **injection pens** (insulin/GLP-1), OTC packages, multiple pharmacy-label layouts, **Supplement Facts** panels, **Drug Facts** panels, QR codes, and 1D/2D barcodes (NDC). Every capture workflow below is designed to comfortably handle all of them. When real images are provided, the guided-capture decision tree (§7) should be validated against them.

> **WLJ laws this design obeys (non-negotiable, product-visible):**
> - **Visual Truth Contract** — *only actual user completion may visually resemble completion.* Taken doses get the "done" treatment (fill, check, color); pending/overdue/missed/low get badges, muted text, or rail color — **never** completion-resembling visuals. This shapes every dashboard state below.
> - **Beth is a Chief of Staff, not a clinician** — observes, educates, prepares physician discussion; never diagnoses, prescribes, or recommends dose changes.
> - **OCR is never truth** — every extracted value is a reviewable draft with confidence; nothing canonical until the user confirms.
> - **History is forward-only** — WLJ cannot reconstruct pre-existing dose changes; the UX states this honestly and never fabricates a timeline.
> - **"Chief of Staff" in all user-facing copy** — never the personal assistant name in shipped strings.
>
> **Naming note (C9):** for readability this document refers to the assistant as **"Beth"** throughout, but **every "Beth" here renders as "Chief of Staff" (or "your assistant") in shipped UI copy, microcopy, and labels.** "Beth" is an internal/configurable name and must never appear in a shipped string (e.g., "Ask Beth" ships as "Ask your Chief of Staff"). See the Canon §7 naming rule.

---

## 1. Product Vision

Medication Intelligence is the WLJ capability that turns *"what am I taking?"* into *"is my treatment working, and what should I do with that?"* It is a flagship surface — not a reminder app, not a pill tracker, not adherence software. It is a **treatment intelligence companion** that helps a user understand what they take, why, how consistently, how it's changing, how it interacts with the rest of their life, and what's worth raising with their physician.

The experience principle: **every interaction increases understanding — it never just displays data.** A number always comes with a meaning. A trend always comes with a "so what." A missed dose is a neutral observation, never a scolding. The system is simple, intelligent, helpful, encouraging — never overwhelming, never judgmental, never alarmist.

It feels unmistakably like Whole Life Journey: the same calm visual language, the same Chief-of-Staff voice, the same respect for the user's autonomy and their relationship with their real physician.

---

## 2. User Personas

Personas are grounded in WLJ's actual user reality (the app already models glucose/CGM, insulin subtypes, GLP-1 use, cycling workouts, labs, and supplements).

**P1 — "The Engaged Manager" (primary).** Mid-life, a chronic condition under active treatment (e.g., type 2 diabetes), on multiple therapies — a basal insulin (Lantus), a GLP-1 (Mounjaro), plus supplements. Tracks glucose (CGM), weight, and exercise. Wants to *understand* whether treatment is working, prepare for endocrinology visits, and learn how rides/sleep/meals affect glucose. **Needs:** treatment momentum, cross-domain observations, physician prep, learning plans. High engagement, daily visits.

**P2 — "The Busy Adherer."** Healthy-ish, 1–3 maintenance meds (statin, BP med) + a couple of supplements. Wants low-friction logging, refill warnings, and reassurance. **Needs:** fast capture, inventory/refill, gentle reminders, a clean dashboard. Visits a few times a week.

**P3 — "The Caregiver."** Manages medications for a parent or partner alongside their own. Juggles multiple bottles, pharmacies, providers. **Needs:** reliable capture (many label formats), duplicate detection, a clean med list to share with clinicians, cabinet oversight. *(v2 designs single-user; caregiver multi-profile is flagged as a future consideration, not built here.)*

**P4 — "The Optimizer."** Few or no prescriptions; a deep supplement stack. Curious, experimental. Wants to know if supplements actually do anything for them. **Needs:** learning plans, supplement-timing experiments, cross-domain correlations, cabinet/duplicate hygiene.

**P5 — "The Older Adult" (accessibility-forward).** Several daily meds, some vision/dexterity limits. **Needs:** large type, high contrast, simple linear flows, voice logging, forgiving capture, no alarmist tone. Drives the accessibility baseline (§15).

Design priority order: **P1 → P2 → P4 → P5 → P3.**

---

## 3. Core Workflows

The product reduces to a small set of repeated jobs. Everything else is in service of these.

1. **Glance** — "what do I take today, and am I on track?" (Dashboard, §5)
2. **Log** — "I took it / I skipped it" (one tap, anywhere — dashboard, detail, widget, watch, Beth)
3. **Add** — "put this medication/supplement into the system" (Intake Wizard + Guided Capture, §6–§7)
4. **Understand one thing** — "tell me about *this* medication" (Detail, §2/Screen 2)
5. **Understand the whole** — "is my treatment working?" (Treatment Dashboard + Timeline, §8/§12)
6. **Restock** — "what's running low / expired?" (Inventory + Cabinet, §9/§16)
7. **Prepare** — "get me ready for my doctor" (Physician Mode, §10)
8. **Learn** — "does X actually help me?" (Learning Plans, §11)
9. **Discuss** — "talk to me about my meds" (Beth, §13)

Each workflow is reachable in ≤2 taps from the dashboard and is independently valuable.

---

## 4. Screen Inventory

| # | Screen | Job | Entry points |
|---|--------|-----|--------------|
| S1 | Medication Dashboard | Glance + log | Home, Health tab, bottom nav |
| S2 | Medication Detail | Understand one med | Dashboard item, search, Beth |
| S3 | Intake Wizard (hub) | Add (any source) | Dashboard "+", scan, empty state |
| S4 | Guided Capture | Camera capture | Intake Wizard |
| S5 | Confidence Review | Confirm extracted draft | After capture |
| S6 | Treatment Dashboard | Understand the whole | Dashboard "Treatment" tab |
| S7 | Cross-Domain Timeline | Cause & effect | Detail, Treatment, Beth |
| S8 | Inventory / Refills | Restock | Dashboard inventory card |
| S9 | Medicine Cabinet | Cabinet hygiene | Inventory, Health menu |
| S10 | Physician Mode | Prepare for visit | Dashboard, Treatment, Calendar (pre-appointment) |
| S11 | Learning Plans (list + detail) | Learn | Beth, Dashboard, Health |
| S12 | Beth conversation (med-aware) | Discuss | Chat, any "ask Beth" affordance |
| S13 | Empty / Error states | Recover & onboard | Contextual |
| S14 | Settings (meds): reminders, privacy, consent | Configure | Dashboard overflow |

---

## 5. Medication Dashboard (S1)

**Goal:** the one screen a user wants to open every day. It answers "what today, am I on track, anything I should know?" — in that order — and offers one-tap logging.

**Layout (mobile-first, vertical scroll; cards reflow to columns ≥769px):**

1. **Today header** — date, a single calm status line from Beth's composed verdict: *"3 of 5 doses taken. Lantus and metformin still ahead this evening."* No score shouting; a quiet ring or segmented bar shows today's progress. **Visual Truth:** taken segments filled/checked; pending segments outlined/muted; overdue segments get an amber rail badge — never a filled "done" look.

2. **Up next** — the next dose(s) with time + a big one-tap **Take** action. PRN ("as needed") items render as a separate "available if needed" group with no miss-penalty styling. **Take** logs instantly with undo (snackbar), routing through the single adherence authority.

3. **Today's medications & supplements** — two clearly separated groups (meds vs supplements), each row: name, dose, scheduled window, status chip (Taken / Upcoming / Overdue / Skipped). Tap → Detail (S2). Long-press → quick log/skip. **Visual Truth governs every chip.**

4. **Needs attention** (only renders if non-empty) — a short, calm list: running low, refill due, possible duplicate, missed-dose streak, monitoring gap ("A1c is due"). Each is a tappable card with a single clear next step. No red unless genuinely time-sensitive; default to amber/neutral.

5. **Treatment momentum** — one line + a small sparkline trio (adherence, and where relevant the linked biomarker e.g. weight or glucose). Verdict-inside: *"Treatment steady. Adherence 92% this month; weight down 4 lb since your last Mounjaro step-up."* Tap → Treatment Dashboard (S6).

6. **Beth observations** (0–2 max) — the single most useful cross-domain observation, framed for understanding and physician discussion, never as advice: *"Your fasting glucose has run a little higher after short-sleep nights this week — might be worth noting before your visit."* Dismissible; dismissals feed observability.

7. **Quick actions** — Add (camera-first), Refills, Cabinet, Ask Beth, Physician export.

8. **Progress over time** (collapsed by default) — 7/30/90-day adherence and treatment trend; opens fuller charts.

**Tone rules:** zero items overdue → the dashboard celebrates lightly and gets out of the way ("All caught up — nice."). Many items missed → calm and supportive, never a wall of red ("A few got away today. Want to log what you took?").

---

## 6. Medication Detail (S2)

**Goal:** everything a user (or their doctor) would want about one medication, organized so understanding comes before data.

**Header:** name + strength, purpose ("why you take this"), current status (Active / Paused / Discontinued), and the medication's photo if the user opted to retain one (else a clean generic glyph by form: pill, capsule, pen, liquid, inhaler).

**Sections (progressive disclosure; the top third is the 90% case):**

- **At a glance** — current dose, frequency, route/form, SIG (as written), today's status, this-month adherence (one number + meaning).
- **Schedule** — the dosing plan; PRN clearly marked; edit affordance.
- **Dose & treatment timeline** — the **forward-only** history from the change ledger: started, dose changes (↑/↓), pauses, provider/pharmacy changes, discontinuation — each with date and *reason* ("doctor-directed," "side effect," "cost"). Pre-tracking history is labeled honestly: *"Tracking started May 2026 — earlier history not recorded."* This is the spine of "treatments change over time."
- **Adherence** — trend, streaks, missed pattern; framed neutrally.
- **Inventory & refills** — estimated remaining, projected run-out date, refill status, pharmacy, Rx number.
- **Prescriber & pharmacy** — structured provider/pharmacy (reused from existing provider records), tap to call.
- **Observed outcomes (cross-domain)** — the high-value section. Deterministic, evidence-linked observations relating this med to **labs, glucose, weight, meals, workouts, sleep** — each with a small chart and a plain-language verdict, each flagged if "worth discussing with your physician." Never causal language ("because"); always observational ("coincided with," "tended to").
- **Side effects** — user-reported reports (never inferred), with onset dates; "report a side effect" action.
- **Photos & evidence** — bottle/label images if retained (opt-in); extraction provenance.
- **Questions to discuss** — auto-collected, editable talking points seeded from open observations and monitoring gaps; one tap to add to Physician Mode.
- **Beth observations** — this med's narrated verdicts.

**Actions:** Take/Skip, Edit, Pause/Resume, Discontinue (writes a ledger event, never a hard delete), Request refill, Add to physician export, Start a learning plan about this med.

---

## 7. Intake Wizard (S3) + Guided Capture (S4)

**Goal:** adding a medication should feel effortless and *smart* — the system asks only for what it still needs, and always explains **why** it wants another picture. Camera-first, manual always available.

**Entry (S3 hub):** a single "Add" surface offering source paths, camera prominent:
- **Scan a bottle** (prescription or OTC)
- **Scan a prescription label**
- **Scan a supplement** (Supplement Facts)
- **Upload a medication list / pharmacy paperwork / physician list** (photo or PDF)
- **Enter manually**
- **Scan barcode / QR** (fast NDC path)

All paths converge on **Confidence Review (S5)** before anything is saved. Nothing is canonical until confirmed.

**Guided Capture (S4) — confidence-driven, minimal steps.** The system requests the *fewest* images needed and stops as soon as confidence is sufficient. It narrates intent at every step.

```
PRESCRIPTION BOTTLE
 Step 1 — Front of bottle.        "Let's start with the front."
 Step 2 — Prescription label.     "Now the pharmacy label — this has your dose, prescriber, and Rx number."
 → If name + dose + SIG confidence HIGH → skip to Review.
 Step 3 (only if low) — Other side / Drug Facts.
                                  "I couldn't read the directions clearly — one more of the label, please."
 Optional — Barcode/QR if present "Scanning the barcode confirms the exact product (NDC)."

SUPPLEMENT
 Step 1 — Front.                  "Front of the bottle."
 Step 2 — Supplement Facts.       "The Supplement Facts panel — ingredients and serving size."
 Step 3 (only if needed) — Directions.
                                  "The directions, so I can suggest a schedule."

INJECTION PEN (insulin / GLP-1)
 Step 1 — Pen label / carton.     "The pen label or its box."
 Step 2 — Dose/SIG detail.        "How it's dosed — I want to get units right."
 → Routes to insulin handling (basal/bolus subtype) so dose-per-event tracking works.

OTC PACKAGE
 Step 1 — Front.
 Step 2 — Drug Facts panel.
```

**Always-on capture intelligence:**
- **Live framing hints** — "move closer," "reduce glare," "hold steady" — so most captures succeed first try.
- **Why-this-photo microcopy** — every additional request states the reason ("the back has the active ingredients").
- **Confidence-driven stopping** — never ask for a 3rd or 4th image the system doesn't need.
- **Barcode/QR fast path** — if a readable NDC is found, prefill from the lookup service and ask the user only to confirm.
- **Multi-item documents** — a pharmacy printout or physician list yields multiple draft rows; the user reviews them as a checklist.

**Confidence Review (S5):** the heart of "OCR is never truth."
- Each field shows its value **and** a confidence indicator. **Low-confidence fields are left blank and highlighted** — never silently guessed.
- **Prescription vs supplement** is an explicit, forced toggle (defaults to the stricter "medication" until confirmed).
- **Dose/frequency ambiguity** ("take 1–2 as needed") → the verbatim SIG is shown; the user sets the structured value; PRN is offered.
- **Duplicate detection** runs here: if the name/NDC/drug-class matches an active med, a calm banner asks *"Looks like you already track Metformin 500mg — is this the same one (maybe a dose change), or different?"* → routes to "update existing (creates a dose-change event)" vs "add new," never a silent duplicate.
- **Old bottle vs current Rx:** if an active med exists at a different dose, ask *"Is this your current prescription or an older bottle?"* — default to "historical," never overwrite current truth.
- **Confirm** writes through the canonical save path (creates the medication + a "started"/"dose-changed" ledger event). The draft is then inert and auto-expires.

---

## 8. Treatment Dashboard (S6)

**Goal:** elevate from *medications* to *treatment*. Answer "is my treatment working?" at the level of goals and therapies, not pills.

**Layout:**
- **Treatment goals** — user/clinician-defined (e.g., "Lower A1c," "Sustainable weight loss"), each with a calm progress indicator sourced from real biometrics (labs, weight), never invented.
- **Current therapies** — the meds/supplements grouped by the goal/condition they serve (a treatment plan), with per-therapy momentum.
- **What's improving / what's stalled** — two honest columns, evidence-linked: *"Improving: weight (−9 lb / 3 mo). Stalled: morning glucose (flat 4 weeks)."*
- **Historical therapies** — what was tried and stopped, with reasons — the "treatment story."
- **Things to monitor** — due labs, follow-ups, refill horizons.
- **Provider discussion items** — the running list that flows into Physician Mode.
- **Beth observations** — treatment-level narration.

**Tone:** progress is framed as a journey; "stalled" is neutral and forward-looking ("worth a conversation"), never failure.

---

## 9. Inventory Management (S8)

**Goal:** the user never runs out unexpectedly and never over-orders. Beth quietly maintains an estimate.

**Per-item:** estimated remaining (pills/pens/mL), projected run-out date, refill status (refills remaining, last filled), running-low flag, expired flag.

**Inventory card (dashboard):** "2 refills due this week" with one-tap "Request refill" (where supported) or "Mark refilled." Adjusting supply is one tap (e.g., "+30 filled").

**Estimation is honest:** the estimate is derived from dose schedule + logged intake and is labeled an *estimate*; the user can correct it anytime. Low-confidence estimates say so rather than asserting false precision.

**Pens/injectables:** track units-per-pen and pens-remaining; surface run-out in "days at current dose."

---

## 10. Physician Mode (S10)

**Goal:** turn months of tracking into a one-tap, clinician-ready summary that makes the visit better. Surfaces near appointments (calendar-aware: "Endocrinology Tuesday — want to prep?").

**One-tap export contents:**
- Current medications (name, dose, frequency, route/form, start date, prescriber, pharmacy)
- Current supplements
- Recent dose/treatment changes (timeline, with reasons)
- Adherence summary (per med, 7/30/90-day)
- Key trends with **graphs**: glucose, weight, relevant labs over the treatment window
- **Questions for physician** (auto-collected + user-added)
- Treatment observations (flagged "discuss")
- Allergies & conditions (once captured)

**Formats:** an on-screen **print-friendly view** (immediate) and a downloadable **PDF**. FHIR is explicitly out of scope for v2.

**Framing (safety):** every export is clearly labeled *"Self-tracked information to support your conversation — not a medical record,"* and observations are phrased as patterns to discuss, never findings or recommendations.

**Pre-appointment flow:** Beth offers to prep ("3 things stood out this month; want them in your summary?"), assembles the export, and the user walks in ready.

---

## 11. Learning Plans (S11) — *(formerly "Experiment Engine")*

**Goal:** help users learn what works **for their body** — observe, learn, adjust, discuss. Never prescribe. "Learning Plan" is the user-facing name; the framing is curiosity, not clinical trial.

**Experience:**
- **Discover** — Beth proposes plans grounded in the user's data, or the user starts one: pre-ride nutrition, sleep, protein goals, hydration, glucose response, **medication timing**, supplement timing.
- **Set up** — plain-language hypothesis ("Does 20g of carbs before long rides reduce my post-ride lows?"), what we'll watch (auto-captured from canonical sources — glucose, workout), how many times (e.g., "4 rides"), and the trigger ("rides over an hour").
- **Run** — when the trigger happens, the plan auto-captures the metrics and asks only for a quick subjective note ("How did energy feel?"). Progress shows "2 of 4 rides done."
- **Findings** — after the target count, a **deterministic** summary: *"On all 4 carb rides your lowest glucose was higher (avg 78 vs 61). On the days you skipped carbs, you dipped lower."* Beth narrates this; she never invents it.
- **Adjust / Discuss** — close with options: keep testing, try a variation, or "add this to your physician summary." Never "you should do X."

**Card states:** Proposed → Active (with progress) → Complete (with finding) → Archived. Calm, encouraging, journal-like.

---

## 12. Cross-Domain Timeline (S7)

**Goal:** help users *see* cause and effect across their life — the single most differentiating screen.

**Design:** a scrollable vertical timeline (or horizontally zoomable on larger screens) layering, on a shared time axis:
- Medication changes (started/↑/↓/stopped — from the ledger)
- Weight, glucose, key labs (as trend bands)
- Nutrition, exercise, sleep (as activity markers)
- Symptoms / side effects
- Appointments & provider visits
- Journal entries & treatment milestones

**Interaction:** tap any marker for context; pinch/zoom time; filter layers on/off. A "moments that line up" affordance highlights *observed* co-occurrences (e.g., a Lantus reduction marker sitting at the start of a downward weight band) — always observational, evidence-linked, with a "discuss with physician" option. **Never asserts causation.**

**Why it matters:** this is where "how medications interact with the rest of life" becomes visible and intuitive — the visual payoff of WLJ's cross-domain data.

---

## 13. Notifications (§10 of brief)

**Philosophy:** every notification must be *meaningful, timely, and actionable.* WLJ is not a nag. Default to fewer, smarter pings; let the user tune. Group, don't spam. Respect quiet hours.

**Tiers:**
- **Time-sensitive, actionable** (opt-in, user-scheduled): dose reminders (only for meds the user wants reminded about — many won't), low-glucose-pattern safety note. One reminder per window, with one-tap log.
- **Helpful, non-urgent** (batched, digest-friendly): running low / refill due, possible duplicate found after a scan, missed-dose gentle nudge (only after a *pattern*, never a single miss), monitoring due ("A1c is due").
- **Intelligence moments** (rare, high-value): treatment review available, learning plan complete, "questions for your physician" before an appointment, a notable cross-domain observation.

**Anti-fatigue rules:** never two notifications for the same fact; collapse same-window doses into one; suppress reminders for taken/PRN items; a weekly digest can replace many small pings for low-engagement users; one tap to "remind me less." Tone is always supportive, never alarmist — a missed dose is "want to log what you took?", not "YOU MISSED A DOSE."

---

## 14. Beth Interaction Philosophy (§11 of brief)

**Role:** Beth is the Chief of Staff for the user's treatment — she narrates composed, deterministic understanding and helps the user act and prepare. She reads structured state and rendered observations only (never raw OCR, raw logs, or raw meals).

**What Beth does:**
- **Medication review** — "Here's where each of your meds stands."
- **Treatment review** — "Is treatment working?" answered with momentum + evidence.
- **Weekly / monthly summaries** — calm rollups; what improved, what to watch, what to discuss.
- **Physician prep** — assembles questions and the export before appointments.
- **Learning plans** — proposes, runs, and reports findings.
- **Cross-domain observations** — glucose/exercise/nutrition/sleep relationships, always observational.
- **Missed doses** — supportive, curious ("anything change this week?"), never judgmental.

**Conversation tone:** warm, concise, confident-but-humble. Leads with meaning, offers a next step, respects autonomy. Celebrates real wins; normalizes setbacks.

**Hard boundaries (always):** Beth **never** diagnoses, prescribes, recommends a dose change, interprets labs as clinical findings, or contradicts a physician. When asked to cross a line, she declines warmly and redirects: *"I can't advise on dose changes — that's your doctor's call. But I can pull together what your glucose and weight have done since your last change so you can ask them about it."* Possible interactions/duplicates are surfaced as *"worth checking with your pharmacist,"* never as clinical assertions.

---

## 15. Accessibility (§13 of brief)

Baseline, not an afterthought — driven by persona P5.

- **Large type & scaling** — respects OS dynamic type; layouts reflow without truncation; no fixed-height text containers.
- **Contrast & color-independence** — status never conveyed by color alone; every chip has a label/icon (Taken ✓, Overdue ⏰). Meets WCAG AA contrast. Color-blind-safe palette (no red/green-only distinctions).
- **Touch targets** — ≥44×44px everywhere; primary actions large and reachable one-handed.
- **Voice** — log by voice ("I took my Lantus"), and ask Beth by voice; capture flow speaks its prompts for low-vision users.
- **Simple linear flows** — capture and logging never require precise gestures; everything has a plain-tap path.
- **Screen-reader support** — semantic labels, ordered focus, image alt text, announced state changes.
- **Forgiving capture** — generous framing tolerance; manual entry always one tap away if the camera is hard to use.
- **No alarmist motion/sound** — gentle, optional haptics; no flashing.

---

## 16. Empty & Error States (§14, §15 of brief)

**Empty states teach the next step (never a blank wall):**
- **No medications** — friendly hero: "Let's add your first medication — snap a bottle and I'll do the rest." Camera-first CTA + manual.
- **No supplements** — "Track supplements too — I can read the Supplement Facts for you."
- **No history yet** — "Your treatment timeline starts now. As things change, I'll keep the story." (sets the forward-only expectation honestly).
- **No scans** — explains the camera benefit + privacy ("I read the label; I don't keep the photo unless you ask").
- **No provider / no treatment plan** — optional, low-pressure: "Add your prescriber to make doctor visits easier — totally optional."
- **No adherence data** — "Log a few doses and I'll start showing your patterns."

**Error states are always recoverable, never dead ends:**
- **Low OCR confidence** — "I caught most of it but couldn't read the dose. Want to retake that side, or type it in?" (offers both; never guesses).
- **Duplicate medication** — the calm same-or-different banner (§7), not an error.
- **Conflicting directions** — show both readings, ask the user to pick, keep verbatim SIG.
- **Unreadable label** — "That one's tough to read — try more light or less glare, or enter it manually." Live tips.
- **Missing information** — save what's confirmed, mark the rest "needs detail," let the user finish later (no all-or-nothing).
- **Unknown supplement** — "I don't recognize this one — let's capture what's on the label and you can confirm." Falls back to manual fields.
- **Expired medication** — neutral flag + gentle suggestion to review with pharmacist; never alarmist.

---

## 17. Mobile Experience (§12 of brief)

WLJ is mobile-first (iOS Swift/SwiftUI wrapper + HealthKit). Medication Intelligence must be excellent in-hand.

- **Quick logging** — take/skip from dashboard, notification, widget, or watch in one tap, with undo.
- **Camera-first add** — the "+" opens guided capture immediately; the whole add flow is thumb-reachable.
- **One-handed design** — primary actions in the lower third; no critical control at the top edge.
- **Fast review** — Confidence Review optimized for thumb scanning: big confirm, easy field-by-field fix.
- **Widgets** — a home-screen widget showing "next dose" + today's progress (Visual-Truth-correct); tap to log.
- **Lock-screen / Live Activity** — next-dose reminder with a log action without unlocking into the app.
- **Apple Watch** — glanceable "next dose," tap-to-log, and "low/refill" complications; raise-to-log.
- **Offline support** — logging and capture queue offline and sync when back online; the user is never blocked by connectivity (extraction may defer with a clear "I'll read this when you're back online").
- **HealthKit harmony** — respects existing health-data sync; no double-entry where HealthKit already provides data.

---

## 18. Product Differentiation (§17 of brief)

Researched against the named competitors. **WLJ does not compete on reminders — it competes on intelligence and integration.**

| Capability | Medisafe / MyTherapy / CareClinic | Apple Health meds | **WLJ Medication Intelligence** |
|---|---|---|---|
| Reminders & logging | ✅ (their core) | ✅ basic | ✅ (table stakes, not the pitch) |
| Adherence tracking | ✅ | partial | ✅ single-source-of-truth, honest |
| **Treatment momentum** ("is it working?") | ❌ | ❌ | ✅ verdict + evidence |
| **Cross-domain observations** (meds ↔ glucose/weight/sleep/labs/exercise) | ❌ | ❌ | ✅ deterministic, evidence-linked |
| **Forward-only treatment timeline** with reasons | partial (logs) | ❌ | ✅ change ledger + cross-domain layers |
| **Learning Plans** (personal n-of-1 discovery) | ❌ | ❌ | ✅ observe→learn→adjust→discuss |
| **Physician Mode** (clinician-ready, one tap) | partial (lists) | partial | ✅ summary + trends + questions + PDF |
| **Chief-of-Staff narration** (a companion, not a log) | ❌ | ❌ | ✅ Beth, within safe boundaries |
| **Cabinet intelligence** (expiry, duplicates, health score) | partial | ❌ | ✅ whole-cabinet view |
| Lives inside a **whole-life** platform | ❌ (meds-only silos) | partial | ✅ glucose, weight, labs, fitness, journal, faith |

**The one-line pitch:** *Other apps remind you to take your medicine. WLJ helps you understand whether your treatment is working — and gets you ready to talk to your doctor about it.* The moat is the **cross-domain data WLJ already owns** (glucose, weight, labs, fitness, sleep, nutrition) plus a Chief of Staff that turns it into understanding — something a standalone medication tracker structurally cannot do.

---

## 19. Medicine Cabinet (§16 of brief)

**Goal:** a digital home medicine cabinet — Beth understands not just the active regimen but *everything in the house.* This is a distinct, delightful feature beyond the dashboard.

**Experience:**
- **The shelf** — a visual cabinet of all products (active meds, supplements, OTCs, PRN-only), grouped by shelf (Daily meds / Supplements / As-needed / Inactive).
- **Cabinet health score** — a single gentle indicator of cabinet hygiene (nothing expired, no duplicates, nothing forgotten), with a friendly breakdown — never a scolding grade.
- **Expired** — clearly flagged, with a calm "review with your pharmacist / safe-disposal" note.
- **Unused / dormant** — meds with no recent logs ("haven't logged this in 60 days — still taking it?"). Helps prune the list honestly.
- **Duplicates** — same-ingredient supplements or same-class meds surfaced for review ("two products with magnesium — worth checking you're not doubling up").
- **Inventory trends** — what's running low across the whole cabinet; batch refill.
- **Add to cabinet** — same guided capture; OTCs and PRN items welcome, not just daily prescriptions.

**Tone:** organized, calm, slightly satisfying — like tidying a real cabinet. Useful for P3 (caregiver) and P4 (optimizer) especially. Never alarmist about expiry or duplicates; always "worth a look," with the pharmacist as the safe escalation.

---

## 20. Recommended Implementation Order (§19 of brief)

Sequenced for early daily value, then depth — mapped to the Phase 2 engineering phases (this is *product* priority, not new architecture).

1. **Dashboard + one-tap logging + Detail (S1, S2)** — the daily-use core; immediate value on existing data. *(Eng: stabilization + read surfaces.)*
2. **Intake Wizard + Guided Capture + Confidence Review (S3–S5)** — make adding effortless and trustworthy; the acquisition moment. *(Eng: image-first phase.)*
3. **Inventory + Refills (S8)** — high practical value, low complexity; reduces real-world pain fast.
4. **Treatment Dashboard + Cross-Domain Timeline (S6, S7)** — the "is it working?" payoff; WLJ's differentiation becomes visible. *(Eng: intelligence + state contract.)*
5. **Beth med-aware conversations (S12)** — narration over the now-rich state; weekly/monthly reviews. *(Eng: Beth intelligence.)*
6. **Physician Mode (S10)** — converts tracking into clinical value; strong retention/word-of-mouth. *(Eng: physician export.)*
7. **Learning Plans (S11)** — flagship delight for engaged users. *(Eng: Learning Plans phase — internal models `IntakeExperiment`/`ExperimentObservation`.)*
8. **Medicine Cabinet (S9)** — whole-home completeness; broadens beyond the daily regimen.
9. **Notifications, Widgets, Watch, Offline polish (§13, §17)** — woven through every phase, hardened last.
10. **Accessibility & empty/error states (§15, §16)** — designed in from step 1, audited as a gate before each release.

**Guiding sequence principle:** ship something a user opens *every day* first (Dashboard), make *adding* delightful second (Capture), then layer *intelligence* (Treatment, Timeline, Beth), then *clinical value* (Physician Mode) and *delight* (Learning Plans, Cabinet). Accessibility and calm, non-alarmist tone are present from day one — they are the product, not a finish.

---

*End of Phase 3. Pure product/UX specification — no code, no migrations, no models, no architecture redesign. Awaiting the canonical reference images to validate the guided-capture decision tree (§7), and explicit instruction before any build.*
