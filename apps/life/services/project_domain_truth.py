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

    _MAX_TASKS = 60          # bound the payload; standing.task_count carries the true total

    def _project_entity(self, p):
        # Child TASK records — the SAME canonical Task rows the Tasks domain owns (via the
        # Project FK), surfaced here SCOPED to this project so the CoS can answer "what's open /
        # done / what's next / what's stalled on this project" instead of only counts. This is a
        # REFERENCE to the canonical Task authority, not a second producer (III.1): every field
        # comes straight from the Task model, and the Tasks domain remains the owner. `p.tasks.all()`
        # is prefetch-cached in describe() and already ordered (Task.Meta: status, priority, due_date).
        tasks = [
            {"title": t.title,
             "status": t.completion_status,
             "due_date": t.due_date.isoformat() if t.due_date else None,
             "completed_at": (t.completed_at.isoformat()
                              if getattr(t, "completed_at", None) else None),
             "priority": t.priority}
            for t in list(p.tasks.all())[:self._MAX_TASKS]
        ]
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
            # Canonical Task records for this project (reference, not a second authority).
            extensions={"tasks": tasks} if tasks else {},
            freshness=F.CURRENT,
        )
