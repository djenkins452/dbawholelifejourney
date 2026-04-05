# ==============================================================================
# File: intents/medicine_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Medicine-related intent definitions for AI structured data extraction
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-04
# ==============================================================================
"""
Medicine & Supplement Intent Definitions

OpenAI function (tool) definitions for medicine/supplement-related actions:
- take_medicine: Log that user took a medication
- take_supplement: Log that user took a supplement
- take_medicines_by_time: Mark all medicines/supplements for a time period as taken
- email_medicine_list: Email the user's current medicine list with adherence stats
"""

MEDICINE_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "take_medicine",
            "description": "Log that the user took a specific medication by name. Use when user mentions taking a specific medication (prescription or medical). Do NOT use for supplements like creatine or vitamins — use take_supplement instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "medicine_name": {
                        "type": "string",
                        "description": "Name of the medicine (brand or generic name)"
                    },
                    "dose_label": {
                        "type": "string",
                        "description": "Optional dose label like 'morning', 'evening', 'bedtime' to identify which scheduled dose"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes about taking the medicine"
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
            "description": "Log that the user took a specific supplement by name. Use when user mentions taking a supplement like creatine, vitamin D, fish oil, magnesium, protein, etc. Do NOT use for prescription medications — use take_medicine instead.",
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
            "name": "take_medicines_by_time",
            "description": "Mark all medicines and supplements for a time-of-day period as taken. Use when user says things like 'took my evening meds', 'mark morning medicines taken', 'took all my nightly pills', 'took my morning supplements'. Time periods: morning, mid_morning, lunch, afternoon, evening, nightly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_of_day": {
                        "type": "string",
                        "enum": ["morning", "mid_morning", "lunch", "afternoon", "evening", "nightly"],
                        "description": "The time-of-day period to mark medicines for"
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
            "name": "email_medicine_list",
            "description": "Email the user's current medicine list to a specified email address. Includes medicine names, doses, schedules, prescribing doctor, and recent adherence stats. Use when user asks to email, send, or share their medicine list, medication list, or list of medicines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient_email": {
                        "type": "string",
                        "description": "Email address to send the medicine list to. Only include this if the user provides a SPECIFIC email address like 'send to john@example.com'. If they just say 'email me' or 'send it to me', OMIT this parameter — the system will use their account email automatically."
                    },
                    "include_adherence": {
                        "type": "boolean",
                        "description": "Whether to include adherence/consistency stats in the email. Default true."
                    },
                    "include_inactive": {
                        "type": "boolean",
                        "description": "Whether to include paused/completed medicines. Default false — only active medicines."
                    }
                },
                "required": []
            }
        }
    },
]
