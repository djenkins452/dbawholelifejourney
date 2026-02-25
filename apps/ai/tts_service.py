"""
TTS Service — Text-to-Speech for CoS Voice Output.

Converts CoS text responses to audio using OpenAI's TTS API.
Returns MP3 audio bytes for streaming or embedding.

Project: Whole Life Journey
Path: apps/ai/tts_service.py
"""

import base64
import logging
from typing import Optional, Tuple

from django.conf import settings

logger = logging.getLogger(__name__)

# Voice options for OpenAI TTS
VOICE_CHOICES = {
    "alloy": "Alloy (neutral, balanced)",
    "echo": "Echo (warm, male)",
    "fable": "Fable (expressive, storytelling)",
    "nova": "Nova (warm, female)",
    "onyx": "Onyx (authoritative, deep)",
    "shimmer": "Shimmer (clear, friendly)",
}

DEFAULT_VOICE = "nova"
DEFAULT_MODEL = "tts-1"  # "tts-1" (fast) or "tts-1-hd" (high quality)
MAX_INPUT_LENGTH = 4096  # OpenAI TTS limit


def generate_speech(
    text: str,
    voice: str = None,
    model: str = None,
    speed: float = 1.0,
) -> Optional[bytes]:
    """
    Generate speech audio from text using OpenAI TTS API.

    Args:
        text: Text to convert to speech (max 4096 chars).
        voice: Voice to use (alloy, echo, fable, nova, onyx, shimmer).
        model: TTS model (tts-1 for speed, tts-1-hd for quality).
        speed: Playback speed (0.25 to 4.0, default 1.0).

    Returns:
        MP3 audio bytes, or None on failure.
    """
    if not text or not text.strip():
        return None

    # Truncate to API limit
    if len(text) > MAX_INPUT_LENGTH:
        text = text[:MAX_INPUT_LENGTH]

    voice = voice or DEFAULT_VOICE
    model = model or DEFAULT_MODEL

    # Validate voice
    if voice not in VOICE_CHOICES:
        voice = DEFAULT_VOICE

    # Validate speed
    speed = max(0.25, min(4.0, speed))

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        response = client.audio.speech.create(
            model=model,
            voice=voice,
            input=text,
            speed=speed,
            response_format="mp3",
        )

        # Read the audio bytes from the streaming response
        audio_bytes = response.content
        if audio_bytes:
            logger.debug(
                "TTS: Generated %d bytes of audio (voice=%s, model=%s)",
                len(audio_bytes), voice, model,
            )
            return audio_bytes

        return None

    except Exception as e:
        logger.error("TTS: Speech generation failed: %s", e)
        return None


def generate_speech_base64(
    text: str,
    voice: str = None,
    model: str = None,
    speed: float = 1.0,
) -> Optional[str]:
    """
    Generate speech audio and return as base64-encoded string.

    Useful for embedding in JSON responses.

    Returns:
        Base64-encoded MP3 string, or None on failure.
    """
    audio_bytes = generate_speech(text, voice=voice, model=model, speed=speed)
    if audio_bytes:
        return base64.b64encode(audio_bytes).decode("ascii")
    return None


def get_audio_data_url(base64_audio: str) -> str:
    """Build a data URL from base64 audio for <audio> tag src."""
    return f"data:audio/mpeg;base64,{base64_audio}"


def get_user_tts_preferences(user) -> dict:
    """
    Get TTS preferences for a user.

    Returns dict with voice, model, speed, enabled status.
    Falls back to defaults if preferences don't exist.
    """
    defaults = {
        "enabled": False,
        "voice": DEFAULT_VOICE,
        "model": DEFAULT_MODEL,
        "speed": 1.0,
        "auto_play": False,
    }

    try:
        prefs = user.preferences
        defaults["enabled"] = getattr(prefs, "tts_enabled", False)
        defaults["voice"] = getattr(prefs, "tts_voice", DEFAULT_VOICE) or DEFAULT_VOICE
        defaults["speed"] = getattr(prefs, "tts_speed", 1.0) or 1.0
        defaults["auto_play"] = getattr(prefs, "tts_auto_play", False)
    except Exception:
        pass

    return defaults


def clean_text_for_speech(text: str) -> str:
    """
    Clean text for better TTS output.

    Removes markdown formatting, emoji, and other artifacts that
    sound unnatural when read aloud.
    """
    import re

    if not text:
        return ""

    # Remove markdown bold/italic
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)

    # Remove markdown headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Remove markdown bullet points (keep the text)
    text = re.sub(r'^\s*[-*•]\s+', '', text, flags=re.MULTILINE)

    # Remove numbered lists (keep text)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

    # Remove markdown links (keep text)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)

    # Remove emoji (common ranges)
    text = re.sub(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
        r'\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF'
        r'\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF'
        r'\U00002702-\U000027B0\U000024C2-\U0001F251]+',
        '', text,
    )

    # Collapse multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Collapse multiple spaces
    text = re.sub(r' {2,}', ' ', text)

    return text.strip()
