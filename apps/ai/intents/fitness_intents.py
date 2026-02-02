# ==============================================================================
# File: intents/fitness_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Fitness-related intent definitions for AI structured data extraction
# Owner: Danny Jenkins (admin@wholelifejourney.com)
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
            "description": """Log a workout session with exercises. Use this function when the user:

COMPLETED EXERCISES (most common - trigger on ANY of these patterns):
- Lists exercises they did: "I did 10 pushups", "did 20 squats", "I did pushups, situps, and squats"
- Reports reps/sets: "I did 3 sets of 10 pushups", "just did 50 crunches", "knocked out 100 jumping jacks"
- Uses past tense with exercises: "did my pushups", "finished my squats", "got in some lunges"
- Mentions exercise counts: "10 pushups, 10 situps, 10 squats", "20 burpees and 30 mountain climbers"

FINISHED A WORKOUT:
- "Just finished my workout", "done with my workout", "completed my workout"
- "Just got back from the gym", "finished at the gym", "done at the gym"
- "Finished lifting", "done with weights", "finished training"
- "Wrapped up my exercise", "finished exercising"

WORKOUT IN PROGRESS OR JUST DONE:
- "Just worked out", "I worked out", "got my workout in"
- "Hit the gym", "went to the gym", "was at the gym"
- "Did my exercises", "got my exercises done", "finished my exercises"
- "Crushed my workout", "killed it at the gym", "had a great workout"
- "Got my sweat on", "put in work", "trained today"

SPECIFIC WORKOUT TYPES:
- "Did leg day", "finished arm day", "completed chest day", "did back day"
- "Did upper body", "finished lower body", "did full body"
- "Did my strength training", "finished resistance training"
- "Did HIIT", "finished circuit training", "did CrossFit"
- "Did calisthenics", "finished bodyweight workout"

CASUAL/INFORMAL:
- "Worked out this morning", "exercised today", "trained this afternoon"
- "Got some exercise in", "squeezed in a workout"
- "Did a quick workout", "had a light workout", "did an easy workout"
- "Had a tough workout", "brutal workout today", "intense session"

LISTING WHAT THEY DID:
- Any message listing exercises with numbers (reps) should trigger this
- "10 pushups and 10 situps" = workout with 2 exercises
- "pushups, squats, lunges" = workout with 3 exercises
- "bench press 3x10" = workout with bench press, 3 sets of 10 reps

Generate a descriptive name based on the exercises mentioned (e.g., "Bodyweight Workout", "Upper Body", "Quick Core Session").""",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the workout - generate based on exercises if not specified (e.g., 'Bodyweight Workout', 'Upper Body', 'Leg Day', 'Quick Core Session', 'Morning Strength')"
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration of the workout in minutes if mentioned"
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
                                "name": {"type": "string", "description": "Exercise name (e.g., 'pushups', 'squats', 'bench press')"},
                                "sets": {"type": "integer", "description": "Number of sets (default to 1 if just reps given)"},
                                "reps": {"type": "integer", "description": "Number of reps per set"},
                                "weight": {"type": "number", "description": "Weight used if mentioned (in lbs or kg)"}
                            }
                        },
                        "description": "List of exercises performed - extract from user message"
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
            "description": """Log a specific set of a weighted exercise during a workout. Use when user reports a SINGLE SET with weight.

WHEN TO USE (weighted exercises with specific set info):
- "Just did 185 on bench for 8 reps", "benched 225 for 5"
- "Hit 315 on squat for 3", "squatted 225x8"
- "Deadlifted 405 for 5 reps", "pulled 365x3"
- "Did 135 on overhead press for 10"
- "Set 2: 185 for 8 reps", "third set: 200x6"
- "Warmup set: 135x10", "working set: 185x5"
- "Log 10 reps of bench press at 185"
- "Just hit a PR - 225 for 8 on bench!"
- "New personal record: 315 squat for 5"

WEIGHT FORMATS TO RECOGNIZE:
- "185 lbs", "185 pounds", "185#" = 185 pounds
- "100 kg", "100 kilos" = 100 kilograms
- Just a number like "225" = assume pounds for US users
- "bodyweight" or "BW" = note it, no weight number

REP FORMATS:
- "for 8 reps", "for 8", "x8", "8 reps"
- "225x5" = 225 lbs for 5 reps
- "3x10 at 135" = interpret as 3 sets of 10 (use log_workout instead)

PR/PERSONAL RECORD:
- "PR", "personal record", "new max", "hit a new max"
- "best ever", "lifetime PR", "all-time best"

DO NOT USE for bodyweight exercises without weight (use log_workout instead):
- "did 20 pushups" → use log_workout
- "50 situps" → use log_workout""",
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise_name": {
                        "type": "string",
                        "description": "Name of the exercise (e.g., 'bench press', 'squat', 'deadlift', 'overhead press', 'barbell row')"
                    },
                    "weight": {
                        "type": "number",
                        "description": "Weight used in pounds (convert kg to lbs if needed: kg * 2.2)"
                    },
                    "reps": {
                        "type": "integer",
                        "description": "Number of repetitions completed"
                    },
                    "set_number": {
                        "type": "integer",
                        "description": "Which set this is (1, 2, 3, etc.) if mentioned"
                    },
                    "is_warmup": {
                        "type": "boolean",
                        "description": "True if user says 'warmup', 'warm-up', or 'warming up'"
                    },
                    "is_pr": {
                        "type": "boolean",
                        "description": "True if user mentions PR, personal record, new max, best ever"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional context (felt easy, was hard, form notes, etc.)"
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
            "description": """Log a cardio/aerobic exercise session. Use for any cardiovascular activity.

RUNNING/JOGGING:
- "Went for a run", "just ran", "finished my run", "got a run in"
- "Ran 3 miles", "did a 5k", "ran for 30 minutes"
- "Jogged around the neighborhood", "went jogging"
- "Morning run", "evening run", "quick run"
- "Did a tempo run", "easy run today", "long run"
- "Ran on the treadmill", "treadmill run"
- "Trail run", "ran the trails"

WALKING:
- "Went for a walk", "took a walk", "walked today"
- "Walked 2 miles", "walked for an hour"
- "Morning walk", "evening walk", "lunch walk"
- "Power walked", "brisk walk", "leisurely walk"
- "Walked the dog", "walked around the block"
- "Did my steps", "got my steps in", "hit 10k steps"

CYCLING/BIKING:
- "Went for a bike ride", "rode my bike", "cycled today"
- "Biked 10 miles", "rode for an hour"
- "Spin class", "did spinning", "indoor cycling"
- "Stationary bike", "bike trainer", "Peloton ride"
- "Mountain biking", "road cycling"

SWIMMING:
- "Went swimming", "swam today", "did laps"
- "Swam for 30 minutes", "pool workout"
- "Swam a mile", "did 20 laps"

OTHER CARDIO:
- "Did the elliptical", "elliptical for 30 minutes"
- "Rowing machine", "rowed for 20 minutes", "did the erg"
- "Stairmaster", "stair climber", "climbed stairs"
- "Jump rope", "jumped rope for 15 minutes", "skipping rope"
- "Did cardio", "cardio session", "cardio day"
- "Aerobics class", "Zumba", "dance class"
- "Hiking", "went hiking", "hiked 5 miles"
- "Boxing", "kickboxing", "cardio kickboxing"

INTENSITY PHRASES:
- Easy: "easy", "light", "recovery", "leisurely", "casual"
- Medium: "moderate", "steady", "comfortable", "normal pace"
- Hard: "hard", "intense", "tough", "pushed it", "all out", "sprint", "intervals"

TIME/DISTANCE FORMATS:
- "30 minutes", "half hour", "an hour", "45 min"
- "3 miles", "5k", "10k", "half marathon", "marathon"
- "3 km", "5 kilometers"

METRICS (if mentioned):
- Calories: "burned 300 calories", "300 cal"
- Heart rate: "average HR 145", "heart rate was 150"
- Pace: "9 minute miles", "8:30 pace\"""",
            "parameters": {
                "type": "object",
                "properties": {
                    "activity": {
                        "type": "string",
                        "description": "Type of cardio activity (running, walking, cycling, swimming, elliptical, rowing, hiking, jump rope, stairmaster, etc.)"
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration in minutes (convert hours: 1 hour = 60, 1.5 hours = 90)"
                    },
                    "distance": {
                        "type": "number",
                        "description": "Distance covered if mentioned"
                    },
                    "distance_unit": {
                        "type": "string",
                        "enum": ["miles", "km"],
                        "description": "Unit for distance - default 'miles' for US users, 'km' if user says km/kilometers"
                    },
                    "intensity": {
                        "type": "string",
                        "enum": ["easy", "medium", "hard"],
                        "description": "Intensity level based on user's description"
                    },
                    "calories_burned": {
                        "type": "integer",
                        "description": "Calories burned if user mentions it"
                    },
                    "avg_heart_rate": {
                        "type": "integer",
                        "description": "Average heart rate if user mentions it"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional context (weather, how they felt, route, etc.)"
                    }
                },
                "required": ["activity", "duration_minutes"]
            }
        }
    },
]
