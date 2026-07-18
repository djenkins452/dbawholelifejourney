"""ProjectDomainTruth — canonical interface to Projects truth.

Thin facade over ProjectQueries + Project model properties. Read-only; owns no new
retrieval logic. There is no SAE 'projects' module, so current() queries ProjectQueries
directly (like GoalDomainTruth), never state(). Projects had a full model but ZERO
retrieval plumbing — this exposes it.
"""
from apps.core.truth import freshness as F
from apps.core.truth.current import CurrentTruth
from apps.core.truth.domain import DomainTruth, register_domain_truth
from apps.core.truth.entity import CompleteEntity

_DOMAIN = "projects"


@register_domain_truth
class ProjectDomainTruth(DomainTruth):
    domain = "projects"
    current_metrics = ("active_projects",)
    history_metrics = ()
    entity_types = ("project",)

    def current(self, metric):
        from apps.life.services.project_queries import ProjectQueries
        if metric == "active_projects":
            projects = list(ProjectQueries.active(self.user)
                            .order_by("priority", "-created_at"))
            if not projects:
                return CurrentTruth.absent(_DOMAIN, metric, F.MISSING,
                                           source="project_queries",
                                           reason="no active projects")
            return CurrentTruth.found(
                _DOMAIN, metric, len(projects), F.CURRENT, source="project_queries",
                detail={"projects": [
                    {"title": p.title, "status": p.status, "priority": p.priority,
                     "target_date": p.target_date.isoformat() if p.target_date else None,
                     "progress_percentage": p.progress_percentage,
                     "task_count": p.task_count,
                     "completed_task_count": p.completed_task_count}
                    for p in projects]})
        raise KeyError(f"projects current unsupported: {metric!r} "
                       f"(have {self.current_metrics})")

    def describe(self, entity_type="project"):
        if entity_type not in (None, "project"):
            raise KeyError(f"projects domain cannot describe {entity_type!r} "
                           f"(have {self.entity_types})")
        from apps.life.services.project_queries import ProjectQueries
        return [self._project_entity(p)
                for p in ProjectQueries.active(self.user).prefetch_related("tasks")]

    def describe_one(self, name):
        from apps.life.models import Project
        q = (name or "").strip()
        if not q:
            return None
        p = (Project.all_objects.filter(user=self.user, title__icontains=q)
             .order_by("status", "-created_at").first())
        return self._project_entity(p) if p else None

    def _project_entity(self, p):
        return CompleteEntity(
            kind="project",
            identity=p.title,
            definition={"description": (p.description_plain or "").strip(),
                        "purpose": (p.purpose_plain or "").strip(),
                        "priority": p.priority,
                        "category": p.category or None,
                        "tags": list(p.tags or []),
                        "cover_image_url": (p.cover_image.url
                                            if getattr(p, "cover_image", None) else None)},
            status=p.status,
            plan={"target_date": p.target_date.isoformat() if p.target_date else None,
                  "start_date": p.start_date.isoformat() if p.start_date else None},
            standing={"is_overdue": p.is_overdue,
                      "task_count": p.task_count,
                      "completed_task_count": p.completed_task_count,
                      "progress_percentage": p.progress_percentage},
            performance={"completed_date": p.completed_date.isoformat()
                         if p.completed_date else None,
                         "reflection": (p.reflection_plain or "").strip()},
            freshness=F.CURRENT,
        )
