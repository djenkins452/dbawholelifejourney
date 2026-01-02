# ==============================================================================
# File: apps/admin_console/management/commands/load_project_from_json.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to load projects and tasks from JSON files
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================
"""
Load a project and its tasks from a JSON file with full executable task validation.

Usage:
    python manage.py load_project_from_json <path_to_json>

The JSON file must have the following structure:
{
    "project": {
        "name": "Project Name",
        "description": "Project description"
    },
    "tasks": [
        {
            "phase": "Phase 1",
            "name": "Task title",
            "description": {
                "objective": "...",
                "inputs": ["..."],
                "actions": ["..."],
                "output": "..."
            },
            "priority": "High|Medium|Low",
            "status": "New|...",
            "effort": "Small|Medium|Large",
            "allow_out_of_phase": false
        }
    ]
}
"""

import json
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.admin_console.models import (
    AdminProject, AdminProjectPhase, AdminTask,
    AdminTaskStatusConfig, AdminTaskPriorityConfig,
    AdminTaskCategoryConfig, AdminTaskEffortConfig,
    ExecutableTaskValidationError, validate_executable_task_description
)


# Priority mapping from JSON to database values
PRIORITY_MAP = {
    'High': 1,
    'Medium': 3,
    'Low': 5,
}

# Effort mapping from JSON to database values
EFFORT_MAP = {
    'Small': 'S',
    'Low': 'S',
    'Medium': 'M',
    'Large': 'L',
    'High': 'L',
}

# Status mapping from JSON to database values
STATUS_MAP = {
    'New': 'backlog',
    'Backlog': 'backlog',
    'Ready': 'ready',
    'In Progress': 'in_progress',
    'Blocked': 'blocked',
    'Done': 'done',
}


class Command(BaseCommand):
    help = 'Load a project and its tasks from a JSON file with executable task validation'

    def add_arguments(self, parser):
        parser.add_argument(
            'json_file',
            type=str,
            help='Path to the JSON file containing the project definition'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Validate the file without creating records'
        )

    def handle(self, *args, **options):
        json_path = options['json_file']
        dry_run = options['dry_run']

        self.stdout.write(f"Loading project from: {json_path}")

        # Read and parse JSON file
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f"File not found: {json_path}")
        except json.JSONDecodeError as e:
            raise CommandError(f"Invalid JSON: {e}")

        # Validate structure
        if 'project' not in data:
            raise CommandError("JSON must have a 'project' key")
        if 'tasks' not in data:
            raise CommandError("JSON must have a 'tasks' key")

        project_data = data['project']
        tasks_data = data['tasks']

        # Validate project fields
        if 'name' not in project_data:
            raise CommandError("Project must have a 'name'")

        self.stdout.write(f"Project: {project_data['name']}")
        self.stdout.write(f"Tasks to load: {len(tasks_data)}")

        # First pass: validate all tasks before creating anything
        self.stdout.write("\nValidating all tasks...")
        phases_needed = set()

        for i, task_data in enumerate(tasks_data, 1):
            task_name = task_data.get('name', f'Task {i}')
            self.stdout.write(f"  Validating: {task_name}")

            # Check required fields
            if 'name' not in task_data:
                raise CommandError(f"Task {i}: Missing 'name' field")
            if 'description' not in task_data:
                raise CommandError(f"Task {i} ({task_name}): Missing 'description' field")
            if 'phase' not in task_data:
                raise CommandError(f"Task {i} ({task_name}): Missing 'phase' field")

            # Validate executable task description
            description = task_data['description']
            try:
                validate_executable_task_description(description)
            except ExecutableTaskValidationError as e:
                errors = e.messages if hasattr(e, 'messages') else [str(e)]
                error_msg = "; ".join(errors)
                raise CommandError(
                    f"Task {i} ({task_name}): Executable task validation failed - {error_msg}"
                )

            # Track phases needed
            phase_str = task_data['phase']
            phases_needed.add(phase_str)

        self.stdout.write(self.style.SUCCESS(f"\nAll {len(tasks_data)} tasks validated successfully!"))
        self.stdout.write(f"Phases needed: {sorted(phases_needed)}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n--dry-run specified, no records created."))
            return

        # Create records in a transaction
        with transaction.atomic():
            # Create or get project
            project, created = AdminProject.objects.get_or_create(
                name=project_data['name'],
                defaults={
                    'description': project_data.get('description', ''),
                    'status': 'open'
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"\nCreated project: {project.name}"))
            else:
                self.stdout.write(f"\nUsing existing project: {project.name}")

            # Create or get phases
            phases = {}
            for phase_str in sorted(phases_needed):
                # Extract phase number from "Phase N" format
                try:
                    phase_num = int(phase_str.replace('Phase ', ''))
                except ValueError:
                    raise CommandError(f"Invalid phase format: {phase_str}. Expected 'Phase N'")

                phase, created = AdminProjectPhase.objects.get_or_create(
                    phase_number=phase_num,
                    defaults={
                        'name': phase_str,
                        'objective': f'Tasks for {phase_str}',
                        'status': 'not_started'
                    }
                )
                phases[phase_str] = phase
                if created:
                    self.stdout.write(f"  Created phase: {phase_str}")
                else:
                    self.stdout.write(f"  Using existing phase: {phase_str}")

            # Get or create config records
            status_config = AdminTaskStatusConfig.objects.filter(name='backlog', active=True).first()
            priority_configs = {c.value: c for c in AdminTaskPriorityConfig.objects.filter(active=True)}
            category_config = AdminTaskCategoryConfig.objects.filter(name='feature', active=True).first()
            effort_configs = {c.value: c for c in AdminTaskEffortConfig.objects.filter(active=True)}

            # Create tasks
            self.stdout.write(f"\nCreating tasks...")
            created_count = 0
            skipped_count = 0

            for task_data in tasks_data:
                task_name = task_data['name']
                phase = phases[task_data['phase']]

                # Check if task already exists
                existing = AdminTask.objects.filter(
                    title=task_name,
                    phase=phase,
                    project=project
                ).first()

                if existing:
                    self.stdout.write(f"  Skipped (exists): {task_name}")
                    skipped_count += 1
                    continue

                # Map values
                priority_str = task_data.get('priority', 'Medium')
                priority_val = PRIORITY_MAP.get(priority_str, 3)

                effort_str = task_data.get('effort', 'Medium')
                effort_val = EFFORT_MAP.get(effort_str, 'M')

                status_str = task_data.get('status', 'New')
                status_val = STATUS_MAP.get(status_str, 'backlog')

                # Create task
                task = AdminTask(
                    title=task_name,
                    description=task_data['description'],  # Already validated JSON
                    category='feature',
                    priority=priority_val,
                    status=status_val,
                    effort=effort_val,
                    phase=phase,
                    project=project,
                    created_by='claude',
                    # Config references
                    status_config=status_config,
                    priority_config=priority_configs.get(priority_val),
                    category_config=category_config,
                    effort_config=effort_configs.get(effort_val),
                )
                task.save()  # This will run full validation
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Created: {task_name}"))

        self.stdout.write(self.style.SUCCESS(
            f"\nDone! Created {created_count} tasks, skipped {skipped_count} existing."
        ))
