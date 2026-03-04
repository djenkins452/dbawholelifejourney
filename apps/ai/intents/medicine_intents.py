# ==============================================================================
# File: intents/medicine_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Medicine-related intent definitions for AI structured data extraction
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-04
# ==============================================================================
"""
Medicine Intent Definitions

OpenAI function (tool) definitions for medicine-related actions:
- take_medicine: Log that user took a medicine
- take_medicines_by_time: Mark all medicines for a time period as taken
- email_medicine_list: Email the user's current medicine list with adherence stats
"""

MEDICINE_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "take_medicine",
            "description": "Log that the user took a specific medicine by name. Use when user mentions taking a specific medication by name.",
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
            "name": "take_medicines_by_time",
            "description": "Mark all medicines for a time-of-day period as taken. Use when user says things like 'took my evening meds', 'mark morning medicines taken', 'took all my nightly pills', 'I took my two evening medicines'. Time periods: morning, mid_morning, lunch, afternoon, evening, nightly.",
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
                        "description": "Email address to send the medicine list to. If the user says 'email me' or 'send it to me' without specifying, use their account email."
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
                "required": ["recipient_email"]
            }
        }
    },
]
