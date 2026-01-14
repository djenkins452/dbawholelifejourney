"""
Summarization service using OpenAI API for structured summaries.

This service handles transcript summarization for the Capture feature, creating
structured summaries using BLUF methodology (bottom line up front) with the
following sections:
- Overview (executive summary)
- Key Points
- Scripture References (if applicable)
- Action Items
- Notable Quotes
- Detailed Notes

Usage:
    from apps.capture.services import summarization_service

    # Summarize transcript and update the CaptureEntry
    result = summarization_service.summarize_transcript(capture_entry)

    if result['success']:
        print(f"Summary: {result['summary']}")
    else:
        print(f"Error: {result['error']}")
"""

import logging
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# Summarization prompt template (uses BLUF methodology with clean output headers)
BLUF_SYSTEM_PROMPT = """You are an expert summarizer that creates structured, actionable summaries from transcripts.

Your task is to analyze the provided transcript and create a well-organized summary in markdown format.

## Output Format

Create a summary with the following sections (use ## for section headers):

## Overview
A 2-3 sentence executive summary capturing the core message or main takeaway. Put the most important conclusion first.

## Key Points
- 3-5 bullet points highlighting the most important ideas
- Each point should be concise (1-2 sentences)
- Focus on actionable insights

## Scripture References
- List any Bible verses or religious texts mentioned
- Include the reference and brief context
- If no scripture is mentioned, write "No scripture references found in this recording."

## Action Items
- Specific actions the listener could take
- Practical next steps mentioned or implied
- If no clear action items, write "No specific action items identified."

## Notable Quotes
- 2-3 memorable or impactful quotes from the speaker
- Use quotation marks and keep them brief
- If no notable quotes, write "No notable quotes identified."

## Detailed Notes
A more comprehensive summary (3-5 paragraphs) covering:
- Main themes and arguments
- Supporting points and examples
- Context and background information

## Guidelines
- Be concise but thorough
- Maintain the speaker's intent and tone
- Use bullet points for lists
- Keep formatting consistent
- Do not add information not present in the transcript
"""

BLUF_USER_PROMPT_TEMPLATE = """Please summarize the following transcript into a structured summary:

---
TRANSCRIPT:
{transcript}
---

Create the summary following the format specified, with all required sections."""


class SummarizationError(Exception):
    """Custom exception for summarization errors."""

    def __init__(self, message: str, user_message: str = None):
        super().__init__(message)
        self.user_message = user_message or message


class SummarizationService:
    """Service for summarizing transcripts using OpenAI API."""

    def __init__(self):
        self.client = None
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        self._initialize_client()

    def _initialize_client(self):
        """Initialize OpenAI client if API key is available."""
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key)
            except ImportError:
                logger.warning("OpenAI package not installed. Run: pip install openai")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")

    @property
    def is_available(self) -> bool:
        """Check if summarization service is available."""
        return self.client is not None

    def summarize_transcript(self, capture_entry) -> dict:
        """
        Summarize transcript from a CaptureEntry and update its fields.

        Args:
            capture_entry: CaptureEntry model instance with transcript

        Returns:
            dict with keys:
                - success (bool): Whether summarization succeeded
                - summary (str): The summary text (if successful)
                - error (str): Error message (if failed)
        """
        from apps.capture.models import CaptureEntry

        if not self.is_available:
            error_msg = "Summarization service not available - OpenAI API key not configured"
            logger.warning(error_msg)
            capture_entry.status = CaptureEntry.STATUS_FAILED
            capture_entry.error_message = "Summarization service is temporarily unavailable. Please try again later."
            capture_entry.save(update_fields=['status', 'error_message'])
            return {'success': False, 'error': error_msg}

        if not capture_entry.transcript:
            error_msg = "No transcript provided"
            logger.error(f"CaptureEntry {capture_entry.id}: {error_msg}")
            capture_entry.status = CaptureEntry.STATUS_FAILED
            capture_entry.error_message = "No transcript available to summarize. Please try recording again."
            capture_entry.save(update_fields=['status', 'error_message'])
            return {'success': False, 'error': error_msg}

        try:
            logger.info(f"CaptureEntry {capture_entry.id}: Generating summary ({len(capture_entry.transcript)} chars)")
            summary = self._call_api(capture_entry.transcript)

            # Update CaptureEntry on success
            capture_entry.summary = summary
            capture_entry.status = CaptureEntry.STATUS_READY
            capture_entry.error_message = ''
            capture_entry.save(update_fields=['summary', 'status', 'error_message'])

            logger.info(f"CaptureEntry {capture_entry.id}: Summary complete, {len(summary)} characters")
            return {'success': True, 'summary': summary}

        except SummarizationError as e:
            logger.error(f"CaptureEntry {capture_entry.id}: Summarization error - {e}")
            capture_entry.status = CaptureEntry.STATUS_FAILED
            capture_entry.error_message = e.user_message
            capture_entry.save(update_fields=['status', 'error_message'])
            return {'success': False, 'error': str(e)}

        except Exception as e:
            logger.exception(f"CaptureEntry {capture_entry.id}: Unexpected error during summarization")
            capture_entry.status = CaptureEntry.STATUS_FAILED
            capture_entry.error_message = "An unexpected error occurred during summarization. Please try again."
            capture_entry.save(update_fields=['status', 'error_message'])
            return {'success': False, 'error': str(e)}

    def _call_api(self, transcript: str) -> str:
        """
        Call OpenAI API to generate summary.

        Args:
            transcript: The transcript text to summarize

        Returns:
            The generated summary as markdown

        Raises:
            SummarizationError: If API call fails
        """
        # Truncate very long transcripts to stay within token limits
        # GPT-4o-mini has 128k context, but we limit for cost/speed
        max_transcript_length = 100000  # ~25k tokens
        if len(transcript) > max_transcript_length:
            logger.info(f"Truncating transcript from {len(transcript)} to {max_transcript_length} chars")
            transcript = transcript[:max_transcript_length] + "\n\n[Transcript truncated due to length]"

        user_prompt = BLUF_USER_PROMPT_TEMPLATE.format(transcript=transcript)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": BLUF_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=4000,  # Sufficient for comprehensive summary
                temperature=0.3,  # Lower temperature for more consistent output
            )

            summary = response.choices[0].message.content.strip()

            if not summary:
                raise SummarizationError(
                    "OpenAI returned empty summary",
                    "Unable to generate summary. Please try again."
                )

            return summary

        except SummarizationError:
            raise
        except Exception as e:
            error_str = str(e).lower()

            # Handle specific OpenAI API errors
            if 'invalid_api_key' in error_str or 'authentication' in error_str:
                raise SummarizationError(
                    f"OpenAI API authentication failed: {e}",
                    "Summarization service is temporarily unavailable. Please try again later."
                )
            elif 'rate_limit' in error_str:
                raise SummarizationError(
                    f"OpenAI API rate limit exceeded: {e}",
                    "The summarization service is busy. Please wait a few minutes and try again."
                )
            elif 'context_length' in error_str or 'token' in error_str:
                raise SummarizationError(
                    f"Transcript too long for API: {e}",
                    "Your recording is too long to summarize. Please try a shorter recording."
                )
            else:
                raise SummarizationError(
                    f"OpenAI API error: {e}",
                    "Summarization failed. Please try again or contact support if the problem persists."
                )


# Singleton instance
summarization_service = SummarizationService()
