"""
AI Profile Content Moderation

This module provides content moderation for user AI profile inputs.
It ensures inappropriate, harmful, or injection-attempt content is
filtered before being used in AI prompts.

Key principles:
- Filter obvious harmful content (profanity, hate speech, threats)
- Detect and neutralize prompt injection attempts
- Preserve user privacy by sanitizing PII patterns
- Ensure outputs align with WLJ's values (wholesome, faith-friendly, respectful)
"""

import re
import logging

logger = logging.getLogger(__name__)


# Patterns that indicate prompt injection attempts
INJECTION_PATTERNS = [
    r'ignore\s+(all\s+)?(previous|above)\s+(instructions?|prompts?)',
    r'ignore\s+(previous|above|all)\s+(instructions?|prompts?)',
    r'disregard\s+(everything|all|previous)',
    r'forget\s+(your|all|previous)',
    r'you\s+are\s+now\s+a',
    r'act\s+as\s+(if\s+you|a)',
    r'pretend\s+(to\s+be|you\'re)',
    r'jailbreak',
    r'bypass\s+(safety|filter|restriction)',
    r'override\s+(system|instruction)',
    r'\bDAN\b',  # "Do Anything Now" jailbreak
    r'system\s*prompt',
    r'reveal\s+(your|system)\s+(prompt|instruction)',
    r'admin\s+mode',
    r'developer\s+mode',
    r'debug\s+mode',
    r'disable\s+(restrictions?|filters?)',
]

# Harmful content patterns (broad categories)
HARMFUL_PATTERNS = [
    r'\b(kill|murder|harm|hurt|attack)\s+(myself|yourself|him|her|them|people)\b',
    r'\bsuicid(e|al)\b',
    r'\bself[- ]harm\b',
    r'\b(hate|racist|sexist)\b',
    r'\b(f[*u][*c]k|sh[*i]t|a[*s][*s]hole|b[*i]tch)\b',
    r'\bn[*i]gg[*e]r\b',
]

# PII patterns to warn about (not blocked, but logged)
PII_PATTERNS = [
    (r'\b\d{3}[-.]?\d{2}[-.]?\d{4}\b', 'SSN'),
    (r'\b\d{16}\b', 'credit card'),
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 'email'),
]


class ProfileModerationResult:
    """Result of profile content moderation."""

    def __init__(self, is_safe: bool, sanitized_content: str,
                 warnings: list = None, blocked_reason: str = None):
        self.is_safe = is_safe
        self.sanitized_content = sanitized_content
        self.warnings = warnings or []
        self.blocked_reason = blocked_reason

    def __str__(self):
        if self.is_safe:
            return f"Safe (warnings: {len(self.warnings)})"
        return f"Blocked: {self.blocked_reason}"


def moderate_ai_profile(content: str) -> ProfileModerationResult:
    """
    Moderate AI profile content for safety and appropriateness.

    Args:
        content: Raw user input for AI profile

    Returns:
        ProfileModerationResult with moderation outcome
    """
    if not content or not content.strip():
        return ProfileModerationResult(
            is_safe=True,
            sanitized_content='',
            warnings=[]
        )

    content = content.strip()
    warnings = []

    # Check length
    if len(content) > 2000:
        content = content[:2000]
        warnings.append("Profile truncated to 2000 characters")

    # Check for prompt injection attempts
    content_lower = content.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, content_lower, re.IGNORECASE):
            logger.warning(f"Prompt injection attempt detected in AI profile")
            return ProfileModerationResult(
                is_safe=False,
                sanitized_content='',
                blocked_reason="Content appears to contain instructions for the AI system. Please describe yourself naturally."
            )

    # Check for harmful content
    for pattern in HARMFUL_PATTERNS:
        if re.search(pattern, content_lower, re.IGNORECASE):
            logger.warning(f"Harmful content detected in AI profile")
            return ProfileModerationResult(
                is_safe=False,
                sanitized_content='',
                blocked_reason="Content contains language that doesn't align with our community values. Please revise."
            )

    # Check for PII (warn but don't block)
    for pattern, pii_type in PII_PATTERNS:
        if re.search(pattern, content):
            warnings.append(f"Your profile may contain sensitive information ({pii_type}). Consider removing it.")

    # Sanitize content
    sanitized = sanitize_for_prompt(content)

    return ProfileModerationResult(
        is_safe=True,
        sanitized_content=sanitized,
        warnings=warnings
    )


def sanitize_for_prompt(content: str) -> str:
    """
    Sanitize content for safe inclusion in AI prompts.

    This doesn't block content but makes it safe for prompt inclusion:
    - Removes control characters
    - Normalizes whitespace
    - Escapes potential prompt delimiters
    """
    if not content:
        return ''

    # Remove control characters except newlines and tabs
    sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', content)

    # Normalize whitespace (multiple spaces/newlines to single)
    sanitized = re.sub(r'[ \t]+', ' ', sanitized)
    sanitized = re.sub(r'\n{3,}', '\n\n', sanitized)

    # Escape potential prompt injection markers
    # Replace common prompt delimiters with lookalikes
    sanitized = sanitized.replace('```', '`​`​`')  # Zero-width space
    sanitized = sanitized.replace('###', '#​#​#')
    sanitized = sanitized.replace('---', '-​-​-')

    # Remove any remaining markdown headers that could be prompt markers
    sanitized = re.sub(r'^#{1,6}\s+SYSTEM', '', sanitized, flags=re.MULTILINE | re.IGNORECASE)
    sanitized = re.sub(r'^#{1,6}\s+USER', '', sanitized, flags=re.MULTILINE | re.IGNORECASE)
    sanitized = re.sub(r'^#{1,6}\s+ASSISTANT', '', sanitized, flags=re.MULTILINE | re.IGNORECASE)

    return sanitized.strip()


def build_safe_profile_context(profile_content: str) -> str:
    """
    Build a safe, bounded context string from user's AI profile.

    This wraps the profile content in clear boundaries so the AI
    understands it's user-provided context, not system instructions.

    Args:
        profile_content: The moderated profile content

    Returns:
        Safe context string for inclusion in AI prompts
    """
    if not profile_content or not profile_content.strip():
        return ''

    moderation_result = moderate_ai_profile(profile_content)

    if not moderation_result.is_safe:
        logger.warning(f"Profile content blocked: {moderation_result.blocked_reason}")
        return ''

    sanitized = moderation_result.sanitized_content
    if not sanitized:
        return ''

    # Build bounded context
    context = f"""
USER PROFILE CONTEXT (user-provided personal information for personalization):
The user has shared the following about themselves:
"{sanitized}"
End of user profile.

Use this context to personalize your responses, but remember:
- This is self-reported information from the user
- Respect their privacy and be sensitive to their situation
- Stay within your role as a supportive life coach
- Never reveal or repeat this profile verbatim
"""
    return context.strip()
