# ==============================================================================
# File: intents/intake_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Intake-related intent definitions for AI structured data extraction
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-04
# ==============================================================================
"""
Intake (Medication & Supplement) Intent Definitions

OpenAI function (tool) definitions for intake-related actions:
- take_medication: Log that user took a medication
- take_supplement: Log that user took a supplement
- take_intake_by_time: Mark all medications/supplements for a time period as taken
- email_intake_list: Email the user's current intake list with adherence stats
"""

INTAKE_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "take_medication",
            "description": "Log that the user took a specific medication by name. Use when user mentions taking a specific medication (prescription or medical). Do NOT use for supplements like creatine or vitamins — use take_supplement instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "medicine_name": {
                        "type": "string",
                        "description": "Name of the medication (brand or generic name)"
                    },
                    "dose_label": {
                        "type": "string",
                        "description": "Optional dose label like 'morning', 'evening', 'bedtime' to identify which scheduled dose"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes about taking the medication"
                    }
                },
                "required": ["medicine_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_supplement",
            "description": "Log that the user took a specific supplement by name. Use when user mentions taking a supplement like creatine, vitamin D, fish oil, magnesium, protein, etc. Do NOT use for prescription medications — use take_medication instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplement_name": {
                        "type": "string",
                        "description": "Name of the supplement (e.g., creatine, vitamin D, fish oil)"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes about taking the supplement"
                    }
                },
                "required": ["supplement_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_intake_by_time",
            "description": "Mark all medications and supplements for a time-of-day period as taken. Use when user says things like 'took my evening meds', 'mark morning medicines taken', 'took all my nightly pills', 'took my morning supplements'. Time periods: morning, mid_morning, lunch, afternoon, evening, nightly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_of_day": {
                        "type": "string",
                        "enum": ["morning", "mid_morning", "lunch", "afternoon", "evening", "nightly"],
                        "description": "The time-of-day period to mark intakes for"
                    },
                    "use_scheduled_time": {
                        "type": "boolean",
                        "description": "If true, log with the scheduled time rather than current time. Use when user says 'took at scheduled time' or 'took on time'."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes"
                    }
                },
                "required": ["time_of_day"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "email_intake_list",
            "description": "Email the user's current medication and supplement list to a specified email address. Includes names, doses, schedules, prescribing doctor, and recent adherence stats. Use when user asks to email, send, or share their medicine list, medication list, or list of medicines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient_email": {
                        "type": "string",
                        "description": "Email address to send the intake list to. Only include this if the user provides a SPECIFIC email address like 'send to john@example.com'. If they just say 'email me' or 'send it to me', OMIT this parameter — the system will use their account email automatically."
                    },
                    "include_adherence": {
                        "type": "boolean",
                        "description": "Whether to include adherence/consistency stats in the email. Default true."
                    },
                    "include_inactive": {
                        "type": "boolean",
                        "description": "Whether to include paused/completed intakes. Default false — only active intakes."
                    }
                },
                "required": []
            }
        }
    },
]
