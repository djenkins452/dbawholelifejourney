# ==============================================================================
# File: intents/fitness_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Fitness-related intent definitions for AI structured data extraction
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-04
# ==============================================================================
"""
Fitness Intent Definitions

OpenAI function (tool) definitions for fitness-related actions:
- log_workout: Log a completed workout session
- log_exercise_set: Log a specific set during a workout
- log_cardio: Log cardio exercise
"""

FITNESS_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "log_workout",
            "description": "Log a completed workout session. Use when user mentions completing a workout, gym session, or exercise routine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the workout (e.g., 'Upper Body', 'Leg Day', 'Morning Run')"
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration of the workout in minutes"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Notes about how the workout went"
                    },
                    "exercises": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "sets": {"type": "integer"},
                                "reps": {"type": "integer"},
                                "weight": {"type": "number"}
                            }
                        },
                        "description": "List of exercises performed with sets/reps/weight"
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_exercise_set",
            "description": "Log a specific set of an exercise. Use when user mentions completing a set with weight and reps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise_name": {
                        "type": "string",
                        "description": "Name of the exercise (e.g., 'bench press', 'squats', 'deadlift')"
                    },
                    "weight": {
                        "type": "number",
                        "description": "Weight used (in pounds or kg based on user preference)"
                    },
                    "reps": {
                        "type": "integer",
                        "description": "Number of repetitions"
                    },
                    "set_number": {
                        "type": "integer",
                        "description": "Which set this is (1, 2, 3, etc.)"
                    },
                    "is_warmup": {
                        "type": "boolean",
                        "description": "Whether this is a warmup set"
                    },
                    "is_pr": {
                        "type": "boolean",
                        "description": "Whether this is a personal record"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Notes about the set"
                    }
                },
                "required": ["exercise_name", "weight", "reps"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_cardio",
            "description": "Log a cardio exercise session. Use when user mentions running, walking, cycling, swimming, or other cardio activities.",
            "parameters": {
                "type": "object",
                "properties": {
                    "activity": {
                        "type": "string",
                        "description": "Type of cardio (e.g., 'running', 'walking', 'cycling', 'swimming', 'elliptical')"
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration in minutes"
                    },
                    "distance": {
                        "type": "number",
                        "description": "Distance covered (miles or km based on preference)"
                    },
                    "distance_unit": {
                        "type": "string",
                        "enum": ["miles", "km"],
                        "description": "Unit for distance. Default to 'miles' for US users."
                    },
                    "intensity": {
                        "type": "string",
                        "enum": ["easy", "medium", "hard"],
                        "description": "Intensity level of the workout"
                    },
                    "calories_burned": {
                        "type": "integer",
                        "description": "Estimated calories burned if known"
                    },
                    "avg_heart_rate": {
                        "type": "integer",
                        "description": "Average heart rate during exercise if known"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Notes about the cardio session"
                    }
                },
                "required": ["activity", "duration_minutes"]
            }
        }
    },
]
