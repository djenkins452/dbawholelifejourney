"""
Platform capability: TRUTH CATALOG (Capabilities).

The enumerable surface of Layer 1 — "what truth can WLJ deterministically answer?"
It aggregates every registered Domain Truth Object's `supports()` into one queryable
catalog: per domain, which metrics are answerable as Current Truth and as History.

Consumers: the Deterministic Provider Registry (discover what each domain answers),
Beth (know what she can be asked before reaching for the LLM), dashboards/reports
(render only answerable truth), and certification (a single artifact proving the
Layer 1 truth surface). Reads class-level declarations only — no user data, no I/O.
"""


def truth_catalog():
    """{domain: {"current": (...metrics), "history": (...metrics)}} for all domains."""
    from apps.core.truth.domain import get_domain_truth, registered_domains
    catalog = {}
    for domain in registered_domains():
        catalog[domain] = get_domain_truth(None, domain).supports()
    return catalog


def can_answer(domain, metric, kind="current"):
    """True if `domain` can answer `metric` as `kind` ("current" | "history")."""
    return metric in truth_catalog().get(domain, {}).get(kind, ())


def answerable_metrics(domain, kind="current"):
    return tuple(truth_catalog().get(domain, {}).get(kind, ()))


def catalog_summary():
    """Counts for certification / dashboards: domains and total answerable truths."""
    cat = truth_catalog()
    current = sum(len(v.get("current", ())) for v in cat.values())
    history = sum(len(v.get("history", ())) for v in cat.values())
    return {"domains": sorted(cat),
            "domain_count": len(cat),
            "current_metric_count": current,
            "history_metric_count": history,
            "total_answerable": current + history}
