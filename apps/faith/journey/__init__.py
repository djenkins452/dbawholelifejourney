"""
Walking With God Through Scripture — Journey feature.

Isolated submodule under apps/faith. Registered as its own Django app
(`apps.faith.journey`, label `journey`) to keep migrations, admin, and
models separate from the existing reading-plan system.

See docs/CLAUDE_WALKING_WITH_GOD.md for the full spec.
"""

default_app_config = "apps.faith.journey.apps.JourneyConfig"
