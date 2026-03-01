"""
Test Redis connectivity through Django's cache layer.

Usage:
    python manage.py test_redis
"""

import time

from django.core.cache import cache
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Test Redis connectivity via Django cache'

    def handle(self, *args, **options):
        start = time.monotonic()
        try:
            cache.set("redis_test", "ok", 60)
            value = cache.get("redis_test")
            elapsed_ms = (time.monotonic() - start) * 1000

            if value == "ok":
                self.stdout.write(self.style.SUCCESS(
                    f'REDIS TEST SUCCESS ({elapsed_ms:.0f} ms): value="{value}"'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'REDIS TEST DEGRADED ({elapsed_ms:.0f} ms): '
                    f'set/get returned {value!r} (circuit breaker may be open)'
                ))
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            if elapsed_ms > 500:
                self.stdout.write(self.style.ERROR(
                    f'REDIS TEST TIMEOUT (>{elapsed_ms:.0f} ms): {type(e).__name__}: {e}'
                ))
            else:
                self.stdout.write(self.style.ERROR(
                    f'REDIS TEST FAILED ({elapsed_ms:.0f} ms): {type(e).__name__}: {e}'
                ))
