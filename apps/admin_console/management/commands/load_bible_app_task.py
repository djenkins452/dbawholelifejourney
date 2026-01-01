# ==============================================================================
# File: apps/admin_console/management/commands/load_bible_app_task.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Load Bible App Updates task into ClaudeTask queue
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================
"""
Management command to load the Bible App Updates multi-phase task.
Safe to run multiple times - checks for existing task first.
"""

from django.core.management.base import BaseCommand

from apps.admin_console.models import ClaudeTask


class Command(BaseCommand):
    help = "Load Bible App Updates task into ClaudeTask queue"

    def handle(self, *args, **options):
        # Check if task already exists
        existing = ClaudeTask.objects.filter(
            title__icontains='Bible App Updates'
        ).first()

        if existing:
            self.stdout.write(
                self.style.WARNING(
                    f"Task already exists: {existing.task_id} - {existing.title}"
                )
            )
            self.stdout.write(f"  Current Phase: {existing.current_phase}")
            self.stdout.write(f"  Status: {existing.status}")
            return

        # Create the task
        task = ClaudeTask.objects.create(
            title='Bible App Updates - Multi-Phase Feature',
            status=ClaudeTask.STATUS_IN_PROGRESS,
            priority=ClaudeTask.PRIORITY_MEDIUM,
            category=ClaudeTask.CATEGORY_FEATURE,
            description=(
                "Major enhancement to the Faith module adding Bible reading "
                "and study features.\n\n"
                "Goal: Help users build consistent Scripture engagement habits through:\n"
                "- Guided reading plans on various topics\n"
                "- Study tools (highlights, bookmarks, notes)\n"
                "- Prayer integration before study\n"
                "- Interactive AI help\n"
                "- Learning tools (character profiles, topical verses)\n"
                "- Future: AR/immersive experiences"
            ),
            acceptance_criteria=(
                "Phase 1: Reading plans browsable and startable, study tools functional\n"
                "Phase 2: Prayer prompts appear before Bible study sessions\n"
                "Phase 3: Background worship music plays, voice narration available\n"
                "Phase 4: AI Q&A works for Bible questions\n"
                "Phase 5: Character profiles, topical verses, audio/video content accessible\n"
                "Phase 6: AR features work on supported devices"
            ),
            phases=(
                "Phase 1: Bible Reading + Study Tools (COMPLETE)\n"
                "Phase 2: Prayer prompts before Bible study\n"
                "Phase 3: Background worship music with voice narration\n"
                "Phase 4: Interactive Q&A / AI Help\n"
                "Phase 5: Learning Tools (character profiles, topical verses, audio/video)\n"
                "Phase 6: AR/Immersive experiences"
            ),
            current_phase=1,
            source=ClaudeTask.SOURCE_USER,
            session_label='Bible App Updates',
            notes=(
                "Phase 1 deployed 2026-01-01:\n"
                "- 7 new models (ReadingPlanTemplate, ReadingPlanDay, UserReadingPlan, "
                "UserReadingProgress, BibleHighlight, BibleBookmark, BibleStudyNote)\n"
                "- 6 pre-loaded reading plans\n"
                "- Study tools for highlights (6 colors), bookmarks, and notes\n"
                "- Navigation updated with Reading Plans and Study Tools links\n"
                "- All 1395 tests pass"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created: {task.task_id} - {task.title}"
            )
        )
        self.stdout.write(f"  Current Phase: {task.current_phase}")
        self.stdout.write(f"  Total Phases: {task.total_phases}")
        self.stdout.write(f"  Status: {task.status}")
