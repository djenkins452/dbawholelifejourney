# ==============================================================================
# File: apps/users/about_me_views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: M3 — About Me, the Personal Knowledge management workspace
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-19
# ==============================================================================
"""About Me — what your Chief of Staff knows about you.

A first-class workspace, not a Preferences accordion. It is the customer-facing trust
surface over the canonical Personal Knowledge authority built in M2: the SAME authority
the Chief of Staff consumes, so what the user edits here is exactly what it knows.

PRESENTATION LAW (frozen design §5): the Knowledge Map reports stored knowledge as a
COUNT and nothing else. No "Rich"/"Some"/"Not yet" quality labels, no percentages, no
completeness scores, no progress bars, no deficiency language, and no colour encoding
sufficiency. An empty topic is a neutral fact about WLJ's storage, never a gap in the
person — a life is not a form.

M3 owns management and review. It does NOT own the interview, natural learning, or any
automatic writing.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.core.personal_knowledge import legacy_import
from apps.core.personal_knowledge import service as pk
from apps.core.personal_knowledge.models import (
    Provenance,
    ReviewState,
    Sensitivity,
    Topic,
)

logger = logging.getLogger(__name__)

# Topics shown on the map, in a stable order. This is an organizational aid, NOT an
# ontology of a human life — a user is never expected to have knowledge in every one.
MAP_TOPICS = [
    Topic.FAMILY, Topic.WORK, Topic.INTERESTS, Topic.GOALS, Topic.VALUES,
    Topic.ROUTINES, Topic.HOME, Topic.HISTORY, Topic.HEALTH_CONTEXT,
    Topic.FAITH, Topic.COMMUNICATION, Topic.OTHER,
]

_TOPIC_LABEL = dict(Topic.choices)
_PROVENANCE_LABEL = {
    Provenance.ABOUT_ME_ENTRY: "You added this here",
    Provenance.EXPLICIT: "You asked me to remember this",
    Provenance.INTERVIEW: "From getting to know you",
    Provenance.CANDIDATE_ACCEPTED: "You accepted this from a conversation",
    Provenance.IMPORTED: "Imported",
    Provenance.LEGACY_EXTRACTION: "Noted from earlier conversations",
}


def _fact_view(fact):
    """Customer-language projection of one fact. No model/table jargon."""
    return {
        "id": fact.id,
        "statement": fact.statement,
        "topic": fact.topic,
        "topic_label": _TOPIC_LABEL.get(fact.topic, fact.topic.replace("_", " ").title()),
        "subject": fact.subject_display,
        "provenance_label": _PROVENANCE_LABEL.get(fact.provenance, "Saved"),
        "needs_review": fact.review_state == ReviewState.UNREVIEWED,
        "is_sensitive": fact.sensitivity == Sensitivity.SENSITIVE,
        "pinned": fact.pinned,
        "created_at": fact.created_at,
        # Kept out of routine context until reviewed — shown so the state is honest.
        "in_standing_context": (
            fact.review_state != ReviewState.UNREVIEWED
            and fact.sensitivity != Sensitivity.SENSITIVE
        ),
    }


class AboutMeView(LoginRequiredMixin, TemplateView):
    """The workspace overview: what I know, and how to manage it."""

    template_name = "users/about_me.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        counts = pk.topic_counts(user)
        total = sum(counts.values())

        cards = []
        for topic in MAP_TOPICS:
            count = counts.get(str(topic), 0)
            cards.append({
                "key": str(topic),
                "label": _TOPIC_LABEL[topic],
                "count": count,
                # FACTUAL count only. "nothing yet" is a neutral statement about
                # storage — never a judgment, never a prompt to fill a gap.
                "count_label": (f"{count} thing I know" if count == 1
                                else f"{count} things I know" if count
                                else "nothing yet"),
            })
        # Emergent topics (Contract 8.4) — anything stored outside the known set still
        # appears, so knowledge can never become invisible because it lacked a category.
        for key, count in sorted(counts.items()):
            if key not in {str(t) for t in MAP_TOPICS}:
                cards.append({
                    "key": key, "label": key.replace("_", " ").title(), "count": count,
                    "count_label": (f"{count} thing I know" if count == 1
                                    else f"{count} things I know"),
                })

        context.update({
            "topic_cards": cards,
            "total_count": total,
            "pending_review": legacy_import.pending_review_count(user),
            "has_legacy_material": (legacy_import.has_legacy_material(user)
                                    if total == 0 else False),
            "page_title": "About Me",
        })
        return context


class AboutMeTopicView(LoginRequiredMixin, TemplateView):
    """Everything stored under one topic, with per-fact controls."""

    template_name = "users/about_me_topic.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        topic = self.kwargs.get("topic", "")
        facts = pk.facts_by_topic(self.request.user, topic).order_by("-created_at")
        context.update({
            "topic": topic,
            "topic_label": _TOPIC_LABEL.get(topic, topic.replace("_", " ").title()),
            "facts": [_fact_view(f) for f in facts],
            "sensitivity_choices": Sensitivity.choices,
            "page_title": "About Me",
        })
        return context


class AboutMeReviewView(LoginRequiredMixin, TemplateView):
    """Review what WLJ noted from earlier conversations.

    Everything here is UNREVIEWED legacy extraction: retrievable on request, but kept out
    of routine context until the user keeps it. Reviewing is optional and resumable, and
    never blocks using the product.
    """

    template_name = "users/about_me_review.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        pending = (pk.active_facts(user)
                   .filter(provenance=Provenance.LEGACY_EXTRACTION,
                           review_state=ReviewState.UNREVIEWED)
                   .order_by("topic", "-created_at"))
        context.update({
            "facts": [_fact_view(f) for f in pending],
            "pending_count": pending.count(),
            "legacy_summary": legacy_import.import_legacy_knowledge(user, dry_run=True),
            "page_title": "About Me",
        })
        return context


class AboutMeImportView(LoginRequiredMixin, View):
    """Bring legacy knowledge forward for review. Idempotent; never destructive."""

    def post(self, request, *args, **kwargs):
        summary = legacy_import.import_legacy_knowledge(request.user)
        adopted = sum(v["adopted"] for v in summary.values())
        if adopted:
            messages.success(
                request,
                f"I've brought {adopted} thing{'s' if adopted != 1 else ''} forward from "
                "our earlier conversations. Have a look and keep what's right.")
        else:
            messages.info(request, "There's nothing new to bring forward.")
        return redirect(reverse("users:about_me_review"))


class AboutMeFactActionView(LoginRequiredMixin, View):
    """Per-fact controls: keep, edit, delete, pin, sensitivity.

    Every write goes through the canonical M2 service, so cache invalidation, lineage and
    standing-context eligibility are handled by the one authority — never re-implemented
    here. The UI can look like plain editing while correction preserves lineage beneath.
    """

    def post(self, request, pk_id, action, *args, **kwargs):
        # Ownership is enforced by the ONE authority, never re-implemented here.
        fact = pk.get_fact(request.user, pk_id)
        if fact is None:
            raise Http404("No such knowledge")
        redirect_to = request.POST.get("next") or reverse("users:about_me")
        try:
            if action == "keep":
                pk.mark_reviewed(fact)
                messages.success(request, "Kept.")
            elif action == "correct":
                statement = (request.POST.get("statement") or "").strip()
                if not statement:
                    messages.error(request, "Please enter what I should remember.")
                else:
                    pk.correct_fact(fact, statement)
                    messages.success(request, "Updated.")
            elif action == "delete":
                pk.delete_fact(fact)
                messages.success(request, "Removed. I won't remember that.")
            elif action == "pin":
                pk.set_pinned(fact, not fact.pinned)
                messages.success(request, "Pinned." if not fact.pinned else "Unpinned.")
            elif action == "sensitive":
                new = (Sensitivity.NORMAL if fact.sensitivity == Sensitivity.SENSITIVE
                       else Sensitivity.SENSITIVE)
                pk.set_sensitivity(fact, new)
                messages.success(
                    request,
                    "Marked sensitive — I'll keep it out of everyday conversation."
                    if new == Sensitivity.SENSITIVE else "No longer marked sensitive.")
            else:
                messages.error(request, "That action isn't available.")
        except Exception:
            logger.warning("About Me: action %s failed fact=%s", action, pk_id,
                           exc_info=True)
            messages.error(request, "That didn't save. Please try again.")
        return redirect(redirect_to)


class AboutMeAddView(LoginRequiredMixin, View):
    """Add something manually. Explicit user authorship — reviewed by definition."""

    def post(self, request, *args, **kwargs):
        statement = (request.POST.get("statement") or "").strip()
        topic = (request.POST.get("topic") or Topic.OTHER).strip()
        subject = (request.POST.get("subject") or "").strip()
        redirect_to = request.POST.get("next") or reverse("users:about_me")
        if not statement:
            messages.error(request, "Please enter what you'd like me to remember.")
            return redirect(redirect_to)
        try:
            pk.add_fact(request.user, statement, topic=topic, subject_label=subject,
                        provenance=Provenance.ABOUT_ME_ENTRY,
                        review_state=ReviewState.USER_AUTHORED)
            messages.success(request, "Got it — I'll remember that.")
        except Exception as exc:
            logger.warning("About Me: add failed", exc_info=True)
            messages.error(request, str(exc) if isinstance(exc, ValueError)
                           else "That didn't save. Please try again.")
        return redirect(redirect_to)


class AboutMeClearView(LoginRequiredMixin, View):
    """Remove everything WLJ has learned. Personal Knowledge ONLY.

    Deliberately scoped: this never touches goals, tasks, health records, journal
    entries, people or any other domain record — only what the Chief of Staff has
    learned about the user.
    """

    def post(self, request, *args, **kwargs):
        if (request.POST.get("confirm") or "").strip().lower() != "remove everything":
            messages.error(
                request,
                'To remove everything, type "remove everything" to confirm.')
            return redirect(reverse("users:about_me"))
        removed = pk.clear_facts(request.user)
        messages.success(
            request,
            f"Removed {removed} thing{'s' if removed != 1 else ''}. Your goals, tasks, "
            "health records and journal entries are untouched.")
        return redirect(reverse("users:about_me"))
