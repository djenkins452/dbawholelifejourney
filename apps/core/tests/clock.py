"""One test-time clock seam for everything that asks what time it is for a user.

WHY THIS EXISTS
---------------
`apps.core.utils.get_user_now` and `get_user_today` are the two halves of one
authority, and both derive from `django.utils.timezone.now()`. Tests that froze
only the DATE half left the TIME half running on the wall clock, so a fixture
describing a morning briefing got the evening composer after 8 PM — the suite
passed all afternoon and failed at night, with nothing about the code changed.

Freezing `timezone.now` rather than the two helpers is deliberate: dozens of
modules bind `get_user_now` / `get_user_today` at import time, so patching those
names reaches only the modules that import them inside a function. Everything
reads the same instant this way, whichever import style it uses, and the date and
the hour cannot drift apart because they are derived from one value.

USAGE
-----
    from apps.core.tests.clock import user_clock, morning, evening

    with morning(self.user) as clock:
        brief = compose_executive_brief(self.user)      # 8 AM, deterministically

    with evening(self.user, on=MY_TEST_DAY):
        ...

    with user_clock(self.user, hour=13, minute=30) as clock:
        Thing.objects.create(user=self.user, date=clock.today)   # seed the SAME day

Pass `on=` when the test already has a date of its own; otherwise every run uses
REFERENCE_DAY, so nothing depends on the real current date either.
"""
from contextlib import contextmanager
from datetime import date, datetime, time, timezone as _utc
from unittest import mock

# A fixed, unremarkable day: mid-week, mid-month, mid-year, no DST boundary near it
# in the timezones WLJ users are in. Chosen so no test depends on "today".
REFERENCE_DAY = date(2026, 6, 17)          # a Wednesday

MORNING_HOUR = 8                            # before every daypart pivot
MIDDAY_HOUR = 13
EVENING_HOUR = 21                           # after the 8 PM wind-down pivot



class _FrozenDatetime:
    """Stands in for `datetime` inside apps.core.time.system_clock.

    That module is a SECOND time authority: `get_current_time` calls
    `datetime.now(tz)` — Python's clock — not `django.utils.timezone.now()`. Both
    report the same real instant, so nothing fails in production, but a test that
    froze only Django's clock got an unfrozen answer from anything reading this one
    (`GuidanceItem.is_snoozed`, `HealthBriefingSnapshot.is_expired`,
    `build_fitness_state`). Replacing the module's `datetime` name rather than the
    function reaches every caller whatever its import style.
    """

    __slots__ = ("_instant",)

    def __init__(self, instant):
        self._instant = instant

    def now(self, tz=None):
        return self._instant.astimezone(tz) if tz is not None else self._instant

    def __getattr__(self, name):          # everything else behaves as datetime does
        return getattr(datetime, name)


class FrozenClock:
    """The instant the suite is pinned to, in terms a fixture can seed against."""

    __slots__ = ("instant", "local")

    def __init__(self, instant, local):
        self.instant = instant              # aware UTC — what timezone.now() returns
        self.local = local                  # the same moment in the user's timezone

    @property
    def now(self):
        return self.local

    @property
    def today(self):
        return self.local.date()

    @property
    def hour(self):
        return self.local.hour

    def __repr__(self):
        return f"<FrozenClock {self.local.isoformat()}>"


@contextmanager
def user_clock(user, *, hour=MORNING_HOUR, minute=0, on=None):
    """Freeze the clock at `hour:minute` on `on`, IN THE USER'S OWN TIMEZONE.

    The hour is the user-local hour because that is what the product branches on
    ("is it evening for this person?"), not UTC. Yields a `FrozenClock` so the
    test can seed rows on the same day it is pretending to be.
    """
    from apps.core.utils import _get_user_tz, get_user_now, get_user_today

    tz = _get_user_tz(user)
    local = datetime.combine(on or REFERENCE_DAY, time(hour, minute), tzinfo=tz)
    instant = local.astimezone(_utc.utc)

    with mock.patch("django.utils.timezone.now", return_value=instant), \
            mock.patch("apps.core.time.system_clock.datetime", _FrozenDatetime(instant)):
        # The seam is only worth having if the production authority agrees with it.
        assert get_user_now(user).hour == hour, (
            f"clock seam disagrees with get_user_now: asked for {hour}, "
            f"production reports {get_user_now(user).hour}"
        )
        assert get_user_today(user) == local.date(), (
            "clock seam disagrees with get_user_today — the date and hour halves "
            "have drifted, which is the exact bug this seam exists to prevent"
        )
        yield FrozenClock(instant, local)


def morning(user, on=None):
    """8 AM for this user — before every daypart pivot in the CoS composers."""
    return user_clock(user, hour=MORNING_HOUR, on=on)


def midday(user, on=None):
    return user_clock(user, hour=MIDDAY_HOUR, on=on)


def evening(user, on=None):
    """9 PM for this user — after the 8 PM wind-down pivot."""
    return user_clock(user, hour=EVENING_HOUR, on=on)


def pin_clock(testcase, user, *, hour=MORNING_HOUR, minute=0, on=None):
    """Pin the clock for the whole of one test, and hand back the FrozenClock.

    For the `self.today = date.today()` pattern, which is the same bug wearing
    different clothes: `date.today()` is the SYSTEM-local date, while production asks
    `get_user_today(user)` for the USER's date. Those are different dates whenever the
    two zones straddle midnight, so the fixture seeds one day and the pipeline computes
    another — after 8 PM Eastern, for a UTC user, every time.

        def setUp(self):
            self.user = _make_user()
            self.today = pin_clock(self, self.user).today
    """
    ctx = user_clock(user, hour=hour, minute=minute, on=on)
    clock = ctx.__enter__()
    testcase.addCleanup(ctx.__exit__, None, None, None)
    return clock
