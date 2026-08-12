"""
Token Governor — Enforces a global token budget on assembled prompts.

Accepts the fully assembled message list [system, ...history..., user]
and trims in priority order to stay within the budget ceiling.

Trimming order (lowest priority removed first):
1. Conversation history (oldest messages first)
2. CoS injection sections (if system prompt is still too large)

Feature-flagged via WLJ_TOKEN_BUDGET_ENABLED. When disabled, acts as
a pass-through that only measures (does not trim).

Project: Whole Life Journey
Path: apps/ai/conversation/token_governor.py
"""

import logging
from typing import List, Dict, Optional

from .token_budget import estimate_tokens, estimate_message_tokens

logger = logging.getLogger(__name__)


class TokenReport:
    """Per-request token breakdown for observability."""

    __slots__ = ('components', 'total', 'trimmed', 'over_budget')

    def __init__(self):
        self.components = {}  # {component_name: token_count}
        self.total = 0
        self.trimmed = []  # List of trimmed component names
        self.over_budget = False

    def to_dict(self):
        return {
            'components': dict(self.components),
            'total': self.total,
            'trimmed': self.trimmed,
            'over_budget': self.over_budget,
        }


def govern_prompt(
    messages: List[Dict],
    max_budget: int = None,
    ltrace=None,
    protect_recent: int = 6,
) -> tuple:
    """
    Enforce a global token budget on the assembled prompt.

    Args:
        messages: Full OpenAI message list [system, ...history..., user]
        max_budget: Maximum total prompt tokens allowed. An EXPLICIT value WINS over the
            WLJ_TOKEN_BUDGET_MAX setting (the model-interface tool loop sizes this to the
            model's real context window — the legacy 12k default cannot fit the ~21k
            model-interface system prompt and was silently deleting the conversation).
            When None, falls back to the setting (legacy callers unchanged).
        protect_recent: The most-recent conversation messages that are NEVER trimmed, so the
            immediate conversational antecedent can never be destroyed (Conversation Continuity
            root-cause fix, 2026-08-12). Phase 1 trims only OLDER history.
        ltrace: Optional LatencyTrace for recording governance decisions.

    Returns:
        (governed_messages, token_report) tuple.
    """
    from django.conf import settings
    enabled = getattr(settings, 'WLJ_TOKEN_BUDGET_ENABLED', False)
    # An explicit caller budget wins over the setting; else fall back to the setting/default.
    budget = (max_budget if max_budget is not None
              else getattr(settings, 'WLJ_TOKEN_BUDGET_MAX', 12000))

    report = TokenReport()

    if not messages:
        return messages, report

    # Measure each component
    system_tokens = 0
    history_tokens = 0
    user_tokens = 0
    history_count = 0

    for i, msg in enumerate(messages):
        t = estimate_message_tokens(msg)
        if i == 0:
            system_tokens = t
            report.components['system_prompt'] = t
        elif i == len(messages) - 1:
            user_tokens = t
            report.components['user_message'] = t
        else:
            history_tokens += t
            history_count += 1

    if history_count:
        report.components['conversation_history'] = history_tokens

    report.total = system_tokens + history_tokens + user_tokens

    # Record token report in latency trace
    if ltrace:
        for comp, count in report.components.items():
            ltrace.set_token_report(comp, count)

    if not enabled:
        return messages, report

    # Check if over budget
    if report.total <= budget:
        return messages, report

    report.over_budget = True
    logger.info(
        "TOKEN_GOVERNOR: over budget %d/%d, trimming", report.total, budget,
    )

    # Phase 1: Trim OLDER conversation history (oldest first) — but NEVER the most-recent
    # `protect_recent` messages. Deleting the immediate antecedent is the exact condition that
    # broke multi-turn continuity (the model received "system + bare user sentence" and could
    # not resolve "why?"); it is eliminated structurally here, not just made rarer by budget.
    if len(messages) > 2:
        system_msg = messages[0]
        user_msg = messages[-1]
        history = list(messages[1:-1])
        protected = history[-protect_recent:] if protect_recent > 0 else []
        trimmable = history[:len(history) - len(protected)]

        current_total = report.total
        while trimmable and current_total > budget:
            removed = trimmable.pop(0)
            removed_tokens = estimate_message_tokens(removed)
            current_total -= removed_tokens
            history_tokens -= removed_tokens

        report.components['conversation_history'] = history_tokens
        report.total = current_total
        if len(trimmable) < (len(messages) - 2 - len(protected)):
            report.trimmed.append('conversation_history')

        # Recent turns are always preserved; only older history may have been trimmed.
        history = trimmable + protected
        messages = [system_msg] + history + [user_msg]

    # Phase 2: If still over budget after trimming all history,
    # truncate the system prompt by removing text from the end
    # (lower-priority CoS sections are appended last)
    if report.total > budget and messages:
        excess = report.total - budget
        excess_chars = int(excess * 4)  # ~4 chars per token
        system_content = messages[0].get('content', '')
        if len(system_content) > excess_chars + 500:
            # Truncate from end, preserving at least 500 chars
            truncated = system_content[:len(system_content) - excess_chars]
            # Find last newline to avoid mid-sentence truncation
            last_nl = truncated.rfind('\n')
            if last_nl > len(truncated) // 2:
                truncated = truncated[:last_nl]
            truncated += "\n\n[Context trimmed to fit token budget]"
            messages[0] = dict(messages[0])
            messages[0]['content'] = truncated
            report.components['system_prompt'] = estimate_tokens(truncated) + 4
            report.total = sum(
                estimate_message_tokens(m) for m in messages
            )
            report.trimmed.append('system_prompt')

    if ltrace:
        ltrace.set_governance_decision(
            'token_budget_enforced',
            f"trimmed={','.join(report.trimmed)} final={report.total}",
        )
        # Update token report with post-trim values
        for comp, count in report.components.items():
            ltrace.set_token_report(comp, count)

    logger.info(
        "TOKEN_GOVERNOR: trimmed [%s], final=%d/%d",
        ', '.join(report.trimmed), report.total, budget,
    )

    return messages, report
