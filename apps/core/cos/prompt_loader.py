"""
Prompt Loader — Loads system prompt templates from external markdown files.

Project: Whole Life Journey
Path: apps/core/cos/prompt_loader.py
Purpose: Centralizes prompt file loading with caching and fallback support.
         Prompts live in /prompts/system/*.md for easy editing and version control.

Usage:
    from apps.core.cos.prompt_loader import load_prompt

    rules = load_prompt("cos_operational_rules")
    faith = load_prompt("faith_integration")

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# Cache for prompt contents — survives module lifetime
_prompt_cache: dict = {}


def _get_prompts_dir() -> Path:
    """Get the prompts/system/ directory path."""
    return Path(settings.BASE_DIR) / "prompts" / "system"


@lru_cache(maxsize=32)
def load_prompt(name: str, fallback: str = "") -> str:
    """
    Load a prompt template from prompts/system/{name}.md.

    Args:
        name: Prompt file name without extension (e.g., "cos_operational_rules")
        fallback: Default text if the file is missing

    Returns:
        Prompt text content, or fallback if file not found.

    Note:
        Results are cached via lru_cache. Call load_prompt.cache_clear()
        to force reload (useful after editing prompts in dev).
    """
    filepath = _get_prompts_dir() / f"{name}.md"

    try:
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8").strip()
            if content:
                logger.debug("Loaded prompt '%s' (%d chars)", name, len(content))
                return content
            else:
                logger.warning("Prompt file '%s' exists but is empty", name)
                return fallback
        else:
            if fallback:
                logger.debug(
                    "Prompt file '%s' not found, using fallback (%d chars)",
                    name, len(fallback)
                )
            else:
                logger.warning("Prompt file '%s' not found and no fallback provided", name)
            return fallback
    except Exception as e:
        logger.error("Error loading prompt '%s': %s", name, e, exc_info=True)
        return fallback


def reload_prompts():
    """Clear prompt cache, forcing reload on next access. Useful in development."""
    load_prompt.cache_clear()
    logger.info("Prompt cache cleared — prompts will reload on next access")


def list_available_prompts() -> list:
    """List all available prompt files in the prompts/system/ directory."""
    prompts_dir = _get_prompts_dir()
    if not prompts_dir.exists():
        return []
    return sorted(
        f.stem for f in prompts_dir.glob("*.md")
    )
