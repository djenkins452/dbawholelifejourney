# ==============================================================================
# File: intents/health_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Health-related intent definitions for AI structured data extraction
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-04
# ==============================================================================
"""
Health Intent Definitions

OpenAI function (tool) definitions for health-related actions:
- log_heart_rate: Record heart rate measurement
- log_blood_pressure: Record blood pressure reading
- log_weight: Record weight measurement
- log_glucose: Record blood glucose reading
- log_blood_oxygen: Record SpO2 measurement
- log_food: Record food consumption
"""

HEALTH_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "log_heart_rate",
            "description": "Log a heart rate measurement for the user. Use when user mentions their heart rate, pulse, or BPM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bpm": {
                        "type": "integer",
                        "description": "Heart rate in beats per minute (BPM)"
                    },
                    "context": {
                        "type": "string",
                        "enum": ["resting", "morning", "active", "post_exercise", "stressed", "relaxed", "other"],
                        "description": "Context of the measurement. Default to 'resting' if not specified."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes about the measurement"
                    }
                },
                "required": ["bpm"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_blood_pressure",
            "description": "Log a blood pressure reading for the user. Use when user mentions BP, blood pressure, or systolic/diastolic values.",
            "parameters": {
                "type": "object",
                "properties": {
                    "systolic": {
                        "type": "integer",
                        "description": "Systolic pressure (top number) in mmHg"
                    },
                    "diastolic": {
                        "type": "integer",
                        "description": "Diastolic pressure (bottom number) in mmHg"
                    },
                    "pulse": {
                        "type": "integer",
                        "description": "Pulse rate if measured with blood pressure"
                    },
                    "context": {
                        "type": "string",
                        "enum": ["resting", "morning", "evening", "post_exercise", "stressed", "relaxed", "other"],
                        "description": "Context of the measurement. Default to 'resting' if not specified."
                    },
                    "arm": {
                        "type": "string",
                        "enum": ["left", "right"],
                        "description": "Which arm was used. Default to 'left'."
                    },
                    "position": {
                        "type": "string",
                        "enum": ["sitting", "standing", "lying"],
                        "description": "Body position during measurement. Default to 'sitting'."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes about the measurement"
                    }
                },
                "required": ["systolic", "diastolic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_weight",
            "description": "Log a weight measurement for the user. Use when user mentions their weight, scale reading, or weighing themselves.",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "number",
                        "description": "Weight value"
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["lb", "kg"],
                        "description": "Unit of measurement. Default to 'lb' for US users."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes about the measurement"
                    },
                    "source_artifact_id": {
                        "type": "integer",
                        "description": "If this reading was extracted from an uploaded image/photo (e.g. a scale), the id of that artifact. Provides provenance and enables duplicate detection."
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Your confidence (0.0-1.0) in the value when read from an image. Provide it whenever source_artifact_id is set so WLJ can decide whether to confirm."
                    }
                },
                "required": ["value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_glucose",
            "description": "Log a blood glucose (blood sugar) reading for the user. Use when user mentions glucose, blood sugar, sugar level, or BG.",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "number",
                        "description": "Glucose reading value"
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["mg/dL", "mmol/L"],
                        "description": "Unit of measurement. Default to 'mg/dL' for US users."
                    },
                    "context": {
                        "type": "string",
                        "enum": ["fasting", "before_meal", "after_meal", "bedtime", "random", "cgm"],
                        "description": "Context of the reading. 'fasting' if morning or before eating, 'after_meal' if after food."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes about the reading"
                    }
                },
                "required": ["value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_blood_oxygen",
            "description": "Log a blood oxygen (SpO2) reading for the user. Use when user mentions oxygen level, SpO2, O2 sat, or pulse oximeter reading.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spo2": {
                        "type": "integer",
                        "description": "Blood oxygen saturation percentage (e.g., 98 for 98%)"
                    },
                    "pulse": {
                        "type": "integer",
                        "description": "Pulse rate if measured with SpO2"
                    },
                    "context": {
                        "type": "string",
                        "enum": ["resting", "morning", "active", "post_exercise", "sleeping", "illness", "other"],
                        "description": "Context of the measurement. Default to 'resting' if not specified."
                    },
                    "measurement_method": {
                        "type": "string",
                        "enum": ["finger", "wrist", "ear", "other"],
                        "description": "How the measurement was taken. Default to 'finger'."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes about the measurement"
                    }
                },
                "required": ["spo2"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_food",
            "description": (
                "Log food/meal consumption for the user. Use when the user mentions "
                "eating, having a meal, or specific foods — including when they supply "
                "the nutrition themselves. PASS EVERY NUTRIENT THE USER STATES: values "
                "the user supplies are recorded EXACTLY as given and are never replaced "
                "by a database or estimated value. Omit a nutrient only when the user "
                "did not state it (WLJ may then fill it from a food match). Grams for "
                "macros, MILLIGRAMS for sodium.\n"
                "NUTRITION YOU DON'T HAVE: you CAN estimate calories and macros from "
                "nutrition knowledge — never tell the user you cannot. But do not invent "
                "numbers unasked: if the user just names a food and no match is found, log "
                "it (nutrition stays honestly UNKNOWN) OR offer a quick estimate. When the "
                "user ASKS FOR or ACCEPTS your best estimate, DO provide per-item estimates "
                "and pass them as calories/macros WITH `estimated: true`, so they are stored "
                "labelled as an estimate rather than as measured values or as zeroes. Assume "
                "one serving unless the user says otherwise. Apply this to ANY food — never "
                "single out particular items."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "food_name": {
                        "type": "string",
                        "description": "Name or description of the food item"
                    },
                    "quantity": {
                        "type": "number",
                        "description": "Number of servings or portions. Default to 1."
                    },
                    "meal_type": {
                        "type": "string",
                        "enum": ["breakfast", "lunch", "dinner", "snack"],
                        "description": "Type of meal. Infer from time of day if not specified."
                    },
                    "calories": {
                        "type": "number",
                        "description": "Calories, when the user states them or they are known"
                    },
                    "protein_g": {"type": "number",
                                  "description": "Protein in grams, if the user stated it"},
                    "carbohydrates_g": {"type": "number",
                                        "description": "Carbohydrates in grams, if stated"},
                    "fiber_g": {"type": "number",
                                "description": "Fiber in grams, if stated"},
                    "sugar_g": {"type": "number",
                                "description": "Sugar in grams, if stated"},
                    "fat_g": {"type": "number",
                              "description": "Total fat in grams, if stated"},
                    "saturated_fat_g": {"type": "number",
                                        "description": "Saturated fat in grams, if stated"},
                    "sodium_mg": {"type": "number",
                                  "description": "Sodium in MILLIGRAMS, if stated"},
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes about the food"
                    },
                    "estimated": {
                        "type": "boolean",
                        "description": ("True if the calories/macros are YOUR best estimate "
                                        "(the user asked for or accepted an estimate), not "
                                        "values they stated — stored labelled as an estimate.")
                    },
                    "items": {
                        "type": "array",
                        "description": (
                            "SEVERAL FOODS IN ONE REQUEST. When the user names more than "
                            "one food ('a sandwich and mac and cheese for lunch'), call "
                            "this ONCE with every food as an item — never once per food. "
                            "One call is one authorization covering the whole set, and "
                            "each food is then logged as its own entry. Each item takes "
                            "the same fields as a single food; `meal_type` given at the "
                            "top level applies to every item that does not state its own."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "food_name": {"type": "string"},
                                "quantity": {"type": "number"},
                                "meal_type": {
                                    "type": "string",
                                    "enum": ["breakfast", "lunch", "dinner", "snack"]},
                                "calories": {"type": "number"},
                                "protein_g": {"type": "number"},
                                "carbohydrates_g": {"type": "number"},
                                "fiber_g": {"type": "number"},
                                "sugar_g": {"type": "number"},
                                "fat_g": {"type": "number"},
                                "saturated_fat_g": {"type": "number"},
                                "sodium_mg": {"type": "number"},
                                "notes": {"type": "string"},
                                "estimated": {"type": "boolean"},
                            },
                            "required": ["food_name"],
                        },
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_sleep",
            "description": "Log sleep data for the user. Use when user mentions how they slept, hours of sleep, bedtime, wake time, or sleep quality.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {
                        "type": "number",
                        "description": "Total hours of sleep (e.g., 7.5). Can be decimal."
                    },
                    "quality": {
                        "type": "string",
                        "enum": ["excellent", "good", "fair", "poor", "terrible"],
                        "description": "Sleep quality rating. Infer from user's description if not explicit."
                    },
                    "bedtime": {
                        "type": "string",
                        "description": "When they went to bed (e.g., '10:30 PM', '22:30'). Optional."
                    },
                    "wake_time": {
                        "type": "string",
                        "description": "When they woke up (e.g., '6:00 AM', '06:00'). Optional."
                    },
                    "interruptions": {
                        "type": "integer",
                        "description": "Number of times woke up during the night. Optional."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes about sleep (e.g., 'couldn't fall asleep', 'vivid dreams')"
                    }
                },
                "required": ["hours"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_water",
            "description": "Log water or hydration intake. Use when user mentions drinking water, glasses of water, hydration, or fluid intake.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "Amount of water consumed"
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["oz", "ml", "cups", "liters"],
                        "description": "Unit of measurement. Default 'oz' for US users. 'cups' means 8oz cups."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes"
                    }
                },
                "required": ["amount"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_steps",
            "description": "Log daily step count. Use when user mentions steps walked, step count, or pedometer reading.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of steps"
                    },
                    "distance": {
                        "type": "number",
                        "description": "Distance walked in miles. Optional."
                    },
                    "calories": {
                        "type": "integer",
                        "description": "Active calories burned. Optional."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes"
                    }
                },
                "required": ["count"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_body_measurement",
            "description": "Log a body composition or measurement entry. Use when user mentions body fat, waist measurement, muscle mass, or any body measurement.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "enum": ["body_fat_pct", "lean_mass", "fat_mass", "skeletal_muscle_mass", "waist", "chest", "hips", "arm_left", "arm_right", "thigh_left", "thigh_right", "neck", "shoulders", "calf_left", "calf_right", "bone_mass", "body_water_pct", "visceral_fat", "bmr", "metabolic_age"],
                        "description": "Type of body measurement"
                    },
                    "value": {
                        "type": "number",
                        "description": "Measurement value"
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["pct", "lb", "kg", "in", "cm", "kcal", "years", "index"],
                        "description": "Unit of measurement. Infer from metric type (e.g., body_fat_pct uses 'pct', waist uses 'in')."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes"
                    }
                },
                "required": ["metric", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_body_measurements",
            "description": (
                "Import a COMPLETE set of body measurements captured together at one moment "
                "(a full body check-in) — for example when the user uploads a SCREENSHOT or "
                "PHOTO of a body-measurement app (Renpho Smart Tape, InBody, Withings, Garmin, "
                "Apple Health…), or reports several measurements at once ('my waist is 54.7, "
                "hips 47.2, chest 50.9'). Use THIS instead of calling log_body_measurement "
                "repeatedly — WLJ groups them into one measurement session. Read EVERY populated "
                "value from the source; skip any shown as blank / '--' / 0.00 (those are not "
                "measured). Do NOT include waist-hip ratio — WLJ derives that from waist and hips. "
                "Attach source_artifact_id and a per-measurement confidence (0-1) when the values "
                "were read from an uploaded image."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "measurements": {
                        "type": "array",
                        "description": "One item per populated measurement read from the source.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "metric": {
                                    "type": "string",
                                    "enum": ["neck", "shoulders", "chest", "waist", "abdomen", "hips", "arm_left", "arm_right", "forearm_left", "forearm_right", "thigh_left", "thigh_right", "calf_left", "calf_right", "body_fat_pct", "lean_mass", "fat_mass", "skeletal_muscle_mass", "bone_mass", "body_water_pct", "visceral_fat", "bmr", "metabolic_age", "bmi"],
                                    "description": "Canonical measurement name. Map vendor labels: L-Bicep→arm_left, R-Bicep→arm_right, Left forearm→forearm_left, Shoulder→shoulders, Hip→hips."
                                },
                                "value": {"type": "number", "description": "Measurement value"},
                                "unit": {
                                    "type": "string",
                                    "enum": ["in", "cm", "pct", "lb", "kg", "kcal", "years", "index"],
                                    "description": "Unit shown on the source (circumferences are usually 'in' or 'cm')."
                                },
                                "confidence": {
                                    "type": "number",
                                    "description": "0-1 confidence you read THIS value correctly; lower it for any uncertain value."
                                }
                            },
                            "required": ["metric", "value"]
                        }
                    },
                    "source": {
                        "type": "string",
                        "description": "Where the measurements came from, e.g. 'Renpho Screenshot', 'InBody', 'typed'."
                    },
                    "measured_at": {
                        "type": "string",
                        "description": "ISO 8601 timestamp shown on the source (when the measurements were taken). Omit to use now."
                    }
                },
                "required": ["measurements"]
            }
        }
    },
]

# Validation ranges for questioning unusual values (not hard rejections)
HEALTH_VALIDATION_RANGES = {
    'heart_rate': {
        'normal_min': 40,
        'normal_max': 180,
        'question_template': "{bpm} BPM is {status}. {context_question} Should I log it?"
    },
    'blood_pressure': {
        'systolic_min': 80,
        'systolic_max': 180,
        'diastolic_min': 50,
        'diastolic_max': 120,
        'question_template': "{systolic}/{diastolic} is {status}. {context_question} Should I log it?"
    },
    'weight': {
        'normal_min': 80,
        'normal_max': 400,
        'question_template': "{value} {unit} seems {status}. Is this correct?"
    },
    'glucose': {
        'normal_min': 50,
        'normal_max': 300,
        'question_template': "{value} {unit} is {status}. {context_question} Should I log it?"
    },
    'blood_oxygen': {
        'normal_min': 90,
        'normal_max': 100,
        'question_template': "{spo2}% SpO2 is {status}. Are you feeling okay? Should I log it?"
    }
}
