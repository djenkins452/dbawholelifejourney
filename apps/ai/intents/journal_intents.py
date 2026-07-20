# ==============================================================================
# File: intents/journal_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Journal-related intent definitions for AI structured data extraction
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-04
# ==============================================================================
"""
Journal Intent Definitions

OpenAI function (tool) definitions for journal-related actions:
- create_journal_entry: Create a new journal entry
- add_gratitude: Log gratitude (shorthand for gratitude journal)
"""

JOURNAL_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_journal_entry",
            "description": "Create a new journal entry for the user. Use when user wants to write, journal, reflect, or document their thoughts, experiences, or feelings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title for the journal entry. Generate a brief, meaningful title if not provided."
                    },
                    "body": {
                        "type": "string",
                        "description": "The main content of the journal entry - what the user wants to write about."
                    },
                    "mood": {
                        "type": "string",
                        "enum": ["great", "good", "okay", "low", "difficult"],
                        "description": "The user's current mood. Infer from content if not explicitly stated."
                    },
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Categories for the entry (e.g., 'gratitude', 'reflection', 'goals', 'prayer')"
                    }
                },
                "required": ["body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "import_journal_entries",
            "description": (
                "Import a journal that contains MANY entries at once (a historical journal "
                "export, a Day One / Evernote / Apple Notes export, or a pasted multi-day "
                "journal). Use THIS — not create_journal_entry repeatedly — when one source "
                "holds several dated entries; WLJ shows the user a preview and imports them as "
                "separate entries only after they confirm.\n"
                "IF THE JOURNAL WAS UPLOADED AS A FILE: just call this with source_artifact_id "
                "and an EMPTY entries list. WLJ reads the document itself and determines every "
                "entry's date, time, boundary, and skipped state DETERMINISTICALLY from the "
                "document's own date headers. Do NOT transcribe or normalize the dates yourself, "
                "and do NOT guess — WLJ owns the dates. (This exists because a model-transcribed "
                "date can be wrong; the document is the source of truth.)\n"
                "ONLY when the journal was TYPED directly into the chat (no file) should you "
                "provide `entries`: one entry per date, the ORIGINAL body verbatim (never "
                "rewritten), date as ISO YYYY-MM-DD, time as 24-hour HH:MM (omit if none), and "
                "skipped=true for a day the user marks skipped."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entries": {
                        "type": "array",
                        "description": "One item per journal entry (and per explicitly-skipped day) recognized in the document.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entry_date": {
                                    "type": "string",
                                    "description": "The entry's date, normalized to ISO YYYY-MM-DD (resolve 2-digit years to the full year shown in the document)."
                                },
                                "entry_time": {
                                    "type": "string",
                                    "description": "The entry's clock time in 24-hour HH:MM, if the source shows one. Omit when there is no time."
                                },
                                "body": {
                                    "type": "string",
                                    "description": "The COMPLETE original entry text, verbatim. Preserve paragraphs with blank lines. Never rewrite, summarize, or add section headings."
                                },
                                "skipped": {
                                    "type": "boolean",
                                    "description": "True when the source explicitly marks this day as skipped / no entry. Include such days so the user sees them; WLJ will not create an entry for them."
                                }
                            },
                            "required": ["entry_date"]
                        }
                    },
                    "source": {
                        "type": "string",
                        "description": "A short label for where the entries came from, e.g. 'journal document', 'Day One export'."
                    },
                    "source_artifact_id": {
                        "type": "string",
                        "description": "REQUIRED when the journal was uploaded as a file — WLJ reads the entries/dates from that document. Provide `entries` instead only for a journal typed directly into the chat."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_gratitude",
            "description": "Log something the user is grateful for. Use when user expresses thankfulness or wants to record gratitude.",
            "parameters": {
                "type": "object",
                "properties": {
                    "gratitude": {
                        "type": "string",
                        "description": "What the user is grateful for"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why they're grateful for this (optional context)"
                    }
                },
                "required": ["gratitude"]
            }
        }
    },
]
