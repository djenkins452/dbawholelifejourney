"""
Platform capability: DOMAIN TRUTH OBJECTS.

The single canonical interface to a domain's truth. Every consumer — Beth,
dashboards, reports, exports, APIs, notifications, domain engines, cross-domain
engines, future interfaces — asks the same object the same way:

    truth = get_domain_truth(user, "health")
    truth.current("sleep_last_night")          # -> CurrentTruth   (now)
    truth.history("steps", "last_week")        # -> HistorySeries  (back then)
    truth.state()                              # -> SAE snapshot dict (composed current state)

A `DomainTruth` is a THIN FACADE: it composes the lower platform capabilities
(Current Truth, Point-in-Time History, Freshness, the SAE snapshot) and owns NO new
retrieval logic. Capabilities are the components; the Domain Truth Object is the
interface. This is the per-domain registration unit the Deterministic Provider
Registry will route over.
"""
import logging
from importlib import import_module

_log = logging.getLogger(__name__)

# The synthetic WHOLE-DOMAIN analysis subject. Any domain that declares >= 2 analyzable
# subjects ALSO supports "overall" — the composed roll-up of every subject (the
# whole-domain analogue of a single-subject analysis; see
# apps/ai/cos_services/domain_analysis.py :: _domain_overview). It is advertised HERE,
# in the one catalog source `supports()` builds, so the capability index the model reads
# ("what can I analyze") stays aligned BY CONSTRUCTION with what get_analysis accepts — it
# can never silently drift from a domain's declared `analysis_subjects`. This closes the
# class where "analyze/summarize my WHOLE <domain>" (e.g. "overall health this week") had
# no analyzable subject and returned `unsupported`, even though the per-subject truth all
# existed. NOT a per-domain registration — it appears automatically for every multi-subject
# domain, and never for single-subject ones (where "overall" == the one subject).
WHOLE_DOMAIN_SUBJECT = "overall"

# Domain provider modules that self-register on import (lazy-loaded on first miss).
_KNOWN_PROVIDER_MODULES = (
    "apps.health.services.health_domain_truth",
    "apps.health.services.medicine_domain_truth",   # Medication Canonical Truth
    "apps.finance.services.finance_domain_truth",
    "apps.purpose.services.goal_domain_truth",       # Goals / Missions Canonical Truth
    "apps.life.services.project_domain_truth",        # Projects Canonical Truth
    "apps.life.services.event_domain_truth",          # Significant Events Canonical Truth
    "apps.meals.services.meals_domain_truth",         # Meal Intelligence Canonical Truth
    "apps.medical.services.medical_domain_truth",     # Medical / Lab Canonical Truth
    "apps.purpose.services.habit_domain_truth",       # Habits Canonical Truth
    "apps.notes.notes_domain_truth",                  # Notes Canonical Truth
    "apps.capture.services.capture_domain_truth",     # Capture Canonical Truth
    "apps.capture.services.artifact_domain_truth",     # Uploaded Artifacts as Truth (retrieval)
    "apps.brain_training.services.brain_training_domain_truth",  # Brain Training Canonical Truth
    "apps.core.truth.domain_rollout",   # journal, calendar, tasks, faith, relationships
)

_REGISTRY = {}


def register_domain_truth(cls):
    """Class decorator — register a DomainTruth subclass under its `domain`."""
    if not getattr(cls, "domain", None):
        raise ValueError("DomainTruth subclass must set `domain`")
    _REGISTRY[cls.domain] = cls
    return cls


def get_domain_truth(user, domain):
    """Return the registered DomainTruth for `domain`, bound to `user`."""
    if domain not in _REGISTRY:
        for mod in _KNOWN_PROVIDER_MODULES:        # trigger self-registration
            try:
                import_module(mod)
            except Exception:
                pass
    cls = _REGISTRY.get(domain)
    if cls is None:
        raise KeyError(f"no DomainTruth registered for {domain!r}; "
                       f"have {sorted(_REGISTRY)}")
    return cls(user)


def registered_domains():
    for mod in _KNOWN_PROVIDER_MODULES:
        try:
            import_module(mod)
        except Exception:
            pass
    return sorted(_REGISTRY)


class DomainTruth:
    """Base facade. Subclasses implement `current()` / `history()` by delegating to
    the domain's Current Truth + History providers. `state()` is shared — it reads the
    pre-computed SAE module snapshot (never live-computes on the request path)."""

    domain = None
    current_metrics = ()          # introspection: metrics current() supports
    history_metrics = ()          # introspection: metrics history() supports
    reading_metrics = ()          # introspection: metrics readings() supports (intra-day)
    event_frequency_metrics = ()  # introspection: metrics event_frequency() supports
    consistency_metrics = ()      # introspection: metrics consistency() supports

    def __init__(self, user):
        self.user = user

    def current(self, metric):
        raise NotImplementedError

    def history(self, metric, period="last_7_days", **kwargs):
        raise NotImplementedError

    # READING-WINDOW CAPABILITY (intra-day / high-frequency truth) -------------
    # The datetime-window companion to history(). history() answers "the per-DAY trend
    # over a Period"; readings() answers "the individual SAMPLES inside a datetime
    # Window, plus window statistics and excursions" — the shape a person asks about a
    # CGM/heart-rate/SpO2 stream ("my lows overnight", "readings for the past 12 hours").
    # A domain opts in by declaring `reading_metrics` and returning a
    # ReadingSeries.to_dict() (see apps.core.truth.reading_window). Glucose is the
    # reference adopter. Default: the domain exposes no reading metrics.
    def readings(self, metric, window):
        """Return a ReadingSeries dict (apps.core.truth.reading_window) for `metric`
        over `window` (apps.core.truth.windows.Window). Raise KeyError for an
        unsupported metric."""
        raise NotImplementedError(
            f"{self.domain} domain truth exposes no readings()")

    # EVENT-FREQUENCY CAPABILITY (how often an event happens over time) --------
    # The SERIES companion to readings(). readings() answers "what were my lows THIS
    # night"; event_frequency() answers "are my lows becoming MORE FREQUENT" — one event
    # count per recurring window (each night/day/…), plus the frequency trend + time-of-
    # day clustering (see apps.core.truth.event_frequency). A domain opts in by declaring
    # `event_frequency_metrics` and returning an EventFrequencySeries.to_dict(). The
    # caller (Model Interface) resolves the recurring `windows`; the domain owns ONE bulk
    # query; the platform owns the counts (build_reading_series) and the trend (Trend).
    def event_frequency(self, metric, event, windows):
        """Return an EventFrequencySeries dict (apps.core.truth.event_frequency) counting
        `event` (e.g. 'low') for `metric` across the recurring `windows`
        (apps.core.truth.windows.Window list). Raise KeyError for an unsupported metric."""
        raise NotImplementedError(
            f"{self.domain} domain truth exposes no event_frequency()")

    # CONSISTENCY CAPABILITY (how regular is a repeated observation over time) --------
    # history() answers "is my bedtime getting earlier" (the LEVEL); consistency() answers
    # "is my bedtime becoming more REGULAR" (the SPREAD) — the centre, dispersion (std dev /
    # MAD / range), most/least regular observation, and the arithmetic change in that spread
    # (see apps.core.truth.consistency; clock fields use midnight-safe circular statistics).
    # A domain opts in by declaring `consistency_metrics` and returning the consistency dict.
    # The caller (Model Interface) resolves the (start, end) period; the domain owns ONE bulk
    # query; the platform owns the statistics. Sleep is the reference adopter.
    def consistency(self, metric, start_date, end_date, period_label=""):
        """Return a consistency dict (apps.core.truth.consistency) describing the regularity
        of `metric` over [start_date, end_date]. Raise KeyError for an unsupported metric."""
        raise NotImplementedError(
            f"{self.domain} domain truth exposes no consistency()")

    def state(self):
        from apps.core.ai_state.state_engine import get_module_state
        # Self-heal manual-entry staleness BEFORE reading the snapshot — the SAME
        # shared guard the dashboard uses (apps/ai/signals.py async refresh can be
        # missed/lagged; this makes the snapshot current on read). No-op for non-
        # manual domains; light stale-only rebuild for journal/nutrition. Never
        # raises — a freshness failure must not break a truth read (it is logged).
        try:
            from apps.core.ai_state.state_freshness import ensure_fresh
            ensure_fresh(self.user, [self.domain])
        except Exception:
            _log.warning("DomainTruth.state freshness check failed domain=%s",
                         self.domain, exc_info=True)
        return get_module_state(self.user, self.domain, allow_rebuild=False) or {}

    # ENTITY COMPLETENESS LAW (reusable Layer 1 pattern) ----------------------
    # THE LAW: a canonical entity is complete when it can completely answer the natural
    # business questions about itself from a SINGLE deterministic retrieval. Higher layers
    # retrieve that one complete object; they never assemble fragmented truth from many
    # calls. `describe(entity_type)` is that single retrieval — it returns the domain's
    # canonical entities, each a `CompleteEntity` (the current canonical implementation of
    # the law; the dimension set is open). Medication is the reference impl. See
    # apps/core/truth/entity.py + docs/LAYER1_ENTITY_COMPLETENESS_CONTRACT.md.
    entity_types = ()             # introspection: entity types describe() supports

    def describe(self, entity_type=None):
        """Single deterministic retrieval of the domain's canonical entities, each a
        `CompleteEntity` that can answer the natural questions about itself."""
        raise NotImplementedError(f"{self.domain} domain truth exposes no describe()")

    def _entity_by_identity(self, name, types):
        """Reusable by-name fallback for MULTI-entity domains: return the `CompleteEntity`
        across `types` whose identity matches `name` (exact preferred, else substring),
        by reusing each type's own `describe()` composer — so by-name retrieval returns the
        SAME complete object as the list path for EVERY entity type, not just one. `types`
        ordering also sets cross-type precedence. This closes the SUBSET defect class where
        `describe_one` covered only one of several entity_types (the rest returned nothing
        by name while list retrieval succeeded). No parallel retrieval logic — describe() is
        the single authority."""
        n = (name or "").strip().lower()
        if not n:
            return None

        def _ident(e):
            if isinstance(e, dict):
                return str(e.get("identity") or e.get("name") or e.get("title") or "")
            return str(getattr(e, "identity", "") or "")

        pools = []
        for et in types:
            try:
                pools.append(list(self.describe(et) or []))
            except Exception:
                pools.append([])
        for pool in pools:                      # exact identity, in type order
            for e in pool:
                if _ident(e).strip().lower() == n:
                    return e
        for pool in pools:                      # then substring, in type order
            for e in pool:
                if n in _ident(e).strip().lower():
                    return e
        return None

    # ANALYSIS COMPLETENESS LAW (the investigate-before-concluding guarantee) --------
    # THE LAW: when the user's intent is ANALYSIS of a subject, the Chief of Staff must
    # investigate the deterministic truth WLJ holds before it may conclude "insufficient".
    # A prompt can only REQUEST that; it cannot GUARANTEE it. So WLJ performs the
    # investigation DETERMINISTICALLY: the Analysis surface composes EVERY relevant
    # retrieval for a subject (history across trailing windows + record detail + all-time
    # span/count) into ONE bundle carrying a deterministic completeness verdict
    # (holds_data / evidence). Composition, not reasoning — the model still reasons over
    # the bundle. Because one call returns the whole evidence set, the model can neither
    # under-gather nor truthfully claim "insufficient" while WLJ still holds the truth.
    # A domain declares its analyzable subjects here; the generic composer
    # (apps/ai/cos_services/domain_analysis.py) reuses history()/describe() — no new
    # retrieval logic. `subject -> {history_metric, entity_type, windows}`.
    analysis_subjects = {}        # introspection: subjects the Analysis surface can compose

    def supports(self):
        subjects = tuple(self.analysis_subjects)
        analysis = subjects
        # WHOLE-DOMAIN EXECUTIVE ASSESSMENT coverage is a PROPERTY OF COMPOSED TRUTH, not of
        # manual registration. A domain earns "overall" (the composed state+trends bundle the
        # model reasons an executive assessment from — see
        # apps/ai/cos_services/domain_analysis.py :: _domain_overview) the moment WLJ composes
        # >= 2 assessment facets for it: >= 2 analyzable subjects, OR >= 2 history metrics
        # (trend facets), OR >= 2 current metrics (state facets). This removes the
        # registration-drift class where a domain with real truth still answered "unsupported"
        # for a broad question, and it means a maturing domain lights up automatically as it
        # composes truth — no separate registration step, never Health-special.
        if WHOLE_DOMAIN_SUBJECT not in subjects and (
                len(subjects) >= 2
                or len(self.history_metrics) >= 2
                or len(self.current_metrics) >= 2):
            analysis = (WHOLE_DOMAIN_SUBJECT,) + subjects
        return {"current": tuple(self.current_metrics),
                "history": tuple(self.history_metrics),
                "readings": tuple(self.reading_metrics),
                "event_frequency": tuple(self.event_frequency_metrics),
                "consistency": tuple(self.consistency_metrics),
                "entities": tuple(self.entity_types),
                "analysis": analysis}
