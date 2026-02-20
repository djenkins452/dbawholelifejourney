"""
Natural Language Quick Add Parser.

Rule-based MVP parser for creating calendar events from free text.
Handles patterns like:
  "Bible Study Wednesdays 6pm-8pm"
  "Recurring gym session Mon/Wed/Fri 5:30am-6:30am"
  "Team meeting tomorrow 2pm-3pm"
  "Doctor appointment March 15 10am"
"""

import datetime as dt
import re

from django.utils import timezone


# Day name → ISO weekday number
DAY_MAP = {
    'monday': 1, 'mon': 1, 'mondays': 1,
    'tuesday': 2, 'tue': 2, 'tues': 2, 'tuesdays': 2,
    'wednesday': 3, 'wed': 3, 'wednesdays': 3,
    'thursday': 4, 'thu': 4, 'thur': 4, 'thurs': 4, 'thursdays': 4,
    'friday': 5, 'fri': 5, 'fridays': 5,
    'saturday': 6, 'sat': 6, 'saturdays': 6,
    'sunday': 7, 'sun': 7, 'sundays': 7,
}

# Domain keyword hints
DOMAIN_HINTS = {
    'faith': ['bible', 'church', 'prayer', 'worship', 'devotion', 'sermon', 'faith', 'fellowship'],
    'health': ['gym', 'workout', 'exercise', 'run', 'yoga', 'fitness', 'walk', 'health', 'doctor', 'dentist', 'therapy', 'medical'],
    'family': ['family', 'kids', 'date night', 'spouse', 'dinner with'],
    'work': ['meeting', 'standup', 'review', 'sprint', 'work', 'team', 'client', 'project'],
    'finances': ['budget', 'finance', 'bills', 'tax', 'invest'],
}

RECURRING_KEYWORDS = ['recurring', 'weekly', 'every', 'daily', 'each']

TIME_PATTERN = re.compile(
    r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?',
)

TIME_RANGE_PATTERN = re.compile(
    r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*[-–to]+\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?',
    re.IGNORECASE,
)


def parse_quick_add(text):
    """
    Parse free-text input into event creation parameters.

    Returns dict:
        title (str)
        start_time (time or None)
        end_time (time or None)
        weekdays (list of ISO weekday ints)
        is_recurring (bool)
        domain_slug (str or None)
        date (date or None) — for one-off events
    """
    text_lower = text.lower().strip()

    result = {
        'title': text.strip(),
        'start_time': None,
        'end_time': None,
        'weekdays': [],
        'is_recurring': False,
        'domain_slug': None,
        'date': None,
    }

    # Detect recurring
    for kw in RECURRING_KEYWORDS:
        if kw in text_lower:
            result['is_recurring'] = True
            break

    # Extract weekdays
    for word in re.split(r'[\s,/]+', text_lower):
        word_clean = word.strip('.,;')
        if word_clean in DAY_MAP:
            result['weekdays'].append(DAY_MAP[word_clean])
            result['is_recurring'] = True  # Day names imply recurring

    # Extract time range
    time_range_match = TIME_RANGE_PATTERN.search(text)
    if time_range_match:
        result['start_time'] = _parse_time_parts(
            time_range_match.group(1),
            time_range_match.group(2),
            time_range_match.group(3) or time_range_match.group(6),
        )
        result['end_time'] = _parse_time_parts(
            time_range_match.group(4),
            time_range_match.group(5),
            time_range_match.group(6),
        )
    else:
        # Try single time
        times = TIME_PATTERN.findall(text)
        if times:
            result['start_time'] = _parse_time_parts(times[0][0], times[0][1], times[0][2])
            if len(times) > 1:
                result['end_time'] = _parse_time_parts(times[1][0], times[1][1], times[1][2])

    # Default end time = start + 1 hour
    if result['start_time'] and not result['end_time']:
        start_dt = dt.datetime.combine(dt.date.today(), result['start_time'])
        end_dt = start_dt + dt.timedelta(hours=1)
        result['end_time'] = end_dt.time()

    # Detect "tomorrow"
    if 'tomorrow' in text_lower:
        result['date'] = timezone.localdate() + dt.timedelta(days=1)

    # Detect "today"
    if 'today' in text_lower:
        result['date'] = timezone.localdate()

    # Detect domain
    for domain_slug, keywords in DOMAIN_HINTS.items():
        for kw in keywords:
            if kw in text_lower:
                result['domain_slug'] = domain_slug
                break
        if result['domain_slug']:
            break

    # Clean up title — remove time/day/temporal tokens for a cleaner title
    clean_title = text.strip()
    # Remove time range
    clean_title = TIME_RANGE_PATTERN.sub('', clean_title)
    # Remove standalone times
    clean_title = TIME_PATTERN.sub('', clean_title)
    # Remove recurring keywords
    for kw in RECURRING_KEYWORDS:
        clean_title = re.sub(rf'\b{kw}\b', '', clean_title, flags=re.IGNORECASE)
    # Remove day names
    for day in DAY_MAP:
        clean_title = re.sub(rf'\b{day}\b', '', clean_title, flags=re.IGNORECASE)
    # Remove temporal keywords (tomorrow, today, tonight, next, this)
    for temporal in ['tomorrow', 'today', 'tonight', 'next', 'this']:
        clean_title = re.sub(rf'\b{temporal}\b', '', clean_title, flags=re.IGNORECASE)
    # Remove dangling prepositions left after time/date removal
    clean_title = re.sub(r'\b(at|on|in|by|from|for|until)\s*$', '', clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r'\b(at|on|in|by|from|for|until)\s+(at|on|in|by|from|for|until)\b', '', clean_title, flags=re.IGNORECASE)
    # Clean up whitespace
    clean_title = re.sub(r'\s+', ' ', clean_title).strip(' ,.-/')
    if clean_title:
        result['title'] = clean_title

    return result


def _parse_time_parts(hour_str, minute_str, ampm):
    """Parse hour, minute, am/pm into a time object."""
    hour = int(hour_str)
    minute = int(minute_str) if minute_str else 0

    if ampm:
        ampm = ampm.lower()
        if ampm == 'pm' and hour < 12:
            hour += 12
        elif ampm == 'am' and hour == 12:
            hour = 0
    else:
        # No am/pm — guess based on hour
        if 1 <= hour <= 6:
            hour += 12  # Assume PM for 1-6

    return dt.time(min(hour, 23), min(minute, 59))
