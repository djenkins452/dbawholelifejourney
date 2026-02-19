"""
Phase 5 — Language Rules.

Defines what the CoS is NEVER allowed to say to the user.
These are internal system terms that should never surface
in user-facing output.

Public API:
    - build_language_rules_injection() -> str
    - BANNED_TERMS -> list[str]
"""

# Terms that must NEVER appear in user-facing output.
# The LLM receives these as a system prompt constraint.
BANNED_TERMS = [
    "drift pressure",
    "DriftPressure",
    "governance profile",
    "GovernanceProfile",
    "consistency evaluator",
    "ConsistencyEvaluator",
    "strategy selector",
    "ALIGN strategy",
    "PROTECT strategy",
    "CHALLENGE strategy",
    "COMPRESS strategy",
    "recalibration loop",
    "recalibration trigger",
    "protection pass",
    "noise budget",
    "miss rate",
    "importance weight",
    "capacity factor",
    "responsiveness score",
    "tier 1",
    "tier 2",
    "tier 3",
    "tier 4",
    "PIE event",
    "SAE state",
    "PRIE prediction",
    "PGE guidance",
    "system injection",
    "system prompt",
    "architecture pass",
    "scheduled block",
    "friction gate",
    "intervention log",
    "escalation modifier",
]


def build_language_rules_injection():
    """
    Build system prompt instructions for language compliance.

    Returns:
        str — language rules block for system prompt.
    """
    lines = ["--- LANGUAGE RULES ---"]
    lines.append(
        "You must NEVER use any internal system terminology with the user. "
        "Speak naturally as a trusted advisor, not a system."
    )
    lines.append("")
    lines.append("BANNED PHRASES (never use these with the user):")
    # Group in batches for readability
    for term in BANNED_TERMS:
        lines.append(f'  - "{term}"')
    lines.append("")
    lines.append(
        "INSTEAD, use natural language: "
        "'your workout' not 'scheduled block', "
        "'what you told me matters' not 'governance profile', "
        "'you've been skipping this' not 'miss rate is 0.7', "
        "'your schedule is packed' not 'capacity at 85%'."
    )
    lines.append("--- END LANGUAGE RULES ---")
    return '\n'.join(lines)
