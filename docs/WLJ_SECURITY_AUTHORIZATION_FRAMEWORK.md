# WLJ Security & Authorization Framework

**Status:** **RATIFIED — governing architecture** (2026-07-18). **Rev 2.** This is the approved architectural direction for WLJ authorization. It is **architecture only**: ratification changes **no** production authorization, introduces **no** permissions, creates **no** migrations, and begins **no** implementation. Implementation is a separate, later initiative gated on its own approval.
**Kind:** Foundational governing document — a peer of the CoS Constitution, the LLM Truth/Action Contract, the Current Context Contract, the Layer 1 Domain Framework, and the Operations Vision. Any subsequent authorization/identity/sharing/admin/AI-authority work conforms to this document or amends it deliberately.
**Governing primitives (ratified):** **Identity · Space · Capability · Ownership · Delegation · Trust.** Authorization is decided by a single deterministic **Policy Decision Point (PDP)**. Roles are bundles of capabilities. AI is a derived principal that never self-authorizes. Platform authority is completely separate from data ownership, and **the Platform is not a Space.**
**Constitutional status:** Fits **entirely within the existing Constitution**; **no Constitutional Review required** and **none performed.** The optional *Article VI* (§14) is **NOT** created and **NOT** elevated — it remains future discussion only.
**Rev 2 note:** Elevates **Space** to a first-class primitive (supersedes the "tenant" framing; resolves multi-space validation findings R1–R5 at the primitive level).

> One-line thesis: **Every resource, owner, capability, and grant in WLJ lives inside a *Space* — the canonical container (Personal, Household, Family, Organization, Church, Coaching Practice, …). Authorization is decided on *capabilities granted within a Space*, by a single deterministic authority, across two orthogonal planes: the *Space plane* (authority *inside* a space — whose life/household/org is this?) and the *Platform plane* (authority to *operate WLJ itself*, the substrate that hosts all spaces). A principal participates in many spaces; roles are named bundles of capabilities; the Chief of Staff never self-authorizes and never exceeds the human it acts for — within the space it is acting in.**

---

## 0. Why this document exists (and why not roles)

Today WLJ has **one boolean of privilege.** `is_staff` (occasionally `is_superuser`) is checked in ~90+ places through two idioms — a `UserPassesTestMixin.test_func` and inline `if not request.user.is_staff` guards — with three *separate* definitions of `AdminRequiredMixin`. Tenant isolation is done entirely by user-scoped querysets (`UserOwnedModel` + `SoftDeleteManager` + `.filter(user=request.user)`). Two bespoke API keys (`X-Claude-API-Key`, `X-Gmail-Sync-API-Key`) stand in for service identities. The Django permissions framework is present but dormant (a single real `has_perm`). Audit is siloed across `AdminActivityLog`, `SecurityAuditLog`, and `APIRequestLog`, inconsistent on *who*. There is no impersonation and no user-to-user sharing.

That is a fine posture for a near-single-user product. It will **not** survive the personas WLJ is heading toward: platform administrators, operations personnel, family sharing, trusted delegates, healthcare providers, coaches, financial advisors, churches, AI agents, and personas not yet imagined. `is_staff` conflates "I am an operator" with "I may do anything," and every new distinction would fork the ~90 call sites again.

**We do not begin with roles.** Roles (`Admin`, `Operations`, `Super Admin`) are the *output* of the model, not its foundation. We begin with the primitives that stay stable for a decade: **spaces, identities, capabilities, ownership, delegation, and trust relationships.** A role is then simply a *named bundle of capabilities granted within a space* — data, not a code branch. Adding a persona, or a whole new *kind of space*, becomes adding data, never touching an enforcement site.

And we do not begin with *tenants*. "Tenant" is infrastructure vocabulary. WLJ's canonical container is the **Space** — a product concept a customer understands (my personal space, our household, our church) — which happens to give WLJ clean multi-space isolation for free. Single-user WLJ is not a special case bolted on later: it is simply **one Personal Space per person**.

---

## 0A. The Space primitive (canonical container)

**A Space is the container within which ownership, resources, capabilities, delegation, trust, and every authorization decision are evaluated.** It is the first primitive; everything else is defined *relative to a space*.

**Invariants.**
- **Every resource belongs to exactly one Space.** (Sharing exposes a resource *across* spaces without moving it — §7.)
- **Ownership belongs to a Space**, not directly to a person. A Space *has an owner* (the person or org that owns the container); resources are owned *by the Space*.
- **Capabilities are granted *within* a Space.** A grant is always "capability X, in Space S." There is no space-less data authority.
- **A principal participates in one or more Spaces** via **Membership** (§3.1). One identity, many memberships, many spaces — held simultaneously.
- **Every person has, from creation, exactly one Personal Space** they own and are the sole member of. This is the single-user product today; it needs no "tenant" concept and no migration to exist.
- **The Platform is *not* a Space.** Operating WLJ itself (the substrate hosting all spaces) is the Platform plane (§2.2) and is deliberately outside the Space model — this is what keeps vendor-operator authority from ever implying access to any space's data.

**Space kinds (open set — new kinds are data, not code):**

| Space kind | Owner | Typical members | Example resources |
|---|---|---|---|
| **Personal** | one person | that person (sole) | their journal, health, finance, faith, goals |
| **Household** | a household | cohabiting members | shared meals/pantry, calendar, budgets |
| **Family** | a family unit | spouses, parents, children (age-scoped) | shared milestones, family calendar, guardianship data |
| **Organization** | an org/business | staff with org roles | org records, team data, business config |
| **Church** | a church | clergy, staff, members | congregation data, groups, shared faith content |
| **Coaching Practice** | a practice/coach | coaches + (via shares) clients | client rosters, plans, session notes |
| **Future kinds** | whatever owns it | whoever joins | whatever it contains |

**Why Space (not tenant) is the right primitive.**
- **Product-centric.** A customer never sees "tenant." They see *their space* and *spaces they belong to*. The container is a feature, not plumbing.
- **Uniform.** Personal / household / org are the *same primitive* with different owner kinds and membership rules — one model, not three. (The Meal Intelligence domain already scopes *supply* to a household while *consumption* stays personal — a real precedent for space-scoped ownership.)
- **Isolation for free.** Because a resource belongs to a space and grants are per-space, cross-space leakage is structurally impossible unless a share explicitly permits it.
- **Single-user stays simple.** One person = one Personal Space, one membership, sole owner. Zero extra concepts surface. Multi-space is purely additive (join a household, be granted into a practice).

**This elevation supersedes the "tenant" framing** used in the earlier multi-space validation and **resolves validation findings R1–R5 at the primitive level**: R1 (name the container) = Space; R2 (one identity, many scoped grants) = one identity, many Memberships; R3 (acting-space context) = §3.2 via Current Context; R4 (audit dimension) = Space is a first-class audit field; R5 (grantor for org-owned data) = a member holding the space-scoped `space.share` capability.

### 0A.1 Conceptual model vs. physical implementation (a ratified guard)

Space is the **architectural truth** of ownership. This must not erode into "we'll just keep using `user_id`."

- **Conceptual model (ratified, true now):** *every* current user-owned resource **belongs to that user's Personal Space.** There is no user-owned data that is not, conceptually, space-owned. This is true today, before any Space table exists.
- **Physical implementation (later, at implementation time):** explicit `Space` records and `resource → space` relationships are introduced during the implementation initiative. Until then, a resource's existing `user`/`owner` FK is the *physical stand-in* for "belongs to this person's Personal Space."

**The guard:** `user_id` (or `owner`) is a **temporary physical representation of Personal-Space ownership, never the permanent ownership model.** Implementation MUST NOT conclude "one Personal Space, so `user_id` is enough" and stop there — that would silently re-entrench the exact single-owner assumption this architecture retires. The PDP resolves authorization **by Space** from day one (even when Space is derived from `user_id`), so every enforcement site is already asking the space-shaped question; materializing `Space` records later changes storage, not the model or any call site. When implementation begins, its Phase-0/2 acceptance explicitly includes "ownership is expressed as Space, with `user_id` only a derivation" — a first-class exit criterion, not an afterthought.

---

## 1. Security philosophy (the governing principles)

1. **Capability-based, not role-based.** Authorization decisions are made on fine-grained *capabilities* (`operations.execute`, `users.manage`, `data.read`). Roles are convenience bundles that resolve to capabilities. No enforcement code ever asks "what role is this?" — only "does this principal hold this capability for this resource?"
2. **Single Authorization Authority (one PDP).** Exactly one deterministic component decides every authorization question: the **Policy Decision Point** — `authz.can(principal, capability, resource, context) → Decision`. Every surface *consumes* it; nothing re-implements permission logic. This is Constitutional Article III (single deterministic authority) applied to authorization.
3. **Deny by default; explicit authorization.** Absence of a grant is denial. Nothing is permitted implicitly. New capabilities are unreachable until explicitly granted.
4. **Least privilege.** Principals hold the *minimum* capabilities for their function. `Admin` is not `Super Admin`. Operations is not user management. A service account holds only its narrow set.
5. **Everything is evaluated within a Space.** The Space is the canonical container; ownership, capabilities, delegation, and every authorization decision are relative to a space (§0A). "Space-less" data authority does not exist.
6. **Two orthogonal planes.** The **Space plane** ("what may this principal do *within* this space?") and the **Platform plane** ("who may operate WLJ itself, the substrate hosting all spaces?") are *independent* axes. A human may be a member of several spaces *and* hold platform-operator capabilities; these never leak into each other, and platform authority never implies membership in any customer space. This is the single most important structural decision in the document, and the one thing today's `is_staff` gets wrong.
7. **Defense in depth.** Isolation is enforced at multiple layers that each fail closed: authentication (identity), the PDP (capability), space-scoped querysets (data), step-up auth for sensitive capabilities, and append-only audit. A bug in one layer does not open the door.
8. **Deterministic authority, never reasoning.** Authorization is a deterministic, reproducible, auditable decision. The conversational model's confidence or reasoning is **never** an input to an authorization decision (Constitutional Article I.2/I.7). The model may *propose*; the PDP *decides*.
9. **Product-first invisibility.** Normal users must never perceive that a platform-admin/operations plane exists — nor, in a single-space experience, that "spaces" exist at all. The platform plane is absent from their experience; their WLJ is entirely about their own life. Spaces surface only when a person actually joins or is granted into a second one.
10. **No duplicated permission logic.** One registry of capabilities, one PDP, one audit spine. Reuse before rebuilding (Article IV.3). A CI contract forbids direct `is_staff`/`is_superuser` checks once the PDP lands.

---

## 2. Authorization architecture

A standard, battle-tested shape (PDP/PEP), specialized to WLJ.

### 2.1 The components

| Component | What it is | WLJ form |
|---|---|---|
| **Principal** | The identity acting in a request | A `User`, a `ServiceAccount`, or a *derived* `AI-on-behalf-of` principal (§3). Authentication resolves the principal. |
| **Capability** | A fine-grained, namespaced permission | `<domain>.<action>[.<qualifier>]`, declared once in the **Capability Registry** (§4). |
| **Space** | The canonical container for ownership, resources, and grants (§0A) | Personal / Household / Family / Organization / Church / Coaching Practice / future. Every resource belongs to one. |
| **Membership** | A principal's participation in a Space | `(principal, space, member-role)`. One identity → many memberships → many spaces (§3.1). |
| **Grant** | A binding of capabilities to a principal **within a Space**, optionally further scoped/conditioned/time-boxed | `(principal, capability, space, [resource-scope], conditions, expiry, grantor, revocable)`. Grants are *data*. A grant is always *in a space* (the Platform plane's "space" is the platform substrate itself). |
| **Role bundle** | A named set of capabilities | Convenience only; expands to capabilities at grant time (§5). |
| **PDP** (Policy Decision Point) | The single deterministic authority | `authz.can(principal, capability, resource=None, context=None) → Decision{permit, reason, obligations}`. Pure, deterministic, request-path-safe, always auditable. |
| **PEP** (Policy Enforcement Point) | The thin gate at each surface that *calls* the PDP | A view mixin, an API authenticator, a template tag, the AI action-path gate. A PEP contains **no** policy — only "ask the PDP, then allow or 403/redirect." |

### 2.2 The two planes

```
                         ┌───────────────────────────────────────┐
                         │        Policy Decision Point           │
   principal  ──────────▶│  authz.can(principal, capability,      │──▶ Permit / Deny (+reason, +obligations)
   capability            │            resource, context)          │        │
   resource ─(→ Space)──▶│                                        │        └──▶ Audit (always, incl. Space)
   context (space, MFA)  └───────────────────────────────────────┘
                                     ▲                 ▲
                          ┌──────────┘                 └──────────┐
                    SPACE PLANE                           PLATFORM PLANE
      "What may this principal do WITHIN         "May this principal operate WLJ —
       this Space — read/write/administer?"       the substrate hosting ALL spaces?"
      Grants: membership + capabilities in S      Grants: platform role bundles
      Resolved by the resource's Space            Bound to NO space (not in any space)
```

- **Space plane.** The default answer for a principal with no membership/grant in a resource's Space is *deny*. Within a space, capabilities range from a personal owner's full `data.*` to a coach's read-only share to a church admin's `space.manage_members`. Access is *extended across spaces* — never reduced — by **share/delegation grants** (§7). Enforced both by the PDP (a `data.*` capability requires a grant *in the resource's space*) *and* by space-scoped querysets (defense in depth). For today's single Personal Space this formalizes and hardens `UserOwnedModel` with zero behavior change.
- **Platform plane.** Capabilities like `operations.*`, `users.*`, `security.*`, `secrets.*`, `audit.view`, `ai.configure`, `featureflags.manage` are granted *outside every space* — they operate the substrate, not any space's contents. This is where `is_staff`/`is_superuser` are replaced by explicit, least-privilege bundles. **A platform-plane grant confers no membership in, and no data access to, any space.** Reaching a specific space's life data is a *separate* decision even a Super Admin makes only through an auditable, owner-notified, time-boxed break-glass membership (§7.4, §9). This is exactly the vendor-cannot-read-customer-data boundary multi-space (and enterprise/healthcare) requires — present from day one.

> **Tenant-administration is Space-plane, not Platform-plane.** A coaching-practice owner or church admin manages *their* space via space-scoped capabilities (`space.manage_members`, `space.configure`). They are **not** WLJ operators. Never file space administration into the Platform plane — that conflation is the one modeling error that would force a redesign, and Space-as-primitive makes it impossible to make by accident.

### 2.3 The decision, deterministically

`authz.can` evaluates, in order, failing closed at each step:

1. **Resolve principal** (from the authenticated request or service credential).
2. **Resolve the resource's Space** (every resource belongs to exactly one) — or, for an un-scoped/creation action, the **acting Space** from Current Context (§3.2). Platform-plane capabilities resolve against the platform substrate, not a space.
3. **Collect active grants** for the principal *in that Space* (cached per request/session; O(1) capability-set membership — request-path-safe, no heavy compute).
4. **Capability match**: does any grant confer the requested capability?
5. **Scope match**: does a grant confer this capability *in this Space* (and, if the grant is resource-scoped, over this resource)? A share grant from another space is evaluated here as "grantee holds capability C in space S over scope X." For platform-plane, is the platform scope satisfied?
6. **Conditions**: are the grant's conditions met *now* — MFA/WebAuthn satisfied for the capability's sensitivity tier, time window, IP posture, required approval present, break-glass active?
7. **Obligations**: emit obligations the PEP must honor (e.g., "record reason," "notify owner," "step-up before proceeding").
8. **Decision + audit**: return Permit/Deny with a machine reason; **every** call is auditable (all denies and all elevated permits are logged), stamped with the resolved **Space**.

The decision is a *pure function of stored grants + resolved space + request context*. It never consults the model, never guesses, and is reproducible for audit.

---

## 3. Identity model (principals)

Identity (authentication — *who are you*) is **orthogonal** to authorization (grants — *what may you do*). The canonical model is **one identity, many memberships**: a human authenticates as a single principal (their account) and holds a *set of grants, each within a Space* (their Personal Space, a Household they joined, a Coaching Practice they were granted into) plus, separately, any Platform-plane grants. "Acting as an Operator" is not becoming a different principal — it is *exercising platform-plane capabilities*. This one-identity/many-memberships shape (not principal-switching) is what keeps capability resolution deterministic across many spaces, and it is the fix for `is_staff` conflation.

The table below lists **identity archetypes** — recognizable bundles of capabilities *across spaces and the platform plane* — not separate login accounts.

| Identity | Definition | Default authority | Notes |
|---|---|---|---|
| **Normal User** | A person living their life in WLJ | Full `data.*` on **their own** resources; **zero** platform capabilities | Must never perceive the platform plane exists. The overwhelming majority of principals. |
| **Operations** | Holder of platform operations capabilities | `operations.view`, guarded `operations.execute`, `audit.view` (ops scope) | Often the *same human* as a Normal User, but a *separate* grant set. No user-data access, no user management, no secrets. |
| **Administrator** | Manages the product | `users.view`, scoped `users.manage`, `content.manage`, `featureflags.manage`, product-scoped `config.manage`, `billing.manage` | Explicitly **not** unrestricted. No `security.manage`/`secrets.manage`/`infra.manage`/`breakglass`. |
| **Security Administrator** | Manages security posture | `security.manage`, full `audit.view`, guarded `ai.configure` (guardrails) | Separation of duties: distinct from product Admin so no single admin holds both product and security authority. |
| **Super Administrator** | Unrestricted platform visibility + break-glass | **All** capabilities, including `secrets.manage`, `infra.manage`, `db.maintain`, `breakglass.invoke` | Deliberately different from Admin (§ below). Smallest possible population; hardware-key MFA; the most destructive capabilities require two-person control. |
| **Service Account** | Non-human backend principal | Narrow, explicit capability set per service (e.g. `tasks.read`/`tasks.update` for the Claude Code integration; `intelligence.compute`, `notifications.send` for workers) | First-class principal with credentials + scoped capabilities + audit. Replaces today's bare `X-Claude-API-Key` / `X-Gmail-Sync-API-Key`. No interactive login, no platform-admin capabilities. |
| **AI Agent (CoS on-behalf-of)** | A *derived* principal: the Chief of Staff acting for a specific human | `(that human's capabilities) ∩ AI-allowlist − AI-denylist` — **never exceeds** the human; **never** holds platform capabilities | See §8. The single most important identity constraint in the framework. |
| **Delegate / Trusted Party** *(future)* | A human granted scoped access to *another* user's data | Their own `data.*` on self, **plus** share grants over another owner's scope | Spouse, parent, child, coach, provider, financial advisor, church admin. Expressed purely as share grants (§7). |
| **Future identities** | Partner integrations, organizational/church admins, community roles, etc. | Whatever bundle is defined | The model is open: identity = principal + attributes + grants. New personas need no enforcement changes. |

**The list is explicitly non-exhaustive.** Because identity is "a principal with memberships and grants," new identities are additive.

### 3.1 Membership — the principal ↔ Space binding

A **Membership** binds a principal to a Space and carries that principal's grants *within* it. One identity holds many memberships simultaneously — e.g. one human at once: owner of their Personal Space, a member of a Household, a coach in a Coaching Practice (with client shares), and — on the *separate* Platform plane — an Operator. Each membership's grants are independent; nothing leaks between spaces or into the platform plane. A **Delegate/Trusted Party** is simply a principal holding a membership (or a share, §7) in *someone else's* space. This makes "can one identity belong to multiple spaces / own multiple spaces / hold many trust relationships at once?" answerable with a flat *yes* — they are all memberships and grants.

### 3.2 Acting Space — Current Context for authorization

Data reads/writes resolve their space from the *resource*. But creation and un-scoped actions ("add a record," "start a plan") need to know *which space they happen in*. The **acting Space** is that answer, and it is resolved the WLJ way: **server-side, from Current Context (Constitutional Article II)** — the page/session deterministically declares the active space; scraped DOM is never trusted (II.1). For a person with a single Personal Space this is invisible and automatic. When a person belongs to several spaces, the active space is an explicit, deterministic part of request context — the multi-space generalization of Current Context, not a new authority.

### Super Admin vs Admin (intentional asymmetry)

- **Administrator** manages *the product*: users, content, configuration, operations enablement, feature management, billing. An Administrator must **not** automatically receive unrestricted platform authority.
- **Super Administrator** has *unrestricted platform visibility and control*: platform configuration, security, authentication, secrets, AI provider/model configuration, infrastructure, database maintenance, emergency (break-glass) access, platform diagnostics, and system-wide audit. **Nothing is hidden.** This power is contained by: minimal population, hardware-backed MFA, two-person control on the most destructive capabilities, break-glass semantics (time-boxed, notified, mandatory post-hoc review), and **immutable** audit that even Super Admin can read but never alter.

---

## 4. Capability model

### 4.1 Shape

Capabilities are namespaced verbs: **`<domain>.<action>[.<qualifier>]`**. They are declared **once** in a central, versioned **Capability Registry** (deterministic data; nothing invented inline in a view).

**Platform-plane (illustrative, non-exhaustive):**
`operations.view`, `operations.execute`, `operations.configure`,
`users.view`, `users.manage`, `impersonation.request`, `impersonation.execute`,
`security.manage`, `secrets.manage`, `audit.view`, `audit.export`,
`ai.configure`, `ai.provider.manage`, `featureflags.manage`, `config.manage`,
`billing.manage`, `content.manage`, `infra.manage`, `db.maintain`, `breakglass.invoke`.

**Data-plane (always evaluated *with* a resource/owner scope):**
`data.read`, `data.write`, `data.share`, `data.delete`, `data.export` — optionally qualified by domain (`data.read:health`, `data.write:finance`).

### 4.2 Capability attributes

Each registered capability carries deterministic metadata that the PDP enforces:

| Attribute | Meaning |
|---|---|
| **sensitivity** | `low` / `elevated` / `critical` — drives step-up and audit requirements. |
| **step_up** | Requires fresh strong auth (WebAuthn/MFA within N minutes) before use. (Generalizes today's `AdminOverrideConfirmationMixin`.) |
| **requires_approval** | Two-person control: a second authorized principal must approve. |
| **requires_reason** | The actor must record a justification (audited). |
| **audit** | `always` for all platform + sensitive-data capabilities. |
| **ai_eligibility** | `ai_allowed` / `ai_confirm` (allowed with user confirmation) / `ai_never` (structurally denied to any AI principal). |
| **break_glass_only** | Reachable only through an active break-glass grant. |

### 4.3 Why capabilities (not roles) at the core

Because the *enforcement* code only ever asks `authz.can(principal, "operations.execute", …)`, adding a new persona, splitting Admin into Support-Admin vs Config-Admin, or granting a coach limited write access are all **grant/registry data changes** — never edits to enforcement sites. Roles emerge as bundles; the model never hardcodes them.

---

## 5. Recommended role bundles

Roles are **named capability bundles** (config/data, versioned), each belonging to a **plane**. Representative starting set:

| Bundle | Plane | Capabilities (illustrative) | Explicitly excludes |
|---|---|---|---|
| **Space Owner** | Space | `data.*`, `space.configure`, `space.manage_members`, `space.share` — *within the owned space* | anything in other spaces; all platform capabilities |
| **Space Member** | Space | scoped `data.read`/`data.write` within the space, per member-role | space administration; other spaces; platform |
| **Space Admin** *(household/org/church/practice)* | Space | `space.manage_members`, `space.configure`, `space.share`, scoped `data.*` — *within that one space* | **not** a WLJ operator; no platform capabilities; no other space |
| **Operations** | Platform | `operations.view`, `operations.execute`*, `audit.view:ops` | `users.manage`, `secrets.*`, `security.manage`, any space membership |
| **Support Admin** | Platform | `users.view`, `users.manage:limited`, `impersonation.request`, `content.manage` | `security.*`, `secrets.*`, `infra.*`, `breakglass`, space data |
| **Administrator** | Platform | Support Admin + `featureflags.manage`, `config.manage:product`, `billing.manage` | `security.manage`, `secrets.manage`, `infra.manage`, `db.maintain`, `breakglass` |
| **Security Admin** | Platform | `security.manage`, `audit.view:all`, `audit.export`, `ai.configure:guardrails` | product `config.manage`, `billing.manage` (separation of duties) |
| **Super Administrator** | Platform | **all** platform capabilities + `secrets.manage`, `infra.manage`, `db.maintain`, `breakglass.invoke` | (no *ambient* space membership — space data only via break-glass) |
| **Service Account (per service)** | Platform/space-scoped | only that service's set (e.g. `tasks.read`, `tasks.update`) | interactive/platform-admin capabilities |

\* `operations.execute` is itself tiered — recovery/execute actions on the Ops Wall are `elevated` (step-up), the most destructive are `critical` (approval).

The **Space bundles** (Owner/Member/Admin) are the "normal user" world at every scale — a solo person is a Space Owner of one Personal Space; a church admin is a Space Admin of a Church Space. Crucially, **every Space bundle is a Platform-plane *non-entity*** and vice-versa. Bundles are **starting points**, tunable without code change. The authority is always the underlying capabilities, never the bundle name.

---

## 6. Ownership model

**Ownership belongs to a Space, not directly to a person.** A resource is owned *by the Space it lives in*; a Space in turn *has an owner* (the person or org). "Personal ownership" is simply "owned by a Personal Space whose owner is that person." This one move makes personal / household / org ownership the *same* primitive with different Space kinds — no separate ownership systems to reconcile. Enforced at the query layer (space-scoped querysets) *and* the PDP.

| Ownership form | Owning Space (kind) | Default access | Basis today |
|---|---|---|---|
| **Personal data** | a **Personal Space** (owner = one person) | the space's owner/member (+ AI-on-behalf, §8) | `UserOwnedModel.user` today == "belongs to my Personal Space" |
| **Household / family / shared data** | a **Household/Family Space** | space members, per their grants | precedent: Meal Intelligence *supply* is already household-scoped |
| **Organization / church / practice data** | an **Organization/Church/Coaching Space** | space members, per space-role grants | greenfield (space kinds) |
| **Delegated data** | still the original Space | space members **+** grantees with a live cross-space share (§7) | greenfield |
| **System / platform data** | *not a space* — the platform substrate | platform-plane capabilities only (`config.manage`, `secrets.manage`) | settings, feature flags, model config, secrets |
| **Operations truth** | *not a space* — a Platform-plane Layer 1 truth domain | read via `operations.view`, act via `operations.execute` | Ops Wall / recovery / telemetry — never owned by any space |
| **Audit truth** | *not a space* — the platform, **append-only** | read via `audit.view`; **mutation/deletion by no one** (not even Super Admin) | to be unified (§9) |

**Invariants.**
- A resource belongs to **exactly one Space**; ownership grants access, and **shares only ever *add* cross-space access, never remove** the owning space's.
- **A platform-plane grant confers no membership in, and no data access to, any Space.** An Administrator managing users does not thereby read a user's journal; reaching a space's data requires a share/membership from within that space, or an audited, owner-notified break-glass.
- The Platform, Operations truth, and Audit truth deliberately live **outside** the Space model — they are the substrate, not contents of any space.
- **Audit truth is immutable to all principals.** Read-only even to Super Admin — this is what makes the audit trustworthy.

---

## 7. Sharing & delegation model

Sharing is **cross-Space access**: it lets a principal in one space reach a scoped part of *another* space, without moving the resource. It is the largest *new* surface, so it is designed default-deny, owner-consented, live-revocable, and heavily audited. Everything below is expressed as **grants** — no new enforcement path.

### 7.1 Grant shape

`(grantor, grantee_principal, source_space, scope, level, conditions, expiry, revocable, purpose, audit)`

- **grantor**: an authorized principal *within the source space* — the Space's owner, or (for household/org/church/practice spaces) a member holding the space-scoped `space.share` capability.
- **grantee**: a *principal* (a WLJ account/service), **optionally associated** with a People/`Person` record — but the auth subject is the account, never the descriptive `Person` (People/relationships is *descriptive truth about people in your life*, not an auth identity; keeping these separate is a hard rule).
- **source_space**: the Space whose resources are being shared (the grant is evaluated as "grantee holds `level` in `source_space` over `scope`").
- **scope**: a resource-set *within* the source space — by domain (`health`, `finance`, `faith`), by object, or "all."
- **level**: `read`, `read-write`, or a specific capability subset.
- **conditions**: MFA, purpose-binding, time window.
- **expiry / revocable**: time-boxed by default for sensitive shares; revocation is **immediate** (PDP checks grants live).

A share is *the same object* whether the two parties are individuals (my Personal Space → my spouse) or organizations (a Coaching Practice Space → a client's Personal Space, or vice-versa). **Cross-space sharing is not a special case** — every share crosses spaces; a "personal" share is just one where both spaces are Personal.

### 7.2 Relationship archetypes (all just grants)

Spouse/partner (broad, selected domains) · Parent↔child (guardianship-scoped) · Coach (read health/goals; optional plan write) · Healthcare provider (read medical/health; time-boxed; purpose-bound; HIPAA-aware posture) · Financial advisor (read finance) · Church (read faith / shared community) · Temporary delegation (time-boxed) · Read-only vs read/write (the `level`) · Emergency/break-glass (§7.4).

### 7.3 Consent, visibility, revocation

- The **source space's authority** (its owner, or a member with `space.share`) is the sole grantor of shares over that space's data and can revoke any share at any time; revocation takes effect on the next PDP evaluation (live).
- Every space has a **"who can see this space's data"** surface listing active shares, scopes, levels, and expiry — a product feature, not a hidden setting. For a Personal Space this is the person's own "who can see my data."
- Grant creation/revocation is itself audited (who granted whom what, when, why).

### 7.4 Emergency / break-glass access

A special grant type that: requires elevated conditions (step-up + reason), **notifies the owner**, is strictly time-boxed and auto-expiring, is limited in scope, and is heavily audited with mandatory post-hoc review. Break-glass is how (e.g.) an emergency contact or Super Admin reaches data they normally cannot — visibly and accountably, never silently.

---

## 8. AI authorization model

This section operationalizes Constitutional Articles I.2 (the model reasons, it does not own authority) and I.7 (actions run the safe, deterministic, audited path).

1. **The Chief of Staff never self-authorizes.** It acts as a **derived principal**: "CoS on behalf of User U, **in Space S**." Reasoning ability confers *no* authority.
2. **Bounded by the human, *within the acting space*.** The AI principal's authority = `(U's capabilities resolved by the PDP for Space S) ∩ AI-allowlist − AI-denylist`. Because U's capabilities are *already* space-scoped and the PDP resolves them per space, the AI is **per-space for free** — no new mechanism. It can **never exceed** U in S, and holds **zero** platform capabilities — even if U is also an Operator/Admin, the CoS gets none of U's platform powers, in any space. (An operator's assistant is still just their assistant.)
3. **Acting space is Current Context.** Which space the CoS is acting in is the **acting Space** (§3.2), resolved server-side from Current Context — never inferred by the model. A coach's CoS working a client's shared scope, and that same coach's CoS in their own Personal Space, are the same principal resolved against two different spaces.
4. **Deterministic gate, not a reasoning gate.** The model may *propose* an action; the PDP *decides* deterministically, in the resolved space. The model's confidence is never an authorization input. This is the exact mechanism that keeps I.2/I.7 intact.
5. **Same safe path.** Every AI-initiated action flows: perceive/propose (model) → **validate** → **authorize** (PDP, as CoS-on-behalf-of-U-in-S) → **confirm** (user confirmation for `ai_confirm` capabilities) → **execute** (deterministic handler bound to U + S) → **audit with provenance** (actor chain: model → CoS-on-behalf-of-U → effect, stamped with Space S). This *formalizes* today's `ActionHandler(user)` + confirmation-preference + Learning-Mode kill-switch into explicit action capabilities and an explicit AI principal.
6. **`ai_never` tier.** Some capabilities are structurally denied to *any* AI principal regardless of U's own rights — e.g. delete-account, `data.share` (a human, not the AI, extends a space's data to another space), financial transfers, changing security/auth settings, anything in the platform plane, and any cross-space administration. These require the human to act directly. (Consistent with WLJ's standing "prohibited actions" posture.)
7. **Delegated AI composes.** A coach's CoS acts as "CoS on behalf of Coach, in the client's space, over the share's scope" — the same rule, composed with §7. It never exceeds the coach's share and never leaks between the coach's spaces.
8. **Background AI is a service principal.** Intelligence/computation jobs run as a Service Account with narrow compute capabilities, space-scoped where they touch space data, never as an unbounded actor.

---

## 9. Audit architecture

**Goal:** one trustworthy, append-only record of *everything administrative and every sensitive action*, answering **who / what / when / where / which space / before / after / why** — plus the authorization decision that permitted it.

> **Space is a first-class audit dimension from day one** (validation finding R4). Because the audit spine is append-only and immutable, its schema cannot cleanly gain a dimension later — so `space` and `resource_owner` are present from the first record even while WLJ is single-space (`space = <that Personal Space>`). This is the one part of the framework whose *schema* must be right before implementation; getting it right costs nothing single-space and prevents a permanent pre/post-multi-space seam.

### 9.1 Principles

- **One append-only, tamper-evident audit spine** (hash-chained / WORM-style). A single authority for audit truth (Article III.1 applied to audit). Consolidates today's siloed, inconsistent stores (`AdminActivityLog` records a coarse enum for *who*; `SecurityAuditLog` has full who/what/when but only for the security domain; `APIRequestLog` is request-level). The target is one spine those domains feed, consistent on the real acting principal.
- **Immutable to all.** Readable via `audit.view`; mutable/deletable by no one, including Super Admin. (PII-erasure requests are honored by a separate tombstoning process that preserves the hash chain — see §12.)

### 9.2 The record (7 W's + decision)

| Field | Content |
|---|---|
| **who** | acting principal **and** the real human behind any impersonation/service; not a coarse enum |
| **acting role** | which capability bundle / membership was exercised (plane: Space vs Platform) |
| **what** | capability exercised + resource (type + id) |
| **which space** | the resolved **Space** (and space kind); `resource_owner` within it |
| **when** | timestamp |
| **where** | IP / device / surface / request-id |
| **delegation source** | for cross-space/shared access, the share grant that authorized it |
| **before / after** | state delta or evidence snapshot for mutations |
| **why** | required justification for `elevated`/`critical`/break-glass |
| **authorization** | which grant permitted it; conditions satisfied (MFA, approval, break-glass) |

### 9.3 Special cases

- **AI actions**: full provenance actor chain (model → CoS-on-behalf-of-U → effect), extending the existing action-path audit.
- **Impersonation sessions**: fully bracketed (start/stop, approver, scope); everything done while impersonating is attributed to **both** the real admin and the target user.
- **Grant lifecycle**: creation, modification, revocation, and expiry of shares/role-bundles are audited.

---

## 10. Implementation roadmap (phased; not part of this milestone)

Each phase ships behind the single PDP so enforcement sites are touched **once** (Phase 1) and never again.

- **Phase 0 — Ratify design + define the Capability Registry and the *Space* model as data.** No behavior change. Establish that every existing user has one implicit **Personal Space** (their current `user`-owned data == "their Personal Space").
- **Phase 1 — PDP shim (behavior-preserving).** Introduce `authz.can(...)` returning decisions *equivalent to today* (`is_staff` → the platform bundles it implies; `is_superuser` → all; every `.filter(user=u)` == "resources in u's Personal Space"). Route **every** existing gate through it (the ~90 `is_staff` sites, the three `AdminRequiredMixin` definitions, the API-key checks). Land a CI contract: "no direct `is_staff`/`is_superuser` in views/api; authorization only via `authz.can`" (mirrors `test_constitution_contract` / `test_request_path_safety_contract`).
- **Phase 2 — Grants + Spaces in the DB.** Materialize the Personal Space per user + membership; model capabilities/grants *within a space*; seed current staff/superusers into explicit platform bundles via a data migration; flip the PDP to read grants; keep booleans as a temporary derived fallback, then retire. (Single-space still — no new user-facing concept.)
- **Phase 3 — Split the platform plane.** Separate Operations / Admin / Security / Super Admin bundles; enforce least privilege (remove blanket `is_staff`); attach step-up (WebAuthn) per sensitivity tier (generalizing `AdminOverrideConfirmationMixin`). Confirm platform grants carry **no** space membership.
- **Phase 4 — Unify audit (with Space + resource_owner dimensions from the first record).** One append-only tamper-evident spine; consolidate `AdminActivityLog`/`SecurityAuditLog`/`APIRequestLog` feeds; consistent *who*; `space`/`resource_owner`/`acting_role`/`delegation_source` fields present even while single-space; grant-lifecycle audit.
- **Phase 5 — Formalize the AI principal.** CoS-on-behalf-of-U derived principal + `ai_never`/`ai_confirm` tiers wired into the action-path authorization gate; convert `X-Claude-API-Key`/`X-Gmail-Sync-API-Key` into real Service Accounts with scoped capabilities.
- **Phase 6 — Sharing MVP.** Owner→grantee grants (spouse/read-only), the "who can see my data" surface, live revocation.
- **Phase 7 — Advanced sharing + controlled admin power.** Providers/coaches/church, emergency/break-glass, impersonation with approval + notification, two-person control on `critical` capabilities.
- **Phase 8 — External personas.** Organizational/church accounts, partner integrations.

Phases 1–2 are cheap and the highest leverage: they collapse ~90 scattered checks into one authority with zero behavior change. Later phases arrive only when the personas actually do (Article IV.2 — design ahead of need, build at need).

---

## 11. Migration strategy from today's implementation

Grounded in the current state (see Appendix A). **Strangler-fig, never a flag-day.**

1. **Stand up the PDP behind today's semantics.** `authz.can` initially derives platform capabilities from `is_staff`/`is_superuser` so *nothing changes behaviorally*, but there is now **one** place authorization is decided.
2. **Reroute all gates to the PDP.** Replace the three `AdminRequiredMixin` definitions and the inline `is_staff` guards (heaviest in `ops_views.py`, `diagnostics_views.py`, `admin_console/views.py`) with a single `RequiresCapability("…")` mixin/decorator that calls the PDP. Lock it with a CI contract.
3. **Introduce explicit grants; seed from reality.** A data migration maps existing staff/superusers to role bundles (today's two humans become an explicit Operations/Admin/Super-Admin assignment). The PDP flips to reading grants; `is_staff` becomes *derived* (a superuser bundle sets `is_staff=True` only for Django-admin compatibility) and is eventually reduced to meaning "holds a Django-admin capability."
4. **Promote the API keys to Service Accounts.** `X-Claude-API-Key` and `X-Gmail-Sync-API-Key` become Service Account principals with explicit scoped capabilities (`tasks.read`/`tasks.update`, `gmail.sync`) — same keys, now principals with audit.
5. **Keep ownership as the substrate; add PDP as defense-in-depth; read `UserOwnedModel` as "Personal Space membership."** `UserOwnedModel`/`SoftDeleteManager`/`.filter(user=…)` stay as the enforcement floor — semantically re-read as "belongs to this person's Personal Space." The PDP's `data.*` check (in the resource's space) is layered on top. **Sharing grants are added without touching the owner filter** — they only widen cross-space access. No table renames are required to adopt Space; a resource's `user`/`owner` FK *is* its (Personal) space until other space kinds exist.
6. **Formalize the AI path last** (Phase 5), because it is already user-bound and safe today; the change is making the principal and capability tiers *explicit*, not adding new power.
7. **Verify each step by contract tests; preserve behavior at every step.** Nothing is removed until its replacement is proven equivalent (Article IV.1 — prove the runtime path).

Backwards-compatibility guarantees: no endpoint changes access semantics during Phases 1–2; `is_app_review_account` and MFA middleware keep working (MFA becomes a *condition* the PDP consults rather than a parallel gate); dormant Django Groups/Permissions can be retired or repurposed as the grant store — an implementation choice for Phase 2.

---

## 12. Risks & tradeoffs

| Risk / tradeoff | Mitigation |
|---|---|
| **Complexity vs. today's simple booleans** | PDP shim is behavior-preserving; humans still think in role bundles; Phases 1–2 are small and high-leverage. |
| **Per-request PDP cost** | Grants resolved once per request/session; decision is O(1) set membership; request-path-safe (no heavy compute) — consistent with WLJ's request-path-safety rule. |
| **Over-engineering for a near-single-user product** | *Design* now, *build at need*. Only Phases 0–2 are warranted soon; sharing/impersonation land when personas exist. |
| **Space as a primitive adds abstraction that may never be used** | Minimal by construction: single-user = **one Personal Space, sole owner**; the only machinery a space needs (a scope on a grant) is *already required for sharing*. A resource's `user`/`owner` FK *is* its space until other space kinds exist — no new tables to adopt the concept, no user-facing "space" until a person joins a second one. |
| **Tenant-admin wrongly modeled as platform-admin** | Space-as-primitive makes it structurally impossible: space administration is a space-scoped capability (`space.manage_members`) in the Space plane; the Platform plane is bound to no space. |
| **Audit immutability vs. GDPR/erasure** | Separate PII-tombstoning process preserves the hash chain while removing personal content; erasure is itself audited. |
| **Super Admin = catastrophic single point** | Minimal population; hardware MFA; two-person control on `critical`; break-glass (time-boxed, owner-notified, post-hoc review); audit immutable even to Super Admin. |
| **Sharing = biggest new attack surface** | Default-deny; explicit owner consent; live revocation; purpose/time-boxing; owner-visible; heavy audit; `ai_never` on `data.share`. |
| **AI over-reach** | AI principal ≤ human, zero platform capabilities, `ai_never` tier, deterministic gate (not reasoning) — structurally enforced. |
| **Impersonation abuse** | Approval + owner notification + full bracketed audit + restricted scope + cannot impersonate an equal-or-higher-privilege principal. |
| **Two `AdminRequiredMixin` defs / ~90 scattered checks drift further** | Phase 1 collapses them into one PDP + CI contract *before* any new persona work. |
| **Confusing People/`Person` records with auth identities** | Hard rule: the auth grantee is always an account/principal; a `Person` may be *associated* but is never the auth subject. |

---

## 13. Recommended governing documentation

- **This document** (`docs/WLJ_SECURITY_AUTHORIZATION_FRAMEWORK.md`) becomes a foundational governing doc once ratified — added to the CLAUDE.md reference table and the startup-package index, alongside the Truth/Action Contract, Current Context Contract, Layer 1 Framework, and Operations Vision.
- **Companion docs to spawn at implementation:**
  - *Space & Membership Contract* — space kinds, ownership, membership rules, acting-space via Current Context.
  - *Capability Registry Reference* — the authoritative capability list + attributes.
  - *Sharing & Consent Contract* — grant shapes, archetypes, revocation, break-glass.
  - *Audit & Impersonation Runbook* — the audit record, immutability, impersonation approval/notification flow.
  - *AI Authorization Contract* — the CoS-on-behalf-of principal + `ai_never`/`ai_confirm` tiers (an extension of the LLM Truth/Action Contract).
- **CI contract** (with Phase 1): "authorization is only decided via `authz.can`; no direct `is_staff`/`is_superuser` in views/api," in the family of `test_constitution_contract` / `test_request_path_safety_contract`.

---

## 14. Constitutional Review analysis

**Question:** Does adopting this framework require a Constitutional Review?

**Answer: No — with one deliberately-scoped exception (elevation into an Article), and two future decisions that *would* trigger a Review if ever proposed.**

**Why no Review is required to adopt this design.** A Constitutional Review is mandatory only when a proposal would *change, weaken, remove, or invert* one of the five Articles, the naming rule, or the §0 framing. This framework does none of those. Per §3 itself, "new features, new domains, new truth, new tools … do **not** require a Constitutional Review, as long as [they] stay inside the Articles." Authorization is a *new governing domain*, and it stays firmly inside the Articles. In fact it **reinforces** them:

- **Article III (Single Deterministic Authority)** — the framework's core is *one* PDP; it applies III.1 to authorization rather than weakening it.
- **Article I.2 / I.7 (model reasons; WLJ owns the safe, deterministic, audited action path)** — the AI model (§8) makes authorization *more* faithful to I.2/I.7: the CoS never self-authorizes, never exceeds the human, and every action stays on the deterministic audited path. Nothing here lets reasoning decide authority.
- **Article III.1 for Operations & Audit truth** — Operations truth and Audit truth each get exactly one authority; consistent, not in tension.
- **Article IV (Engineering Discipline)** — one registry, one PDP, one audit spine; reuse before rebuild; no duplicated permission logic.
- **Naming (§1) and I.8 (provider-agnostic)** — untouched; `ai.provider.manage` is a capability *over* configuration, and never makes a provider or assistant name a system identity.

Because the framework operates *below and beside* the Constitution (the Constitution governs the Truth/Reasoning division; this governs who-may-do-what), adopting it is ordinary — significant — architectural work, not a constitutional amendment.

**The one part that *would* be a constitutional act — and only if you choose it.** Making the framework's core invariant a *constitutionally protected Article* is itself a constitutional change. If, after implementation and validation, you want the invariant permanently protected, that elevation goes through the Review process (STOP, ⚠️ notice, explicit written approval, Amendment Log). Proposed candidate, for a future, deliberate review — **not** requested now:

> **Article VI — Deterministic Authorization.** Every resource and grant in WLJ lives within a **Space**; authorization is deterministic, capability-based, and decided by a single authority, evaluated within the resource's space. Roles are bundles of capabilities. The Chief of Staff never self-authorizes and never exceeds the human it acts for, within the space it acts in. Platform authority never implies membership in, or data access to, any space. Audit of administrative and sensitive actions is append-only, space-stamped, and immutable to all principals.

Adopting *this document* as a governing doc does **not** require that Article to exist; the Article is an optional, later hardening. **At ratification (2026-07-18), Article VI is deliberately NOT created and NOT elevated** — it stays here as future discussion only. Note that the candidate is stated at the *primitive* level (Space, capability, single-authority) — so it already covers single-user, household, org, and every future space kind **without amendment**. That tenant-agnostic phrasing is itself evidence the framework is a decade foundation, not a point solution.

**Two future proposals that WOULD require a Review (flagged so implementation stays honest):**
1. Letting the **model's reasoning decide authorization** (AI self-authorizing on confidence) — inverts I.2/I.7 → **Review required, default NO.**
2. Introducing a **second authorization authority** / a permission path that bypasses the PDP — inverts the single-authority principle (and, if Article VI is adopted, the Article) → **Review required, default NO.**

**Ratification decision (2026-07-18):** This framework is **ratified as governing architecture** *without* a Constitutional Review (it is in-bounds and reinforcing). Ratification is **architecture only** — no production authorization changes, no permissions, no migrations, no implementation. Article VI is **not** created; its elevation remains a separate, optional future decision requiring explicit written approval. Implementation (Phases 0–1) is a distinct future initiative gated on its own approval.

---

## Appendix A — Current-state grounding (as-built, for the migration)

- **Identity:** custom `User(AbstractBaseUser, PermissionsMixin)`, email login via allauth (mandatory verification). Privilege = `is_staff` (default False), occasionally `is_superuser`. `is_app_review_account` is a broad bypass flag. MFA enforced by middleware for staff/superusers (WebAuthn + email code), with a hardcoded exempt-email list. No first-class service account.
- **Gates:** ~90+ `is_staff` checks in two idioms; **three** separate `AdminRequiredMixin` definitions (`admin_console/views.py`, `ai_observability/ops_views.py`, `diagnostics_views.py`); `AdminOverrideConfirmationMixin` (step-up re-auth); pervasive `LoginRequiredMixin`; two bespoke API keys (`X-Claude-API-Key`, `X-Gmail-Sync-API-Key`); Django Groups/Permissions present but dormant (one real `has_perm`, in `owner_finance`).
- **Isolation:** entirely via user-scoped querysets — `UserOwnedModel` + `SoftDeleteManager` + `.filter(user=request.user)`. No object-level permission checks.
- **Admin surfaces (all just `is_staff`):** admin_console, Ops Wall, diagnostics, Intelligence Center, certification, Django admin, security dashboard.
- **Audit (siloed):** `AdminActivityLog` (coarse enum for *who*), `SecurityAuditLog` (full who/what/when, security-scoped), `APIRequestLog` (request-level), `TermsAcceptance`, `IPBlocklist`. No unified "admin X did Y to user Z" trail. (`canonical_audit.py` is a code-quality ORM auditor, not an action log.)
- **AI actions:** `intent_service.execute_intent` → `ActionHandler(user)`, bound to the user; a confirmation preference; the Learning-Mode kill-switch; `use_model_interface_writes` as a per-user write-enable rollout flag. No policy/permission object.
- **Impersonation:** none. **Sharing/delegation:** none (greenfield). People/`relationships` is descriptive truth about people in the user's life, **not** auth identity.

---

*This is a PROPOSED design for review. It introduces no code, no migrations, and no change to existing authorization. Implementation is a separate initiative, gated on approval of this design.*
