"""
Management command to populate default choice categories and options.

Usage:
    python manage.py populate_choices
"""

from django.core.management.base import BaseCommand
from apps.core.models import ChoiceCategory, ChoiceOption


class Command(BaseCommand):
    help = 'Populate the database with default choice categories and options'

    def handle(self, *args, **options):
        categories_data = [
            {
                "slug": "mood",
                "name": "Mood",
                "description": "Mood options for journal entries",
                "app_label": "journal",
                "is_system": True,
                "options": [
                    {"value": "happy", "label": "Happy 😊", "icon": "😊", "color": "#10b981", "sort_order": 1},
                    {"value": "grateful", "label": "Grateful 🙏", "icon": "🙏", "color": "#8b5cf6", "sort_order": 2},
                    {"value": "calm", "label": "Calm 😌", "icon": "😌", "color": "#06b6d4", "sort_order": 3},
                    {"value": "anxious", "label": "Anxious 😰", "icon": "😰", "color": "#f59e0b", "sort_order": 4},
                    {"value": "sad", "label": "Sad 😢", "icon": "😢", "color": "#6366f1", "sort_order": 5},
                    {"value": "angry", "label": "Angry 😠", "icon": "😠", "color": "#ef4444", "sort_order": 6},
                    {"value": "tired", "label": "Tired 😴", "icon": "😴", "color": "#64748b", "sort_order": 7},
                    {"value": "energetic", "label": "Energetic ⚡", "icon": "⚡", "color": "#eab308", "sort_order": 8},
                    {"value": "hopeful", "label": "Hopeful 🌟", "icon": "🌟", "color": "#f97316", "sort_order": 9},
                    {"value": "neutral", "label": "Neutral 😐", "icon": "😐", "color": "#9ca3af", "sort_order": 10, "is_default": True},
                ]
            },
            {
                "slug": "milestone_type",
                "name": "Milestone Type",
                "description": "Types of faith milestones",
                "app_label": "faith",
                "is_system": True,
                "options": [
                    {"value": "salvation", "label": "Accepted Christ", "icon": "✝️", "color": "#a855f7", "sort_order": 1},
                    {"value": "baptism", "label": "Baptism", "icon": "💧", "color": "#06b6d4", "sort_order": 2},
                    {"value": "rededication", "label": "Rededication", "icon": "🔄", "color": "#8b5cf6", "sort_order": 3},
                    {"value": "answered_prayer", "label": "Answered Prayer", "icon": "🙏", "color": "#10b981", "sort_order": 4},
                    {"value": "spiritual_insight", "label": "Spiritual Insight", "icon": "💡", "color": "#f59e0b", "sort_order": 5},
                    {"value": "community", "label": "Church/Community Moment", "icon": "⛪", "color": "#6366f1", "sort_order": 6},
                    {"value": "other", "label": "Other", "icon": "📝", "color": "#64748b", "sort_order": 99, "is_default": True},
                ]
            },
            {
                "slug": "prayer_priority",
                "name": "Prayer Priority",
                "description": "Priority levels for prayer requests",
                "app_label": "faith",
                "is_system": True,
                "options": [
                    {"value": "normal", "label": "Normal", "icon": "", "color": "#6366f1", "sort_order": 1, "is_default": True},
                    {"value": "urgent", "label": "Urgent", "icon": "🔥", "color": "#ef4444", "sort_order": 2},
                ]
            },
            {
                "slug": "scripture_translation",
                "name": "Scripture Translation",
                "description": "Bible translation options",
                "app_label": "faith",
                "is_system": True,
                "options": [
                    {"value": "ESV", "label": "English Standard Version", "sort_order": 1, "is_default": True},
                    {"value": "NIV", "label": "New International Version", "sort_order": 2},
                    {"value": "BSB", "label": "Berean Standard Bible", "sort_order": 3},
                    {"value": "NKJV", "label": "New King James Version", "sort_order": 4},
                    {"value": "NLT", "label": "New Living Translation", "sort_order": 5},
                    {"value": "KJV", "label": "King James Version", "sort_order": 6},
                ]
            },
            {
                "slug": "health_metric_type",
                "name": "Health Metric Type",
                "description": "Types of health measurements",
                "app_label": "health",
                "is_system": True,
                "options": [
                    {"value": "weight", "label": "Weight", "icon": "⚖️", "color": "#6366f1", "sort_order": 1},
                    {"value": "blood_pressure", "label": "Blood Pressure", "icon": "💓", "color": "#ef4444", "sort_order": 2},
                    {"value": "heart_rate", "label": "Heart Rate", "icon": "❤️", "color": "#f43f5e", "sort_order": 3},
                    {"value": "blood_sugar", "label": "Blood Sugar", "icon": "🩸", "color": "#f59e0b", "sort_order": 4},
                    {"value": "sleep_hours", "label": "Sleep Hours", "icon": "😴", "color": "#8b5cf6", "sort_order": 5},
                    {"value": "water_intake", "label": "Water Intake", "icon": "💧", "color": "#06b6d4", "sort_order": 6},
                    {"value": "steps", "label": "Steps", "icon": "👟", "color": "#10b981", "sort_order": 7},
                    {"value": "calories", "label": "Calories", "icon": "🔥", "color": "#f97316", "sort_order": 8},
                ]
            },
            {
                "slug": "exercise_type",
                "name": "Exercise Type",
                "description": "Types of exercise activities",
                "app_label": "health",
                "is_system": True,
                "options": [
                    {"value": "walking", "label": "Walking", "icon": "🚶", "color": "#10b981", "sort_order": 1},
                    {"value": "running", "label": "Running", "icon": "🏃", "color": "#ef4444", "sort_order": 2},
                    {"value": "cycling", "label": "Cycling", "icon": "🚴", "color": "#f59e0b", "sort_order": 3},
                    {"value": "swimming", "label": "Swimming", "icon": "🏊", "color": "#06b6d4", "sort_order": 4},
                    {"value": "weights", "label": "Weight Training", "icon": "🏋️", "color": "#6366f1", "sort_order": 5},
                    {"value": "yoga", "label": "Yoga", "icon": "🧘", "color": "#8b5cf6", "sort_order": 6},
                    {"value": "sports", "label": "Sports", "icon": "⚽", "color": "#22c55e", "sort_order": 7},
                    {"value": "other", "label": "Other", "icon": "💪", "color": "#64748b", "sort_order": 99},
                ]
            },
        ]

        for cat_data in categories_data:
            options_data = cat_data.pop('options', [])

            category, created = ChoiceCategory.objects.update_or_create(
                slug=cat_data["slug"],
                defaults=cat_data
            )

            action = "Created" if created else "Updated"
            self.stdout.write(f"{action} category: {category.name}")

            for opt_data in options_data:
                opt_data['is_active'] = True
                option, opt_created = ChoiceOption.objects.update_or_create(
                    category=category,
                    value=opt_data["value"],
                    defaults=opt_data
                )
                opt_action = "+" if opt_created else "~"
                self.stdout.write(f"  {opt_action} {option.label}")

        self.stdout.write(
            self.style.SUCCESS(f"\nDone! Total categories: {ChoiceCategory.objects.count()}")
        )
