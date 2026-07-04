# ==============================================================================
# File: apps/ai/chatgpt_cos/decision_support.py
# Capability: DECISION SUPPORT (the first Layer 2 Chief-of-Staff capability).
#
# Layer 1 answers "what is true" (facts). Layer 2 answers "given everything true
# right now, is this a good decision?" When the user is not ASKING for information
# but COMMUNICATING a decision — abandoning a plan, reprioritizing, accepting a
# tradeoff, giving up on something, or calling it for the night — a world-class
# Chief of Staff does not retrieve facts. It recognizes the decision, evaluates the
# tradeoff against the WHOLE current situation, and helps the executive make the best
# call — sometimes agreeing, sometimes challenging, sometimes proposing a compromise,
# always explaining WHY.
#
# Production failure that motivated this: "I'm not going to work out or get to my
# protein drink. I'm about done tonight. Just need to take my nightly meds and I am
# done." Beth listed the medications. Factually correct; a total failure of the
# conversation — the user was describing the plan for the rest of the evening, and
# the hidden question was "given the day I've had, does this sound right?"
#
# HOW IT DIFFERS
#   • Fact retrieval (Layer 1 / foundational_facts): returns a stored value. Decision
#     Support returns a JUDGMENT about a choice.
#   • Coaching (proactive nudges): pushes a generic best-practice. Decision Support
#     reasons about THIS decision in THIS situation and may endorse doing less.
#   • Recommendations (rec effectiveness): "here's a good thing to do." Decision
#     Support evaluates a decision the user has ALREADY voiced.
#
# ARCHITECTURE: this does NOT redesign Layer 1 or routing. It CONSUMES existing
# deterministic truth (executive_interpretation.interpret → ExecutiveSignals, plus
# the first-person situational truth the user just stated) and produces a COMPOSED
# assessment for Beth to narrate — the established "Beth narrates composed state,
# she does not reason from atomic signals" contract. Deterministic, request-path
# safe, degrades gracefully.
# ==============================================================================
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── Decision speech-acts (the recognizer — this is a routing decision, so it is
#    deterministic and testable). Matched against a normalized message. ──────────
_ABANDON = (
    "not going to", "not gonna", "im not going to", "im not gonna", "not going too",
    "not going to get to", "wont get to", "won't get to", "not doing", "im not doing",
    "gonna skip", "going to skip", "im skipping", "gonna pass on", "passing on",
    "not up for", "not going to make it to", "wont make it to", "cant be bothered",
    "not making it to", "gonna bail", "im bailing", "not going to bother",
    "dont think im going to", "dont think ill", "dont think i will",
    "dont think im gonna", "probably wont", "not going to happen tonight",
)
_SKIP = ("skip",)                      # "skip X" — pair with a commitment word
_END_OF_DAY = (
    "im done", "i am done", "about done", "done for the day", "done for tonight",
    "done for the night", "done for today", "im done for", "call it a day",
    "call it a night", "calling it a night", "calling it a day", "thats it for today",
    "thats it for tonight", "im spent", "im beat", "im wiped", "im crashing",
    "going to bed", "gonna go to bed", "off to bed", "heading to bed", "head to bed",
    "im turning in", "turning in", "in for the night", "im out for the night",
    "wrapping up for the day", "gonna crash", "ready for bed", "just going to bed",
)
_CHANGE_MIND = (
    "changed my mind", "change of plans", "on second thought", "second thoughts",
    "rethinking", "im rethinking", "instead of", "rather than", "decided instead",
    "gonna do instead", "changed my plans",
)
_GIVE_UP_GOAL = (
    "dont think ill finish", "not going to finish", "wont finish", "won't finish",
    "might not finish", "not gonna finish", "give up on", "giving up on",
    "dont think ill hit", "wont hit my", "not going to hit", "not going to reach",
    "dont think ill reach", "quitting", "im quitting", "throwing in the towel",
    "dont think i can finish", "not going to make my goal",
)
_FATIGUE = (
    "im exhausted", "so exhausted", "im so tired", "im tired", "im wiped out",
    "wiped out", "worn out", "im worn out", "im drained", "no energy", "no gas left",
    "running on empty", "im beat", "im spent", "im done in", "im shattered",
    "cant do anymore", "cant anymore", "totally drained", "completely drained",
    "exhausted",
)

# Situational modifiers — context that makes the tradeoff reasonable. Not triggers on
# their own; they colour the empathy and the WHY. Scanned across the recent thread.
_HEAT = ("hot sun", "in the sun", "sun all day", "the heat", "so hot", "out in the sun",
         "heat all day", "scorching", "sweating all day", "humidity")
_LONG_DAY = ("all day", "with friends", "been out", "outside all day", "on my feet",
             "long day", "busy day", "out all day", "running around")
# An ACTIVE / physical / social day. The point: the user already DID something today —
# so easing off tonight is not "falling behind," and the body has real recovery need
# (which changes the effort-vs-benefit math on recovery nutrition). Drives the
# "you've already had a real day" framing.
_ACTIVE_DAY = ("pool", "swim", "swimming", "beach", "lake", "hike", "hiking", "walked",
               "walking", "yard work", "mowing", "golf", "kayak", "boating", "played",
               "on my feet", "with friends", "cookout", "bbq", "ballgame")


def _activity_phrase(ctx):
    """A personal, specific description of what the day actually WAS (not generic)."""
    if any(w in ctx for w in ("pool", "swim", "beach", "lake")):
        return "a day at the pool"
    if any(w in ctx for w in ("hike", "walk", "golf", "kayak", "boating", "yard", "mowing")):
        return "a day on your feet"
    if any(w in ctx for w in ("friends", "cookout", "bbq", "ballgame", "played")):
        return "a full day out with friends"
    return "a full, active day"

# Commitments a decision can touch (for holistic, not single-domain, reasoning).
_COMMITMENTS = {
    "workout": ("work out", "working out", "workout", "exercise", "gym", "training",
                "train", "lift", "lifting", "run", "cardio", "session"),
    "nutrition": ("protein", "shake", "drink", "meal", "dinner", "eat", "eating",
                  "nutrition", "calories", "macros", "food"),
    "faith": ("church", "service", "worship", "mass", "bible", "devotion", "pray",
              "prayer", "small group", "sunday"),
    "goal": ("goal", "finish", "target", "mission", "habit", "streak", "milestone"),
    "sleep": ("bed", "sleep", "turn in", "sleeping", "asleep", "rest", "turning in"),
    "meds": ("meds", "medication", "medications", "pills", "pill", "medicine",
             "nightly meds", "night meds"),
}
# Commitments that are NON-NEGOTIABLE — deferring these is a real risk, not a safe
# tradeoff, so Beth gently challenges rather than endorses.
_NON_NEGOTIABLE = ("meds",)
# Commitments that are safely deferrable for a single evening (one instance ≠ trend).
_DEFERRABLE = ("workout", "nutrition")


@dataclass
class DecisionSignal:
    kind: str                                  # abandon|end_of_day|change_mind|give_up_goal|fatigue
    abandoned: list = field(default_factory=list)   # commitments being let go
    kept: list = field(default_factory=list)        # commitments explicitly kept
    active_day: bool = False                        # already had a physical/social day
    activity: str = ""                              # e.g. "a day at the pool"
    heat: bool = False
    long_day: bool = False
    fatigue: bool = False


def _norm(s):
    s = (s or "").lower().replace("-", " ").replace("/", " ")
    s = s.replace("'", "").replace("’", "")   # I'm→im, don't→dont, I'll→ill
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _commitments_in(text):
    found = []
    for name, cues in _COMMITMENTS.items():
        if any(c in text for c in cues):
            found.append(name)
    return found


def detect_decision(message, recent_context=""):
    """Recognize when the user is COMMUNICATING A DECISION (not asking for facts).

    Returns a ``DecisionSignal`` or ``None``. Speech-act detection uses ONLY the
    current message (so stale content never re-triggers); situational modifiers
    (heat / long day / fatigue) are read from the recent thread too, because they are
    first-person truth that bears on the tradeoff."""
    norm = _norm(message)
    if not norm:
        return None
    ctx = (norm + " " + _norm(recent_context)).strip()

    has_abandon = any(c in norm for c in _ABANDON)
    # "skip <commitment>" is an abandonment; a bare "skip" is not enough.
    has_skip = ("skip" in norm and any(
        c in norm for cues in _COMMITMENTS.values() for c in cues))
    end_of_day = any(c in norm for c in _END_OF_DAY)
    change_mind = any(c in norm for c in _CHANGE_MIND)
    give_up = any(c in norm for c in _GIVE_UP_GOAL)
    fatigue = any(c in norm for c in _FATIGUE)

    if not (has_abandon or has_skip or end_of_day or change_mind or give_up or fatigue):
        return None

    # Kind precedence: giving up on a goal and change-of-mind are the most specific;
    # then abandonment; then end-of-day; fatigue alone is the weakest signal.
    if give_up:
        kind = "give_up_goal"
    elif change_mind:
        kind = "change_mind"
    elif has_abandon or has_skip:
        kind = "abandon"
    elif end_of_day:
        kind = "end_of_day"
    else:
        kind = "fatigue"

    commitments = _commitments_in(norm)
    # A commitment framed as "take my … / keeping my …" is KEPT, not abandoned; meds
    # in an end-of-day plan ("just need to take my nightly meds") are being kept.
    kept, abandoned = [], []
    for c in commitments:
        keep_framed = (c == "meds" and any(
            k in norm for k in ("take my", "still take", "need to take", "gonna take",
                                "going to take", "have my", "keeping", "still do")))
        (kept if keep_framed else abandoned).append(c)
    # Sleep/bed in an end-of-day statement is the plan, not something abandoned.
    if kind in ("end_of_day", "fatigue") and "sleep" in abandoned:
        abandoned.remove("sleep")
        kept.append("sleep")

    heat = any(h in ctx for h in _HEAT)
    long_day = any(l in ctx for l in _LONG_DAY)
    # An active/physical/social day was already accomplished today (explicit activity,
    # or an outdoor day = heat + long day). This reframes "doing less" as "earned rest."
    active_day = any(w in ctx for w in _ACTIVE_DAY) or (heat and long_day)
    return DecisionSignal(
        kind=kind, abandoned=abandoned, kept=kept,
        heat=heat, long_day=long_day,
        fatigue=fatigue or any(f in ctx for f in _FATIGUE),
        active_day=active_day,
        activity=_activity_phrase(ctx) if active_day else "")


@dataclass
class DecisionAssessment:
    posture: str = "endorse"           # endorse | endorse_with_hedge | reflect | caution
    most_important: str = ""
    accomplished: str = ""             # what today already WAS (not a nothing day)
    reasons: list = field(default_factory=list)
    # Tiers by WEIGHT — not everything the user is dropping deserves equal treatment:
    non_negotiable: list = field(default_factory=list)  # (thing, why) — do it regardless
    worth_the_effort: list = field(default_factory=list)  # cheap + high-value: recommend
    deferrable: list = field(default_factory=list)   # fine to let go, guilt-free
    protect: list = field(default_factory=list)      # the recovery essentials (sleep)
    risks: list = field(default_factory=list)
    hedge: str = ""


def _safe_interpret(user, low_energy):
    try:
        from apps.ai.chatgpt_cos.executive_interpretation import interpret
        return interpret(user, low_energy=low_energy)
    except Exception:
        logger.warning("decision_support: interpret failed", exc_info=True)
        from apps.ai.chatgpt_cos.executive_interpretation import ExecutiveSignals
        return ExecutiveSignals()


def assess(user, signal):
    """Evaluate the voiced decision against the WHOLE current situation — the
    executive read (workload, recovery, sleep, mission) plus the first-person
    situational truth. Produces a composed ``DecisionAssessment``."""
    low_energy = bool(signal.fatigue or signal.heat or signal.kind in ("end_of_day",))
    sig = _safe_interpret(user, low_energy=low_energy)
    recovery = bool(getattr(sig, "recovery_needed", False) or signal.fatigue
                    or signal.heat or signal.kind in ("end_of_day", "fatigue"))
    a = DecisionAssessment()

    # WHY the situation points where it does (holistic, evidence-cited).
    if signal.heat:
        a.reasons.append("you were out in the heat")
    if signal.long_day:
        a.reasons.append("it's been a full day")
    sh = getattr(sig, "sleep_hours", None)
    if isinstance(sh, (int, float)) and sh and sh < 6.5:
        a.reasons.append(f"you're already carrying a short night (~{round(sh, 1)}h)")

    # Non-negotiables being dropped is the one thing to challenge.
    dropped_nn = [c for c in signal.abandoned if c in _NON_NEGOTIABLE]

    if signal.kind == "give_up_goal":
        a.posture = "reflect"
        a.most_important = "whether this goal still matters to you and is realistic from here"
        # A goal decision is about the goal, not tonight's heat — surface ONLY a real
        # mission tie-in, never the situational fatigue reasons.
        a.reasons = [f"it ties into {sig.strategic_focus}"] if getattr(
            sig, "strategic_focus", "") else []
        return a

    if signal.kind == "change_mind":
        a.posture = "reflect"
        a.most_important = "whether the new plan serves the day better than the old one"
        return a

    if dropped_nn:
        a.posture = "caution"
        a.most_important = "not letting the essentials slip even on a low day"
        a.risks.append("skipping your meds is the one thing tonight that actually "
                       "carries a cost — that's worth protecting even when everything "
                       "else gets dropped")
        return a

    # abandon / end_of_day / fatigue with only deferrable items → endorse resting.
    a.posture = "endorse"
    if recovery:
        a.most_important = "recovery tonight"
    else:
        a.most_important = "protecting the essentials and letting the rest go"

    # 1) Recognize what today ALREADY was — an active/social day is not a day off, so
    #    easing up tonight is earned, not slacking.
    if signal.active_day:
        sun = " out in the sun" if signal.heat else ""
        a.accomplished = f"{signal.activity}{sun} is real activity and real living — not a day off"

    # 2) Tier what he's dropping by EFFORT vs BENEFIT — the CoS judgment. A physical day
    #    (activity or heat) creates genuine recovery need, which makes the LOW-EFFORT
    #    protein shake worth the two minutes even when the workout clearly is not.
    physical_day = bool(signal.active_day or signal.heat)
    for c in signal.abandoned:
        if c == "workout":
            moved = ("you already moved plenty today, so " if signal.active_day else "")
            a.deferrable.append(("the workout",
                                 f"{moved}one skipped session won't move your trend — "
                                 "and a formal workout on top of a physical day isn't "
                                 "the difference-maker"))
        elif c == "nutrition":
            if physical_day:
                a.worth_the_effort.append((
                    "the protein shake",
                    "it's about two minutes and your body genuinely needs the recovery "
                    "after a physical day — that's a high payoff for almost no effort, "
                    "so it's the one I'd still knock out"))
            else:
                a.deferrable.append(("the protein drink",
                                     "one skipped drink is minor next to actually resting"))
        elif c == "faith":
            a.deferrable.append(("church",
                                 "resting when you're genuinely depleted is a fair "
                                 "tradeoff to make on purpose"))

    # 3) Weight the non-negotiable distinctly from the nice-to-haves.
    if "meds" in signal.kept:
        a.non_negotiable.append(("your meds",
                                 "take those no matter what — that's the one piece that "
                                 "isn't optional"))
    a.protect.append(("a real night's sleep",
                      "it does more for tomorrow than anything you'd force yourself to "
                      "do right now"))

    # 4) A low-cost optional optimization — offered only when there's no shake already
    #    on the table, so he never gets a pile of nudges.
    if signal.heat and "nutrition" not in signal.abandoned and not a.worth_the_effort:
        a.hedge = ("a glass of water before bed — you sweated a lot today, and it's "
                   "effortless — but only if it's easy")
        a.posture = "endorse_with_hedge"
    return a


# ── Composition — Beth NARRATES the assessment (holistic, always WHY, never a fact
#    dump, never generic coaching). ──────────────────────────────────────────────
def _reflect_line(signal):
    if signal.kind == "give_up_goal":
        return "Before you write it off, let's look at it clearly rather than in a tired moment."
    if signal.kind == "change_mind":
        return "Okay — let's make sure the change actually serves you, not just the moment."
    if signal.kind == "fatigue" and not signal.abandoned:
        return "You sound wiped, and that's worth taking seriously rather than pushing through."
    if signal.kind == "end_of_day":
        return "Sounds like you're calling it for the night — and after a day like this, that's a reasonable call, not a failure."
    return "Sounds like you're deciding to ease off tonight — and honestly, that can be the right call."


def _join_why(items):
    """items: list of (thing, why) → 'the workout (because …), and the protein …'."""
    out = []
    for thing, why in items:
        out.append(f"{thing} — {why}")
    if not out:
        return ""
    if len(out) == 1:
        return out[0]
    return "; ".join(out[:-1]) + "; and " + out[-1]


def compose(signal, assessment):
    a, parts = assessment, [_reflect_line(signal)]

    if a.posture == "caution":
        parts.append("The most important thing is " + a.most_important + ".")
        parts.extend(r[0].upper() + r[1:] + "." if r and r[0].islower() else r
                     for r in a.risks)
        parts.append("Drop the workout and the protein if you need to — but take the "
                     "meds first, then rest.")
        return " ".join(parts)

    if a.posture == "reflect":
        parts.append("The real question is " + a.most_important + ".")
        if signal.kind == "give_up_goal":
            if a.reasons:
                parts.append("Worth remembering " + a.reasons[0] + ".")
            parts.append("If it still matters, we can reset the target or the timeline "
                         "instead of dropping it; if it honestly doesn't, letting it go "
                         "on purpose is a legitimate decision, not a failure. Which is "
                         "it — still worth it, or time to release it?")
        elif signal.kind == "change_mind":
            parts.append("Tell me what you're moving to and I'll sanity-check it against "
                         "what's actually due and how much you've got left in the tank.")
        else:
            parts.append("If it's rest you need, that's a fair tradeoff to make "
                         "deliberately. What's driving it — and I'll help you weigh it?")
        return " ".join(parts)

    # endorse / endorse_with_hedge
    # Acknowledge the day already lived — rest is earned, not a shortfall.
    if a.accomplished:
        acc = a.accomplished
        parts.append(f"First though — you've already had a real day. {acc[0].upper()}{acc[1:]}. "
                     "So easing off tonight isn't slacking; it's earned.")
    # Recovery as a DELIBERATE strategy for the mission — not merely "doing less."
    why = (" — " + ", ".join(a.reasons)) if a.reasons else ""
    if a.most_important == "recovery tonight":
        parts.append(f"The right move tonight is recovery{why}. And I mean that as a "
                     "deliberate call, not just doing less: after a day like this, "
                     "resting is what protects tomorrow and keeps the mission moving.")
    else:
        parts.append(f"The most important thing right now is {a.most_important}{why}.")
    # Weighted guidance — non-negotiable, then the one cheap high-value thing, then
    # what to release, then the recovery essential.
    if a.non_negotiable:
        parts.append("If you do nothing else: " + _join_why(a.non_negotiable) + ".")
    if a.worth_the_effort:
        parts.append("If you've got two minutes in you, " + _join_why(a.worth_the_effort)
                     + ". Everything else can wait.")
    if a.deferrable:
        parts.append("Let the rest go guilt-free — " + _join_why(a.deferrable) + ".")
    if a.protect:
        parts.append("Then " + _join_why(a.protect) + ".")
    if a.hedge:
        parts.append("One optional, no-effort thing — " + a.hedge + ".")
    return " ".join(parts)


def respond(user, message, conversation=None):
    """Lane entry: if the message is a DECISION, return a composed decision-support
    answer; otherwise return ``None`` so normal fact/reasoning routing is unaffected."""
    recent = _recent_user_context(conversation)
    signal = detect_decision(message, recent_context=recent)
    if signal is None:
        return None
    try:
        assessment = assess(user, signal)
        answer = compose(signal, assessment)
    except Exception:
        logger.warning("decision_support: assess/compose failed", exc_info=True)
        return None
    if not answer:
        return None
    return {"answer": answer, "tools_called": [], "tools_advertised": [],
            "lane": "decision_support", "decision_kind": signal.kind}


def _recent_user_context(conversation):
    """The user's PREVIOUS message (e.g. 'out in the hot sun all day … tired'), so the
    tradeoff is judged with the situational truth stated a turn earlier."""
    if conversation is None:
        return ""
    try:
        from apps.ai.models import AssistantMessage
        msgs = (AssistantMessage.objects.filter(conversation=conversation, role="user")
                .order_by("-created_at").values_list("content", flat=True)[:2])
        return " ".join(m for m in msgs if m)
    except Exception:
        return ""
