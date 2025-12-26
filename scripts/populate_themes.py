"""
Data migration to populate initial themes.

Run this after the Theme model migration:
    python manage.py shell < scripts/populate_themes.py

Or run it as a Django management command.
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.core.models import Theme

# Define the themes (matching what was in settings.py)
THEMES = [
    {
        "slug": "minimal",
        "name": "Minimal / Life Focus",
        "description": "Clean and focused, perfect for daily journaling",
        "sort_order": 1,
        "is_active": True,
        "is_default": True,
        # Light mode
        "color_primary": "#6b7280",
        "color_secondary": "#f9fafb",
        "color_accent": "#6366f1",
        "color_text": "#374151",
        "color_text_muted": "#6b7280",
        "color_background": "#ffffff",
        "color_surface": "#f3f4f6",
        "color_border": "#e5e7eb",
        # Dark mode
        "dark_color_primary": "#9ca3af",
        "dark_color_secondary": "#111827",
        "dark_color_accent": "#818cf8",
        "dark_color_text": "#f9fafb",
        "dark_color_text_muted": "#9ca3af",
        "dark_color_background": "#030712",
        "dark_color_surface": "#1f2937",
        "dark_color_border": "#374151",
    },
    {
        "slug": "faith",
        "name": "Faith / Scripture Focus",
        "description": "Warm and reverent, ideal for spiritual reflection",
        "sort_order": 2,
        "is_active": True,
        "is_default": False,
        # Light mode
        "color_primary": "#78716c",
        "color_secondary": "#fafaf9",
        "color_accent": "#a855f7",
        "color_text": "#44403c",
        "color_text_muted": "#78716c",
        "color_background": "#ffffff",
        "color_surface": "#f5f5f4",
        "color_border": "#e7e5e4",
        # Dark mode
        "dark_color_primary": "#a8a29e",
        "dark_color_secondary": "#1c1917",
        "dark_color_accent": "#c084fc",
        "dark_color_text": "#fafaf9",
        "dark_color_text_muted": "#a8a29e",
        "dark_color_background": "#0c0a09",
        "dark_color_surface": "#292524",
        "dark_color_border": "#44403c",
    },
    {
        "slug": "wellness",
        "name": "Wellness / Health Focus",
        "description": "Fresh and energizing for health tracking",
        "sort_order": 3,
        "is_active": True,
        "is_default": False,
        # Light mode
        "color_primary": "#059669",
        "color_secondary": "#f0fdf4",
        "color_accent": "#10b981",
        "color_text": "#064e3b",
        "color_text_muted": "#047857",
        "color_background": "#ffffff",
        "color_surface": "#ecfdf5",
        "color_border": "#d1fae5",
        # Dark mode
        "dark_color_primary": "#34d399",
        "dark_color_secondary": "#022c22",
        "dark_color_accent": "#10b981",
        "dark_color_text": "#ecfdf5",
        "dark_color_text_muted": "#6ee7b7",
        "dark_color_background": "#022c22",
        "dark_color_surface": "#064e3b",
        "dark_color_border": "#047857",
    },
    {
        "slug": "ocean",
        "name": "Ocean Blue",
        "description": "Calm and serene, like the sea",
        "sort_order": 4,
        "is_active": True,
        "is_default": False,
        # Light mode
        "color_primary": "#0369a1",
        "color_secondary": "#f0f9ff",
        "color_accent": "#0ea5e9",
        "color_text": "#0c4a6e",
        "color_text_muted": "#0369a1",
        "color_background": "#ffffff",
        "color_surface": "#e0f2fe",
        "color_border": "#bae6fd",
        # Dark mode
        "dark_color_primary": "#38bdf8",
        "dark_color_secondary": "#082f49",
        "dark_color_accent": "#0ea5e9",
        "dark_color_text": "#f0f9ff",
        "dark_color_text_muted": "#7dd3fc",
        "dark_color_background": "#082f49",
        "dark_color_surface": "#0c4a6e",
        "dark_color_border": "#0369a1",
    },
    {
        "slug": "sunset",
        "name": "Sunset Warmth",
        "description": "Warm oranges and soft pinks",
        "sort_order": 5,
        "is_active": True,
        "is_default": False,
        # Light mode
        "color_primary": "#ea580c",
        "color_secondary": "#fff7ed",
        "color_accent": "#f97316",
        "color_text": "#7c2d12",
        "color_text_muted": "#c2410c",
        "color_background": "#ffffff",
        "color_surface": "#ffedd5",
        "color_border": "#fed7aa",
        # Dark mode
        "dark_color_primary": "#fb923c",
        "dark_color_secondary": "#431407",
        "dark_color_accent": "#f97316",
        "dark_color_text": "#fff7ed",
        "dark_color_text_muted": "#fdba74",
        "dark_color_background": "#431407",
        "dark_color_surface": "#7c2d12",
        "dark_color_border": "#c2410c",
    },
    {
        "slug": "lavender",
        "name": "Lavender Dreams",
        "description": "Soft and calming purple tones",
        "sort_order": 6,
        "is_active": True,
        "is_default": False,
        # Light mode
        "color_primary": "#7c3aed",
        "color_secondary": "#f5f3ff",
        "color_accent": "#8b5cf6",
        "color_text": "#4c1d95",
        "color_text_muted": "#6d28d9",
        "color_background": "#ffffff",
        "color_surface": "#ede9fe",
        "color_border": "#ddd6fe",
        # Dark mode
        "dark_color_primary": "#a78bfa",
        "dark_color_secondary": "#2e1065",
        "dark_color_accent": "#8b5cf6",
        "dark_color_text": "#f5f3ff",
        "dark_color_text_muted": "#c4b5fd",
        "dark_color_background": "#2e1065",
        "dark_color_surface": "#4c1d95",
        "dark_color_border": "#6d28d9",
    },
]


def populate_themes():
    """Create or update themes in the database."""
    created_count = 0
    updated_count = 0
    
    for theme_data in THEMES:
        theme, created = Theme.objects.update_or_create(
            slug=theme_data["slug"],
            defaults=theme_data
        )
        if created:
            created_count += 1
            print(f"  Created: {theme.name}")
        else:
            updated_count += 1
            print(f"  Updated: {theme.name}")
    
    print(f"\nDone! Created {created_count}, updated {updated_count} themes.")
    print(f"Total active themes: {Theme.objects.filter(is_active=True).count()}")


if __name__ == "__main__":
    print("Populating themes...")
    populate_themes()