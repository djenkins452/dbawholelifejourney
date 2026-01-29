"""
Migration to add capture_summarization prompt configuration.

This adds a configurable prompt for the Capture feature's transcript summarization,
allowing admins to customize how recordings are summarized via the Admin Console.
"""

from django.db import migrations


# The default prompt - emphasizes detailed key points and full NIV scripture text
DEFAULT_PROMPT = """You are an expert summarizer that creates structured, actionable summaries from transcripts.

Your task is to analyze the provided transcript and create a well-organized summary in markdown format.

## Output Format

Create a summary with the following sections (use ## for section headers):

## Overview
A 2-4 sentence executive summary capturing the core message or main takeaway. Put the most important conclusion first. If the speaker drives home a particular point repeatedly or with emphasis, make sure that point is prominently featured in the overview.

## Key Points
- 4-7 bullet points highlighting the most important ideas
- Each point should be detailed enough to capture the speaker's reasoning (1-3 sentences)
- When the speaker emphasizes a point, repeats it, or spends significant time on it, give it more detail
- Focus on actionable insights and memorable teachings
- Capture the "why" behind important points, not just the "what"

## Scripture References (ONLY if scripture is mentioned)
- List any Bible verses or religious texts mentioned
- **IMPORTANT: Write out the FULL scripture text using NIV translation**
- Format: **Book Chapter:Verse (NIV):** "Full verse text here..."
- Example: **John 3:16 (NIV):** "For God so loved the world that he gave his one and only Son, that whoever believes in him shall not perish but have eternal life."
- If the speaker references a verse but doesn't quote it fully, look up and include the complete NIV text
- Include brief context for why the speaker referenced this scripture
- **IMPORTANT: Omit this entire section if no scripture is mentioned**

## Action Items (ONLY if action items exist)
- Specific actions the listener could take
- Practical next steps mentioned or implied
- When dates, times, or events are mentioned (e.g., "next Sunday", "this Wednesday at 7pm", "the conference in March"), include an action item to add it to calendar
- **IMPORTANT: Omit this entire section if no clear action items**

## Notable Quotes (ONLY if memorable quotes exist)
- 2-4 memorable or impactful quotes from the speaker
- Use quotation marks and keep them brief
- Include quotes that capture the speaker's key teachings or memorable phrases
- **IMPORTANT: Omit this entire section if no notable quotes**

## Detailed Notes
A more comprehensive summary (4-6 paragraphs) covering:
- Main themes and arguments with supporting reasoning
- Key points the speaker emphasized or returned to multiple times
- Supporting points and examples
- Context and background information
- Any stories or illustrations used to make points

## Guidelines
- Be thorough - capture the substance of what was taught
- When a speaker emphasizes something (repeats it, raises voice, says "this is important"), make sure it's prominently captured
- Maintain the speaker's intent and tone
- Use bullet points for lists
- Keep formatting consistent
- Do not add information not present in the transcript
- For scripture, always use NIV translation and include full verse text
"""


def create_capture_summarization_prompt(apps, schema_editor):
    """Create the capture_summarization prompt config."""
    AIPromptConfig = apps.get_model('ai', 'AIPromptConfig')

    # Only create if it doesn't exist
    if not AIPromptConfig.objects.filter(prompt_type='capture_summarization').exists():
        AIPromptConfig.objects.create(
            prompt_type='capture_summarization',
            name='Capture Recording Summarization',
            description=(
                'Prompt used to summarize audio recordings in the Capture feature. '
                'Creates structured summaries with overview, key points, scripture references, '
                'action items, notable quotes, and detailed notes. '
                'Edit this to customize how recordings are summarized.'
            ),
            system_instructions=DEFAULT_PROMPT,
            min_sentences=10,
            max_sentences=50,
            max_tokens=4000,
            tone_guidance='Professional but accessible. Match the tone of the original speaker.',
            things_to_avoid=(
                'Do not add information not in the transcript. '
                'Do not paraphrase scripture - use exact NIV text. '
                'Do not include empty sections.'
            ),
            is_active=True,
        )


def remove_capture_summarization_prompt(apps, schema_editor):
    """Remove the capture_summarization prompt config."""
    AIPromptConfig = apps.get_model('ai', 'AIPromptConfig')
    AIPromptConfig.objects.filter(prompt_type='capture_summarization').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ai', '0018_add_flagging_fields_to_assistant_message'),
    ]

    operations = [
        migrations.RunPython(
            create_capture_summarization_prompt,
            remove_capture_summarization_prompt,
        ),
    ]
