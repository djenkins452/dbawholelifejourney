# ==============================================================================
# File: apps/core/management/decorators.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Decorators for management commands to add error reporting
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================
"""
Management Command Decorators

Provides decorators to enhance management commands with:
- Automatic error reporting via email
- Execution timing
- Logging

Usage:
    from apps.core.management.decorators import notify_on_error

    class Command(BaseCommand):
        @notify_on_error
        def handle(self, *args, **options):
            # Your command logic
            pass
"""

import functools
import time
import traceback
from typing import Any, Callable

from django.conf import settings

from apps.core.security_logging import log_command_error


def notify_on_error(func: Callable) -> Callable:
    """
    Decorator for management command handle() methods.

    Catches any exception, logs it with full context, and sends
    an email notification to admins. Then re-raises the exception
    so Django's normal error handling continues.

    Usage:
        class Command(BaseCommand):
            @notify_on_error
            def handle(self, *args, **options):
                # Your command logic
                pass
    """
    @functools.wraps(func)
    def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        command_name = self.__class__.__module__.split('.')[-1]
        start_time = time.time()

        try:
            result = func(self, *args, **kwargs)
            elapsed = time.time() - start_time

            # Log successful completion
            if hasattr(self, 'stdout'):
                self.stdout.write(
                    f"Command {command_name} completed in {elapsed:.2f}s"
                )

            return result

        except Exception as e:
            elapsed = time.time() - start_time

            # Build context for error report
            context = {
                'elapsed_seconds': f"{elapsed:.2f}",
                'traceback': traceback.format_exc(),
                'args': str(args),
                'kwargs': str(kwargs),
                'debug_mode': settings.DEBUG,
            }

            # Log the error (this sends email notification)
            log_command_error(
                command_name=command_name,
                error=e,
                context=context,
            )

            # Re-raise so Django sees the failure
            raise

    return wrapper


def timed_command(func: Callable) -> Callable:
    """
    Decorator to time management command execution.

    Logs start/end times and elapsed duration.

    Usage:
        class Command(BaseCommand):
            @timed_command
            def handle(self, *args, **options):
                # Your command logic
                pass
    """
    @functools.wraps(func)
    def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        command_name = self.__class__.__module__.split('.')[-1]
        start_time = time.time()

        if hasattr(self, 'stdout'):
            self.stdout.write(f"Starting {command_name}...")

        try:
            result = func(self, *args, **kwargs)
            elapsed = time.time() - start_time

            if hasattr(self, 'stdout'):
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Completed {command_name} in {elapsed:.2f}s"
                    )
                )

            return result

        except Exception as e:
            elapsed = time.time() - start_time

            if hasattr(self, 'stderr'):
                self.stderr.write(
                    self.style.ERROR(
                        f"Failed {command_name} after {elapsed:.2f}s: {e}"
                    )
                )

            raise

    return wrapper
