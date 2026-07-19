"""MedicalDomainTruth — canonical interface to Medical (lab) truth (Layer 1).

Thin facade over the canonical medical models (apps/medical/models.py). Owns NO new
retrieval logic and reads NO SAE snapshot — read live from LabResult / LabPanel /
MedicalDocument. SCOPE: lab/diagnostic-result truth only. Conditions, allergies,
immunizations, procedures, and a structured provider directory do NOT exist as models
in apps/medical. Prescription medication is the `medicine` domain, not this one.
"""
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from apps.core.truth.current import CurrentTruth
from apps.core.truth.domain import DomainTruth, register_domain_truth
from apps.core.truth.entity import CompleteEntity
from apps.core.truth.freshness import CURRENT, MISSING
from apps.core.truth.history import series_from_rows
from apps.core.truth.periods import resolve_period

_DOMAIN = "medical"
_SRC = "medical_models"


def _today(user):
    from apps.core.utils import get_user_today
    return get_user_today(user)


def _test_name(r):
    ct = r.canonical_test
    if ct is not None:
        return ct.short_name or ct.name
    return r.raw_test_name


def _num(d):
    return float(d) if d is not None else None


@register_domain_truth
class MedicalDomainTruth(DomainTruth):
    domain = "medical"
    current_metrics = ("tracked_lab_tests", "abnormal_results",
                       "lab_panels", "lab_documents", "latest_labs")
    history_metrics = ("lab_value",)
    entity_types = ("lab_result", "lab_panel", "document")
    analysis_subjects = {
        "labs": {"entity_type": "lab_result", "history_metric": "lab_value"},
    }

    def _results(self):
        from apps.medical.models import LabResult
        return (LabResult.objects.filter(user=self.user)
                .select_related("canonical_test", "panel", "medical_document"))

    def _latest_per_test(self):
        latest = {}
        for r in self._results().order_by("-collected_at"):
            key = r.canonical_test_id or (r.raw_test_name or "").strip().lower()
            if key not in latest:
                latest[key] = r
        return list(latest.values())

    # ── CURRENT ──────────────────────────────────────────────────────────
    def current(self, metric):
        if metric == "tracked_lab_tests":
            rows = self._latest_per_test()
            names = sorted(_test_name(r) for r in rows)
            return CurrentTruth.found(
                _DOMAIN, metric, len(names), CURRENT if names else MISSING,
                source=_SRC, detail={"tests": names})

        if metric == "abnormal_results":
            rows = [r for r in self._latest_per_test() if r.is_abnormal]
            return CurrentTruth.found(
                _DOMAIN, metric, len(rows), CURRENT if rows else MISSING, source=_SRC,
                detail={"results": [
                    {"test": _test_name(r), "value": r.value_text, "unit": r.unit,
                     "flag": r.abnormal_flag, "status": r.status_label,
                     "collected_at": r.collected_at.isoformat()} for r in rows]})

        if metric == "lab_panels":
            from apps.medical.models import LabPanel
            panels = list(LabPanel.objects.filter(user=self.user).order_by("-collected_at"))
            return CurrentTruth.found(
                _DOMAIN, metric, len(panels), CURRENT if panels else MISSING,
                source=_SRC, detail={"panels": [
                    {"name": p.name, "type": p.get_panel_type_display(),
                     "collected_at": p.collected_at.isoformat(),
                     "result_count": p.result_count,
                     "abnormal_count": p.abnormal_count} for p in panels]})

        if metric == "lab_documents":
            from apps.medical.models import MedicalDocument
            docs = list(MedicalDocument.objects.filter(user=self.user).order_by("-created_at"))
            return CurrentTruth.found(
                _DOMAIN, metric, len(docs), CURRENT if docs else MISSING, source=_SRC,
                detail={"documents": [
                    {"filename": d.original_filename, "pages": d.page_count,
                     "uploaded_at": d.created_at.isoformat()} for d in docs]})

        if metric == "latest_labs":
            r = self._results().order_by("-collected_at").first()
            if r is None:
                return CurrentTruth.absent(_DOMAIN, metric, MISSING, source=_SRC,
                                           reason="no lab results recorded")
            return CurrentTruth.found(
                _DOMAIN, metric, r.collected_at.isoformat(), CURRENT, source=_SRC,
                as_of=r.collected_at.isoformat(),
                detail={"latest_test": _test_name(r), "value": r.value_text,
                        "unit": r.unit, "provider": r.provider})

        raise KeyError(f"medical current unsupported: {metric!r} "
                       f"(have {self.current_metrics})")

    # ── HISTORY (a single lab test's numeric value over time) ────────────
    def history(self, metric, period="last_year", **kwargs):
        if metric != "lab_value":
            raise KeyError(f"medical history unsupported: {metric!r} "
                           f"(have {self.history_metrics})")
        test = (kwargs.get("test") or "").strip()
        p = resolve_period(period, _today(self.user),
                           start=kwargs.get("start"), end=kwargs.get("end"))
        if not test:
            return series_from_rows(_DOMAIN, metric, p, [])
        qs = self._results().filter(
            value_numeric__isnull=False,
            collected_at__date__range=(p.start, p.end),
        ).filter(
            Q(canonical_test__name__iexact=test)
            | Q(canonical_test__short_name__iexact=test)
            | Q(raw_test_name__icontains=test)
        ).order_by("collected_at")
        first = qs.first()
        unit = first.unit if first else None
        rows = [{"date": r.collected_at.date(), "value": _num(r.value_numeric)} for r in qs]
        return series_from_rows(_DOMAIN, metric, p, rows, unit=unit)

    # ── ENTITY COMPLETENESS ──────────────────────────────────────────────
    def describe(self, entity_type="lab_result"):
        if entity_type in (None, "lab_result"):
            return [self._lab_result_entity(r) for r in self._latest_per_test()]
        if entity_type == "lab_panel":
            from apps.medical.models import LabPanel
            return [self._panel_entity(p) for p in
                    LabPanel.objects.filter(user=self.user).order_by("-collected_at")]
        if entity_type == "document":
            from apps.medical.models import MedicalDocument
            return [self._document_entity(d) for d in
                    MedicalDocument.objects.filter(user=self.user).order_by("-created_at")]
        raise KeyError(f"medical cannot describe {entity_type!r} "
                       f"(have {self.entity_types})")

    def describe_one(self, name):
        q = (name or "").strip().lower()
        if not q:
            return None
        pool = self._latest_per_test()
        exact = [r for r in pool if _test_name(r).lower() == q]
        partial = [r for r in pool if q in _test_name(r).lower()]
        hit = exact or partial
        if hit:
            return self._lab_result_entity(hit[0])
        # Not a test name — a lab panel or a document by name/identity, so those entity
        # types are reachable by name too (previously only lab results were).
        return self._entity_by_identity(name, ("lab_panel", "document"))

    # ── mappers ──────────────────────────────────────────────────────────
    def _lab_result_entity(self, r):
        from apps.medical.models import LabResult
        key = (dict(canonical_test=r.canonical_test)
               if r.canonical_test_id else dict(raw_test_name=r.raw_test_name))
        series = list(LabResult.objects.filter(user=self.user, **key)
                      .exclude(value_numeric__isnull=True)
                      .order_by("collected_at")
                      .values_list("collected_at", "value_numeric"))
        trend = [{"date": c.date().isoformat(), "value": _num(v)} for c, v in series]
        ct = r.canonical_test
        definition = {
            "raw_test_name": r.raw_test_name,
            "canonical_name": ct.name if ct else None,
            "short_name": ct.short_name if ct else None,
            "category": ct.get_category_display() if ct else None,
            "loinc_code": ct.loinc_code if ct else None,
            "unit": r.unit,
        }
        if ct is not None:
            try:
                edu = ct.education
                definition["what_it_measures"] = edu.what_it_measures
                definition["what_it_reflects"] = edu.what_it_reflects
            except ObjectDoesNotExist:
                pass
        return CompleteEntity(
            kind="lab_result", identity=_test_name(r), status=r.result_status,
            definition=definition,
            plan={"range_low": _num(r.range_low), "range_high": _num(r.range_high),
                  "range_text": r.range_text},
            standing={"value_text": r.value_text, "value_numeric": _num(r.value_numeric),
                      "unit": r.unit, "abnormal_flag": r.abnormal_flag,
                      "status_label": r.status_label, "is_abnormal": r.is_abnormal,
                      "collected_at": r.collected_at.isoformat(),
                      "reported_at": r.reported_at.isoformat() if r.reported_at else None,
                      "date_estimated": r.date_estimated},
            performance={"reading_count": len(trend), "trend": trend,
                         "latest": trend[-1] if trend else None,
                         "earliest": trend[0] if trend else None},
            extensions={"provider": r.provider, "notes": r.notes,
                        "panel": r.panel.name if r.panel_id else None,
                        "source_document": (r.medical_document.original_filename
                                            if r.medical_document_id else None)})

    def _panel_entity(self, p):
        rows = list(p.results.all())
        return CompleteEntity(
            kind="lab_panel", identity=p.name, status="collected",
            definition={"panel_type": p.panel_type,
                        "panel_type_label": p.get_panel_type_display()},
            plan={"collected_at": p.collected_at.isoformat(), "provider": p.provider},
            standing={"result_count": p.result_count, "abnormal_count": p.abnormal_count,
                      "results": [{"test": _test_name(x), "value": x.value_text,
                                   "unit": x.unit, "flag": x.abnormal_flag}
                                  for x in rows]},
            extensions={"notes": p.notes})

    def _document_entity(self, d):
        return CompleteEntity(
            kind="document", identity=d.original_filename, status="stored",
            # file_hash intentionally excluded — implementation metadata (Danny's decision).
            definition={"page_count": d.page_count,
                        "extraction_method": d.extraction_method},
            standing={"uploaded_at": d.created_at.isoformat()},
            performance={"result_count": d.results.count()},
            extensions={"notes": d.notes})
