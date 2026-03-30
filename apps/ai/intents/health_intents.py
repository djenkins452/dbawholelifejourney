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
            "description": "Log food consumption for the user. Use when user mentions eating, having a meal, or specific foods.",
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
                        "description": "Estimated calories if known or mentioned (can be decimal, e.g. 712.5)"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes about the food"
                    }
                },
                "required": ["food_name"]
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
