# ==============================================================================
# File: apps/finance/views_recurring.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Ordinary-user CRUD over detected and declared recurring series.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Everything a person needs to do with a recurring commitment, without Django admin.

Detection proposes; a person decides. Before this, a detected series had exactly one
verb — confirm or ignore — which meant a candidate that was RIGHT about the commitment
and WRONG about the amount, the cadence or the name could only be accepted whole or
thrown away. That is not a review; it is an ultimatum.

Nothing here confirms anything on the user's behalf, and every correction sets
`source = user`, which is what stops the next detection run from arguing with them.
"""
from __future__ import annotations

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, UpdateView

from apps.core.current_context import PageSummaryMixin
from apps.finance.access import finance_enabled_required
from apps.finance.models import RecurringSeries, Transaction
from apps.finance.views import FinanceAuditMixin, FinanceUserMixin


class RecurringSeriesForm(forms.ModelForm):
    """Correcting what WLJ guessed. Every field the detector fills is editable.

    A person can be right about their own gym membership faster than any heuristic, so
    the form does not defend the detector's answer — it just records theirs.
    """

    class Meta:
        model = RecurringSeries
        fields = ["name", "payee", "kind", "frequency", "amount_expected",
                  "amount_min", "amount_max", "is_variable", "category", "account",
                  "next_due_date", "note"]
        widgets = {
            "next_due_date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "name": "What to call it",
            "payee": "Merchant or payee",
            "kind": "What kind of commitment",
            "frequency": "How often",
            "amount_expected": "Expected amount",
            "amount_min": "Lowest seen",
            "amount_max": "Highest seen",
            "is_variable": "The amount varies",
            "next_due_date": "Next expected",
            "note": "Your note",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Ownership is enforced in the form as well as the view: a corrected series must
        # never be able to point at somebody else's account.
        if user is not None:
            from apps.finance.models import FinancialAccount, TransactionCategory
            self.fields["account"].queryset = FinancialAccount.objects.filter(
                user=user, status="active")
            self.fields["category"].queryset = TransactionCategory.objects.filter(
                Q(user=user) | Q(user__isnull=True))
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing + " form-input").strip()

    def clean(self):
        cleaned = super().clean()
        low, high = cleaned.get("amount_min"), cleaned.get("amount_max")
        if low is not None and high is not None and low > high:
            self.add_error("amount_min", "The lowest amount cannot exceed the highest.")
        if not cleaned.get("is_variable") and cleaned.get("amount_expected") is None:
            self.add_error(
                "amount_expected",
                "A fixed commitment needs an expected amount — or mark it as varying.")
        return cleaned


class SeriesListView(PageSummaryMixin, FinanceUserMixin, ListView):
    """Everything recurring, grouped by what the person still has to decide."""

    model = RecurringSeries
    template_name = "finance/series_list.html"
    context_object_name = "series"
    page_summary_key = "finance.recurring"
    page_summary_title = "Recurring"

    def get_queryset(self):
        show = self.request.GET.get("show") or "active"
        # Archived rows are invisible to the default manager, so the archived view has
        # to ask for them explicitly.
        qs = (RecurringSeries.objects.archived_only() if show == "archived"
              else RecurringSeries.objects.all())
        return (qs.filter(user=self.request.user)
                .select_related("account", "category", "declared_template"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = list(context["series"])
        context["show"] = self.request.GET.get("show") or "active"
        context["candidates"] = [s for s in rows if s.review_state ==
                                 RecurringSeries.REVIEW_CANDIDATE
                                 and s.merged_into_id is None]
        context["confirmed"] = [s for s in rows if s.review_state ==
                                RecurringSeries.REVIEW_CONFIRMED
                                and s.merged_into_id is None]
        context["ignored"] = [s for s in rows if s.review_state ==
                              RecurringSeries.REVIEW_IGNORED]
        context["merged"] = [s for s in rows if s.merged_into_id is not None]
        # `archived_only()`, not `filter(status="archived")` — the default manager has
        # already excluded everything that is not active, so the naive filter always
        # counts zero and the "Show archived" link never appears.
        context["archived_count"] = RecurringSeries.objects.archived_only().filter(
            user=self.request.user).count()
        context["kind_choices"] = RecurringSeries.KIND_CHOICES
        return context


class SeriesDetailView(FinanceUserMixin, DetailView):
    """One commitment, with the transactions that are the reason WLJ believes it."""

    model = RecurringSeries
    template_name = "finance/series_detail.html"
    context_object_name = "series"

    def get_queryset(self):
        # Archived included: a person must be able to open one to restore it.
        return (RecurringSeries.objects.all_with_deleted()
                .exclude(status="deleted").filter(user=self.request.user)
                .select_related("account", "category", "declared_template",
                                "merged_into"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        series = self.object
        # The evidence, as actual rows. A confidence badge with nothing behind it asks
        # the person to trust the detector; the occurrences let them check it.
        context["observations"] = (Transaction.objects
                                   .filter(user=self.request.user,
                                           recurring_series=series)
                                   .select_related("account")
                                   .order_by("-date")[:24])
        context["monthly_equivalent"] = series.monthly_equivalent(
            use="max" if series.is_variable else "expected")
        context["kind_choices"] = RecurringSeries.KIND_CHOICES
        context["merge_targets"] = (RecurringSeries.objects
                                    .filter(user=self.request.user, status="active",
                                            merged_into__isnull=True)
                                    .exclude(pk=series.pk).order_by("name"))
        return context


class SeriesUpdateView(FinanceAuditMixin, FinanceUserMixin, UpdateView):
    """Correct anything WLJ got wrong. The correction outranks the next run."""

    model = RecurringSeries
    form_class = RecurringSeriesForm
    template_name = "finance/series_form.html"

    def get_queryset(self):
        return (RecurringSeries.objects.all_with_deleted()
                .exclude(status="deleted").filter(user=self.request.user))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        # A corrected series is the person's, not the detector's. `source = user` is
        # what `persist()` reads to leave it alone from now on.
        form.instance.source = RecurringSeries.SOURCE_USER
        response = super().form_valid(form)
        messages.success(self.request, f"Saved your changes to {self.object.name}.")
        return response

    def get_success_url(self):
        return reverse("finance:series_detail", args=[self.object.pk])


class SeriesCreateView(FinanceAuditMixin, LoginRequiredMixin, UpdateView):
    """Add a commitment WLJ has not seen — a new subscription, a bill starting soon."""

    model = RecurringSeries
    form_class = RecurringSeriesForm
    template_name = "finance/series_form.html"
    success_url = reverse_lazy("finance:series_list")

    def get_object(self, queryset=None):
        return RecurringSeries(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        # Created by hand, so it is confirmed by definition — the person just declared
        # it. Nothing WLJ *detected* ever arrives in this state.
        form.instance.review_state = RecurringSeries.REVIEW_CONFIRMED
        form.instance.source = RecurringSeries.SOURCE_USER
        form.instance.confidence = "high"
        response = super().form_valid(form)
        messages.success(self.request, f"Added {self.object.name}.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_create"] = True
        return context


def _owned(request, pk):
    """This user's series, INCLUDING archived ones.

    `RecurringSeries.objects` is the `SoftDeleteManager`, which returns only
    `status='active'`. Looking a series up through it makes an archived row a 404 — and
    therefore impossible to restore, which is the one thing archiving is for.
    """
    return get_object_or_404(
        RecurringSeries.objects.all_with_deleted().exclude(status="deleted"),
        pk=pk, user=request.user)


@require_POST
@finance_enabled_required
def series_archive(request, pk):
    """Out of the way, not gone. Archive is reversible; delete is not."""
    series = _owned(request, pk)
    # `archive()`, not `soft_delete()`. Soft delete marks a row for permanent removal
    # after 30 days; archiving is the reversible "out of the way" the person asked for.
    series.archive()
    messages.success(
        request, f"{series.name} archived. You can restore it from Show archived.")
    return redirect(reverse("finance:series_list"))


@require_POST
@finance_enabled_required
def series_restore(request, pk):
    series = _owned(request, pk)
    series.status = "active"
    series.deleted_at = None
    series.save(update_fields=["status", "deleted_at", "updated_at"])
    messages.success(request, f"{series.name} restored.")
    return redirect(reverse("finance:series_detail", args=[series.pk]))


@require_POST
@finance_enabled_required
def series_delete(request, pk):
    """Permanent. The observations survive — only WLJ's reading of them goes.

    The transactions are unlinked rather than removed: deleting a person's belief about
    a pattern must never delete the money that formed it.
    """
    series = _owned(request, pk)
    name = series.name
    Transaction.objects.filter(user=request.user, recurring_series=series).update(
        recurring_series=None)
    RecurringSeries.objects.filter(user=request.user, merged_into=series).update(
        merged_into=None)
    series.delete()
    messages.success(request, f"{name} deleted. Your transactions are untouched.")
    return redirect(reverse("finance:series_list"))


@require_POST
@finance_enabled_required
def series_end(request, pk):
    """This commitment has stopped. Kept for history; out of the forecast.

    Distinct from ignoring it — "I cancelled Netflix in March" and "that was never a
    subscription" are different facts, and a forecast that confuses them is wrong in a
    different way each time.
    """
    from apps.core.utils import get_user_today

    series = _owned(request, pk)
    series.review_state = RecurringSeries.REVIEW_IGNORED
    series.source = RecurringSeries.SOURCE_USER
    series.next_due_date = None
    series.note = (series.note + "\n" if series.note else "") + \
        f"Marked ended by you on {get_user_today(request.user)}."
    series.save(update_fields=["review_state", "source", "next_due_date", "note",
                               "updated_at"])
    messages.success(request, f"{series.name} marked as ended. It's out of your "
                              f"forecast but still in your history.")
    return redirect(reverse("finance:series_detail", args=[series.pk]))


@require_POST
@finance_enabled_required
def series_merge(request, pk):
    """Two rows, one commitment. The observations move; the duplicate stays as a pointer.

    A merchant that renames itself mid-year produces two series for one subscription.
    Merging keeps the survivor's identity and moves every observed transaction onto it,
    so the evidence is not split across a row nobody looks at any more.
    """
    series = _owned(request, pk)
    try:
        target = RecurringSeries.objects.get(
            pk=int(request.POST.get("into") or 0), user=request.user, status="active")
    except (RecurringSeries.DoesNotExist, ValueError, TypeError):
        messages.error(request, "That is not a series WLJ can merge into.")
        return redirect(reverse("finance:series_detail", args=[series.pk]))
    if target.pk == series.pk:
        messages.error(request, "A series cannot be merged into itself.")
        return redirect(reverse("finance:series_detail", args=[series.pk]))

    Transaction.objects.filter(user=request.user, recurring_series=series).update(
        recurring_series=target)
    target.occurrence_count = Transaction.objects.filter(
        user=request.user, recurring_series=target).count()
    if series.first_seen_date and (not target.first_seen_date
                                   or series.first_seen_date < target.first_seen_date):
        target.first_seen_date = series.first_seen_date
    if series.last_seen_date and (not target.last_seen_date
                                  or series.last_seen_date > target.last_seen_date):
        target.last_seen_date = series.last_seen_date
    target.source = RecurringSeries.SOURCE_USER
    target.save(update_fields=["occurrence_count", "first_seen_date", "last_seen_date",
                               "source", "updated_at"])

    series.merged_into = target
    series.review_state = RecurringSeries.REVIEW_IGNORED
    series.source = RecurringSeries.SOURCE_USER
    series.save(update_fields=["merged_into", "review_state", "source", "updated_at"])
    messages.success(request, f"Merged {series.name} into {target.name}.")
    return redirect(reverse("finance:series_detail", args=[target.pk]))


@require_POST
@finance_enabled_required
def series_split(request, pk):
    """This is not one commitment. Detach the observations and let detection re-look.

    Splitting does not guess where the seam is — WLJ already had one go at that and got
    it wrong, which is why the person is here. It unlinks the transactions and clears
    the series so the next run starts from the evidence rather than from its own
    previous answer.
    """
    series = _owned(request, pk)
    detached = Transaction.objects.filter(
        user=request.user, recurring_series=series).update(recurring_series=None)
    series.review_state = RecurringSeries.REVIEW_IGNORED
    series.source = RecurringSeries.SOURCE_USER
    series.note = (series.note + "\n" if series.note else "") + \
        "You said this was more than one commitment."
    series.save(update_fields=["review_state", "source", "note", "updated_at"])
    messages.success(
        request,
        f"Split {series.name}: {detached} transaction(s) released. WLJ will look at "
        f"them again on the next run and propose them separately.")
    return redirect(reverse("finance:series_list"))


@require_POST
@finance_enabled_required
def series_detect(request):
    """Ask the worker to look now. Never runs inline — it classifies everything."""
    from apps.core.celery_utils import safe_enqueue
    from apps.finance.tasks import detect_recurring_and_opportunities

    if safe_enqueue(detect_recurring_and_opportunities, request.user.pk):
        messages.success(
            request, "Looking for recurring patterns now. Refresh in a moment — "
                     "anything found appears here as a candidate for you to confirm.")
    else:
        messages.warning(request, "WLJ couldn't start the search just now. Nothing has "
                                  "changed; try again shortly.")
    return redirect(reverse("finance:series_list"))
