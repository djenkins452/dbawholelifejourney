"""
UAL — Executive Narrative Engine.

Builds the unified executive narrative that gets injected into the
system prompt. Answers: "What is the story of this moment?"

The narrative:
1. Acknowledges state
2. Frames the dominant issue
3. Offers clear next move
4. Invites adjustment

Never lists 8 separate reminders. Always unifies.
"""
import logging

from apps.core.ai_observability.instrumentation import log_engine_span as _instrument_span

logger = logging.getLogger(__name__)


@_instrument_span("UAL", "build_narrative")
def build_narrative(
    scenario_result: dict,
    composites: list,
    intervention: dict,
    signals: dict,
) -> str:
    """
    Build the executive narrative for system prompt injection.

    Returns a formatted string ready for system prompt insertion.
    """
    dominant = scenario_result["dominant_scenario"]
    style = intervention["intervention_style"]
    surfaced = intervention["surfaced_items"]
    suppressed = intervention["suppressed_items"]
    composite = intervention.get("primary_composite")

    # Build the narrative parts
    story = _build_story(dominant, composite, signals, surfaced)
    framing = _build_framing_directive(style, intervention["style_description"])
    surface_block = _build_surfaced_block(surfaced)
    suppress_block = _build_suppressed_block(suppressed)

    parts = [
        "=== EXECUTIVE JUDGMENT (UAL) ===",
        "",
        f"DOMINANT SCENARIO: {dominant}",
    ]

    secondaries = scenario_result.get("secondary_scenarios", [])
    if secondaries:
        parts.append(f"Secondary: {', '.join(secondaries)}")

    if composite:
        parts.append(f"COMPOSITE: {composite}")

    parts.append("")
    parts.append(f"INTERVENTION STYLE: {style}")
    parts.append(framing)
    parts.append("")
    parts.append("NARRATIVE FRAME:")
    parts.append(story)
    parts.append("")
    parts.append(surface_block)

    if suppress_block:
        parts.append("")
        parts.append(suppress_block)

    parts.append("")
    parts.append("INSTRUCTIONS: Unify your response around the narrative frame above.")
    parts.append("Do NOT list separate reminders for each signal. Weave them into ONE cohesive message.")
    parts.append("If the user asks about something outside the dominant scenario, answer directly — don't force the frame.")
    parts.append("")
    parts.append("=== END EXECUTIVE JUDGMENT ===")

    return "\n".join(parts)


def _build_story(
    dominant: str,
    composite,
    signals: dict,
    surfaced: list,
) -> str:
    """Build the human-readable story of this moment."""
    health = signals.get("health_signals", {})
    mood = signals.get("mood_signals", {})
    sched = signals.get("schedule_signals", {})
    drift = signals.get("drift_signals", {})
    rel = signals.get("relational_signals", {})
    upcoming = signals.get("upcoming_events", {})
    time_ctx = signals.get("time_context", {})

    # Composite-specific narratives take priority
    if composite == "LOW_CAPACITY_DAY":
        sleep_dur = health.get("sleep_duration_minutes")
        sleep_str = f"{sleep_dur} minutes of sleep" if sleep_dur else "poor sleep"
        cap = sched.get("capacity_pct", 0)
        return (
            f"Running on {sleep_str} with {cap:.0f}% schedule capacity. "
            f"Today is about protection, not production. "
            f"Lead with health gates, then help identify what can move."
        )

    if composite == "PHYSICAL_RISK":
        return (
            "Injury signals detected in recent journal entries. "
            "If a workout is planned, flag the risk and suggest modification. "
            "Don't lecture — inform and let the user decide."
        )

    if composite == "RELATIONAL_OPPORTUNITY":
        events = upcoming.get("significant_next_7d", [])
        if events:
            nearest = min(events, key=lambda e: e.get("days_until", 99))
            person = nearest.get("person", "someone important")
            days = nearest.get("days_until", "?")
            return (
                f"{person}'s {nearest.get('type', 'event')} is in {days} days. "
                f"Schedule is light enough to prepare. "
                f"Surface the opportunity without being pushy."
            )
        return "A relational opportunity is available. Surface it gently."

    if composite == "EMOTIONAL_OVERLOAD":
        return (
            "Multiple emotional stressors active. Mood is declining and "
            "journal entries show emotional weight. "
            "Reduce cognitive demands. Acknowledge before directing."
        )

    if composite == "RECOVERY_NEEDED":
        sleep_dur = health.get("sleep_duration_minutes")
        return (
            f"Sleep deficit ({sleep_dur or '?'} min) combined with high "
            f"activity load. Body needs recovery. "
            f"Suggest rest-oriented modifications to the day."
        )

    if composite == "ALIGNMENT_CRISIS":
        nn_missed = drift.get("non_negotiables_missed", 0)
        return (
            f"{nn_missed} non-negotiable commitments missed today. "
            f"Drift score is elevated. Name the gap clearly but without "
            f"judgment. Offer one concrete step back toward alignment."
        )

    # Scenario-specific narratives
    if dominant == "TIME_CRITICAL":
        next_4h = sched.get("next_4h_events", [])
        if next_4h:
            next_event = next_4h[0]
            return (
                f"Time-sensitive: {next_event.get('title', 'event')} "
                f"at {next_event.get('time', 'soon')}. "
                f"Focus on what must happen before then. "
                f"Defer everything that can wait."
            )
        overdue = upcoming.get("overdue_tasks", 0)
        return (
            f"{overdue} overdue items need attention. "
            f"Help triage — what's most impactful right now?"
        )

    if dominant == "HEALTH_CRITICAL":
        missed_meds = health.get("medications_missed", 0)
        sleep_dur = health.get("sleep_duration_minutes")
        parts = []
        if missed_meds:
            parts.append(f"{missed_meds} medication(s) missed or late")
        if sleep_dur and sleep_dur < health.get("sleep_target_minutes", 480) * 0.7:
            parts.append(f"only {sleep_dur} min sleep")
        body = ". ".join(parts) if parts else "Health signals need attention"
        return f"{body}. Health gates come first — address these before productivity."

    if dominant == "DRIFT_CRITICAL":
        score = drift.get("drift_score", 0)
        return (
            f"Drift score at {score}. Commitments are slipping. "
            f"Name the specific gap and offer one step back. "
            f"No guilt — just clarity."
        )

    if dominant == "MOOD_CRITICAL":
        trend = mood.get("mood_trend", "declining")
        keywords = mood.get("health_keywords_in_journal", [])
        kw_str = f" (mentioning: {', '.join(keywords[:3])})" if keywords else ""
        return (
            f"Mood trend is {trend}{kw_str}. "
            f"Acknowledge the emotional weight first. "
            f"Offer one gentle next move, not a to-do list."
        )

    if dominant == "RELATIONSHIP_CRITICAL":
        drifting = rel.get("drifting_relationships", [])
        if drifting:
            top = drifting[0]
            return (
                f"{top.get('name', 'Someone important')} hasn't been contacted "
                f"in {top.get('days_since', '?')} days "
                f"(tier-{top.get('tier', '?')}, {top.get('cadence', '?')} cadence). "
                f"Surface the connection opportunity."
            )
        events = upcoming.get("significant_next_7d", [])
        if events:
            nearest = events[0]
            return (
                f"{nearest.get('title', 'Event')} approaching. "
                f"Help prepare thoughtfully."
            )
        return "Relational signals are active. Surface the most important connection."

    # STABLE_EXECUTION (default)
    tod = time_ctx.get("time_of_day", "day")
    if surfaced:
        top = surfaced[0]
        return (
            f"Clean {tod}. No critical signals. "
            f"Top focus: {top.get('label', 'main priority')}. "
            f"Help execute efficiently."
        )
    return (
        f"Clean {tod}. No critical signals active. "
        f"Execute the day plan. Be responsive, not directive."
    )


def _build_framing_directive(style: str, description: str) -> str:
    """Build the framing directive for the AI."""
    return f"- {description}"


def _build_surfaced_block(surfaced: list) -> str:
    """Format surfaced items."""
    if not surfaced:
        return "SURFACE: No critical items — focus on user's request."

    lines = ["SURFACE (max 3):"]
    for i, item in enumerate(surfaced, 1):
        lines.append(
            f"  {i}. {item['label']} — {item['detail']} [{item['category']}]"
        )
    return "\n".join(lines)


def _build_suppressed_block(suppressed: list) -> str:
    """Format suppressed items."""
    if not suppressed:
        return ""

    lines = ["SUPPRESS (do not proactively raise):"]
    for item in suppressed[:5]:  # Cap at 5 to avoid noise
        lines.append(f"  - {item['label']} ({item['category']})")
    return "\n".join(lines)
