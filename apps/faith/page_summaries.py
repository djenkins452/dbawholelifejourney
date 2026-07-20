# ==============================================================================
# File: apps/faith/page_summaries.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Current Context PAGE-SUMMARY providers for Faith overview pages.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Deterministic page-summary providers for the Faith overview pages.

Registered at app-ready (see FaithConfig.ready). Each provider is user-scoped and
request-path-safe (bounded FaithQueries reads — the SAME canonical authority the pages
render from, never a re-derivation), and returns the uniform {title, content, kind} the
assistant consumes as Current Context focus. FACTS ONLY — WLJ exposes counts/dates/
progress; the model decides what they mean (no verdicts, no "on track"). See
docs/WLJ_CURRENT_CONTEXT_CONTRACT.md (overview-page section).
"""
from apps.core.current_context import register_page_summary
from apps.faith.services.faith_queries import FaithQueries


def _days_since_reading(user):
    """Whole days since the last Bible reading (unified plan + routine source), or None."""
    dates = FaithQueries.bible_completion_dates(user, limit=1)
    if not dates:
        return None, None
    from apps.core.utils import get_user_today
    last = dates[0]
    return (get_user_today(user) - last).days, last


@register_page_summary("faith.prayers")
def prayers_page_summary(user, params):
    """The Prayer list / Answered-prayers pages. Deterministic prayer facts only."""
    unanswered = FaithQueries.unanswered_prayers(user).count()
    urgent = FaithQueries.urgent_prayers(user).count()
    answered = FaithQueries.answered_prayers(user).count()
    if not (unanswered or answered):
        return {"title": "Prayers", "kind": "prayers overview",
                "content": "Prayers — no prayer requests recorded yet."}

    recent = list(FaithQueries.unanswered_prayers(user)
                  .order_by("-priority", "-created_at")
                  .values_list("title", flat=True)[:5])
    lines = [
        f"Active (unanswered) prayers: {unanswered}" + (f" — {urgent} urgent" if urgent else ""),
        f"Answered prayers: {answered}",
    ]
    if recent:
        lines.append("Most recent active: " + "; ".join(recent))
    return {"title": "Prayers", "kind": "prayers overview",
            "content": "Prayers overview\n" + "\n".join(lines)}


@register_page_summary("faith.reading_plans")
def reading_plans_page_summary(user, params):
    """The Bible reading-plans page. Deterministic plan/progress facts only."""
    plans = list(FaithQueries.active_reading_plans(user).select_related("template"))
    days_since, last = _days_since_reading(user)
    if not plans:
        content = "Bible reading plans — no active plan right now."
        if days_since is not None:
            content += f" Last recorded reading: {last.isoformat()} ({days_since} days ago)."
        return {"title": "Bible Reading Plans", "kind": "reading plans overview",
                "content": content}

    lines = []
    for pl in plans:
        t = pl.template
        lines.append(
            f"{t.title}: day {pl.current_day} of {t.duration_days}, "
            f"{pl.progress_percentage}% complete ({pl.days_completed} days done)")
    if days_since is not None:
        lines.append(f"Last recorded reading: {last.isoformat()} ({days_since} days ago)")
    return {"title": "Bible Reading Plans", "kind": "reading plans overview",
            "content": "Bible reading plans overview\n" + "\n".join(lines)}


@register_page_summary("faith.home")
def faith_home_page_summary(user, params):
    """The Faith home overview. A deterministic snapshot across prayers + reading — the
    SAME canonical FaithQueries the module pages render, so Beth can never contradict the
    screen. Facts only; the model interprets."""
    unanswered = FaithQueries.unanswered_prayers(user).count()
    answered = FaithQueries.answered_prayers(user).count()
    plans = list(FaithQueries.active_reading_plans(user).select_related("template"))
    days_since, last = _days_since_reading(user)

    from apps.faith.models import FaithMilestone, SavedVerse
    milestones = FaithMilestone.objects.filter(user=user).count()
    memory_verses = SavedVerse.objects.filter(user=user, is_memory_verse=True).count()

    lines = [
        f"Active prayers: {unanswered}  |  Answered prayers: {answered}",
    ]
    if plans:
        pl = plans[0]
        lines.append(f"Active reading plan: {pl.template.title} — day {pl.current_day} "
                     f"of {pl.template.duration_days} ({pl.progress_percentage}%)")
    else:
        lines.append("Active reading plan: none")
    if days_since is not None:
        lines.append(f"Last recorded Bible reading: {last.isoformat()} ({days_since} days ago)")
    if memory_verses:
        lines.append(f"Memory verses: {memory_verses}")
    if milestones:
        lines.append(f"Faith milestones recorded: {milestones}")
    return {"title": "Faith", "kind": "faith overview",
            "content": "Faith overview\n" + "\n".join(lines)}
