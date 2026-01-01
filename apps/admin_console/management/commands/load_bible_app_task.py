# ==============================================================================
# File: apps/admin_console/management/commands/load_bible_app_task.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Load Bible App Updates tasks into ClaudeTask queue
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================
"""
Management command to load the Bible App Updates phase tasks.
Safe to run multiple times - checks for existing tasks first.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.admin_console.models import ClaudeTask


class Command(BaseCommand):
    help = "Load Bible App Updates tasks into ClaudeTask queue"

    def get_next_task_number(self):
        """Get the next available task number."""
        last_task = ClaudeTask.objects.order_by('-task_number').first()
        return (last_task.task_number + 1) if last_task else 1

    def handle(self, *args, **options):
        self.stdout.write("Loading Bible App tasks...")
        self.stdout.write(f"Current task count: {ClaudeTask.objects.count()}")
        created_count = 0
        skipped_count = 0

        # Define all tasks
        tasks = [
            {
                'title': 'Bible App Phase 1: Bible Reading + Study Tools',
                'status': ClaudeTask.STATUS_COMPLETE,
                'priority': ClaudeTask.PRIORITY_MEDIUM,
                'category': ClaudeTask.CATEGORY_FEATURE,
                'description': (
                    "Add Bible reading plans and study tools to help users build "
                    "consistent Scripture engagement habits.\n\n"
                    "Reading Plans:\n"
                    "- Browse and start reading plans on topics like forgiveness, "
                    "prayer, stress, marriage\n"
                    "- Track daily progress with reflections for each day\n"
                    "- Pause/Resume/Abandon functionality\n"
                    "- Featured plans and topic filtering\n\n"
                    "Study Tools:\n"
                    "- Highlight verses in different colors (yellow, green, blue, "
                    "pink, purple, orange)\n"
                    "- Bookmark passages to return to\n"
                    "- Create in-depth study notes with tagging"
                ),
                'acceptance_criteria': (
                    "- Reading plans browsable at /faith/reading-plans/\n"
                    "- Can start a plan and track progress\n"
                    "- Study tools accessible at /faith/study-tools/\n"
                    "- Highlights, bookmarks, and notes can be created/edited/deleted\n"
                    "- Navigation menu updated with Reading Plans and Study Tools links\n"
                    "- All tests pass"
                ),
                'notes': (
                    "Deployed 2026-01-01:\n"
                    "- 7 new models: ReadingPlanTemplate, ReadingPlanDay, "
                    "UserReadingPlan, UserReadingProgress, BibleHighlight, "
                    "BibleBookmark, BibleStudyNote\n"
                    "- 6 pre-loaded reading plans\n"
                    "- Study tools for highlights (6 colors), bookmarks, and notes\n"
                    "- 20+ new views, 11 templates\n"
                    "- Navigation updated\n"
                    "- All 1395 tests pass"
                ),
                'completed_at': timezone.now(),
                'completion_notes': 'Phase 1 fully deployed. Reading plans and study tools working.',
                'search_key': 'Phase 1',
            },
            {
                'title': 'Bible App Phase 2: Prayer Prompts Before Bible Study',
                'status': ClaudeTask.STATUS_NEW,
                'priority': ClaudeTask.PRIORITY_MEDIUM,
                'category': ClaudeTask.CATEGORY_FEATURE,
                'description': (
                    "Add prayer prompts that appear before starting a Bible study "
                    "session.\n\n"
                    "When a user begins a reading plan day or opens study tools, "
                    "offer an optional prayer moment to prepare their heart for "
                    "Scripture reading.\n\n"
                    "Features:\n"
                    "- Optional prayer prompt modal before study sessions\n"
                    "- Pre-written prayers the user can read along with\n"
                    "- Option to write their own prayer\n"
                    "- \"Don't show again\" preference\n"
                    "- Smooth transition into Bible reading after prayer"
                ),
                'acceptance_criteria': (
                    "- Prayer prompt appears when starting a reading plan day\n"
                    "- User can choose to pray, skip, or disable prompts\n"
                    "- Pre-written prayers available for selection\n"
                    "- User preference saved for future sessions\n"
                    "- Smooth UX that doesn't feel intrusive"
                ),
                'search_key': 'Phase 2',
            },
            {
                'title': 'Bible App Phase 3: Background Worship Music + Voice Narration',
                'status': ClaudeTask.STATUS_NEW,
                'priority': ClaudeTask.PRIORITY_MEDIUM,
                'category': ClaudeTask.CATEGORY_FEATURE,
                'description': (
                    "Add ambient worship music and voice narration options for "
                    "Bible reading.\n\n"
                    "Background Music:\n"
                    "- Soft instrumental worship music plays during Bible reading\n"
                    "- Volume controls and mute option\n"
                    "- Multiple music options/playlists\n\n"
                    "Voice Narration:\n"
                    "- Text-to-speech or pre-recorded audio for Scripture passages\n"
                    "- Play/pause/speed controls\n"
                    "- Option to listen while following along visually"
                ),
                'acceptance_criteria': (
                    "- Background music plays during reading sessions\n"
                    "- User can control volume, mute, or disable\n"
                    "- Voice narration available for Scripture text\n"
                    "- Audio controls are intuitive and accessible\n"
                    "- Works on mobile browsers"
                ),
                'search_key': 'Phase 3',
            },
            {
                'title': 'Bible App Phase 4: Interactive Q&A / AI Help',
                'status': ClaudeTask.STATUS_NEW,
                'priority': ClaudeTask.PRIORITY_MEDIUM,
                'category': ClaudeTask.CATEGORY_FEATURE,
                'description': (
                    "Add AI-powered Q&A for Bible study assistance.\n\n"
                    "Features:\n"
                    "- Ask questions about the current passage\n"
                    "- Get explanations of difficult verses\n"
                    "- Historical/cultural context on demand\n"
                    "- Cross-references and related passages\n"
                    "- Study suggestions based on current reading\n\n"
                    "Integration with existing AI service (OpenAI GPT-4o-mini)."
                ),
                'acceptance_criteria': (
                    "- Q&A button/panel available during Bible reading\n"
                    "- User can ask questions and get helpful answers\n"
                    "- Context-aware responses based on current passage\n"
                    "- Cross-references provided when relevant\n"
                    "- Follows existing AI service patterns"
                ),
                'search_key': 'Phase 4',
            },
            {
                'title': 'Bible App Phase 5: Learning Tools (Characters, Topics, Media)',
                'status': ClaudeTask.STATUS_NEW,
                'priority': ClaudeTask.PRIORITY_LOW,
                'category': ClaudeTask.CATEGORY_FEATURE,
                'description': (
                    "Add learning resources to enrich Bible study.\n\n"
                    "Features:\n"
                    "- Bible character profiles (Abraham, Moses, David, Paul, etc.)\n"
                    "- Topical verse collections (love, faith, hope, wisdom, etc.)\n"
                    "- Audio/video content integration\n"
                    "- Maps and visual aids\n"
                    "- Historical timeline\n\n"
                    "Content can be curated or sourced from public domain resources."
                ),
                'acceptance_criteria': (
                    "- Character profiles accessible and informative\n"
                    "- Topical verse collections browsable\n"
                    "- Audio/video content playable in-app\n"
                    "- Maps and visual aids display properly\n"
                    "- Resources linked from relevant reading plan days"
                ),
                'search_key': 'Phase 5',
            },
            {
                'title': 'Bible App Phase 6: AR/Immersive Experiences',
                'status': ClaudeTask.STATUS_NEW,
                'priority': ClaudeTask.PRIORITY_LOW,
                'category': ClaudeTask.CATEGORY_IDEA,
                'description': (
                    "Future: Add augmented reality and immersive experiences for "
                    "Bible study.\n\n"
                    "Potential Features:\n"
                    "- AR overlays for physical Bibles\n"
                    "- Virtual tours of Biblical locations\n"
                    "- 3D models of Temple, Ark, etc.\n"
                    "- Immersive story experiences\n"
                    "- VR compatibility\n\n"
                    "Note: This is a long-term goal requiring significant research "
                    "and potentially native app development."
                ),
                'acceptance_criteria': (
                    "- Research AR/VR web technologies\n"
                    "- Proof of concept for one immersive experience\n"
                    "- Works on AR-capable devices\n"
                    "- Graceful fallback for unsupported devices"
                ),
                'notes': (
                    "This phase is exploratory and may require native app "
                    "development rather than web-only."
                ),
                'search_key': 'Phase 6',
            },
        ]

        # Create each task
        for task_data in tasks:
            search_key = task_data.pop('search_key')

            # Check if task already exists
            if ClaudeTask.objects.filter(
                title__icontains=search_key,
                title__icontains='Bible'
            ).exists():
                self.stdout.write(f"  Skipped: {search_key} (already exists)")
                skipped_count += 1
                continue

            try:
                # Explicitly set task_number
                task_data['task_number'] = self.get_next_task_number()
                task_data['source'] = ClaudeTask.SOURCE_USER
                task_data['session_label'] = 'Bible App Updates'

                task = ClaudeTask.objects.create(**task_data)
                self.stdout.write(self.style.SUCCESS(
                    f"  Created: {task.task_id} - {search_key}"
                ))
                created_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"  ERROR creating {search_key}: {str(e)}"
                ))

        # Summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Bible App Tasks: {created_count} created, {skipped_count} skipped"
        ))
        self.stdout.write(f"Total tasks now: {ClaudeTask.objects.count()}")
