"""
Cross-Domain Signal Generator.

Reads _contract state from ALL SAE domains and generates deterministic,
explainable signals that connect cause → effect across domains.

Architecture:
    Raw Data → Signals/State → [THIS LAYER] → CoS → LLM
    Input: full multi-domain SAE state (UserState.state_data)
    Output: list of structured signal dicts sorted by severity

Rules:
    - ONLY reads from _contract sub-dicts (never flat keys, never raw DB)
    - All logic is deterministic (no LLM, no ML inference)
    - Every signal includes evidence (traceable to source data)
    - Signals are composable: each detector is independent

Usage:
    from apps.core.ai_signals.cross_domain_signals import (
        generate_cross_domain_signals,
    )
    signals = generate_cross_domain_signals(user_state)
"""

import logging

logger = logging.getLogger(__name__)

# ── Severity/Confidence ordering for sort ──
_SEVERITY_ORDER = {'high': 0, 'medium': 1, 'low': 2}
_CONFIDENCE_ORDER = {'high': 0, 'medium': 1, 'low': 2}


def _get_contract(state, domain):
    """Safely extract _contract from a domain's state dict."""
    domain_data = state.get(domain, {})
    if not isinstance(domain_data, dict):
        return {}
    return domain_data.get('_contract', {})


def _get_meta(state, domain):
    """Safely extract _meta from a domain's state dict."""
    domain_data = state.get(domain, {})
    if not isinstance(domain_data, dict):
        return {}
    return domain_data.get('_meta', {})


# ======================================================================
# Signal Detectors — each returns a list of signal dicts (may be empty)
# ======================================================================


def _detect_financial_pressure(state):
    """Detect financial pressure: overdue bills, over-budget, stacking obligations."""
    signals = []
    fin = _get_contract(state, 'finance')
    if not fin:
        return signals

    summary = fin.get('summary', {})
    alerts = fin.get('alerts', {})

    overdue_bills = alerts.get('overdue_bills', [])
    over_budget = alerts.get('over_budget', [])
    pressure = summary.get('cash_pressure_level', 'low')

    # Overdue financial risk
    if overdue_bills:
        severity = 'high' if len(overdue_bills) >= 3 else 'medium'
        signals.append({
            'signal_code': 'overdue_financial_risk',
            'domains': ['finance'],
            'severity': severity,
            'confidence': 'high',
            'summary': f"{len(overdue_bills)} overdue bill(s) need attention.",
            'evidence': {
                'overdue_count': len(overdue_bills),
                'overdue_names': [b.get('name', '') for b in overdue_bills[:3]],
            },
            'recommended_action': 'Review and pay overdue bills',
        })

    # Financial pressure cluster
    if pressure == 'high' or (overdue_bills and over_budget):
        signals.append({
            'signal_code': 'financial_pressure_cluster',
            'domains': ['finance'],
            'severity': 'high' if pressure == 'high' else 'medium',
            'confidence': 'high',
            'summary': (
                "Financial pressure detected: "
                f"{'high liabilities' if pressure == 'high' else ''}"
                f"{' + over-budget categories' if over_budget else ''}"
                f"{' + overdue bills' if overdue_bills else ''}."
            ).replace(': +', ':').strip(': '),
            'evidence': {
                'cash_pressure_level': pressure,
                'over_budget_count': len(over_budget),
                'overdue_bill_count': len(overdue_bills),
            },
        })

    return signals


def _detect_execution_breakdown(state):
    """Detect execution overload: high obligations + low completion."""
    signals = []
    tasks = _get_contract(state, 'tasks')
    capture = _get_contract(state, 'capture')

    if not tasks:
        return signals

    task_summary = tasks.get('summary', {})
    task_alerts = tasks.get('alerts', {})
    overdue_count = task_alerts.get('overdue_count', 0)
    total_pending = task_summary.get('total_pending', 0)
    momentum = task_summary.get('momentum_signal', 'low')

    # Capture backlog pressure
    cap_summary = capture.get('summary', {}) if capture else {}
    backlog = cap_summary.get('backlog_level', 'low')

    # Execution overload: many overdue + high capture backlog
    if overdue_count >= 3 and backlog in ('medium', 'high'):
        signals.append({
            'signal_code': 'execution_overload',
            'domains': ['tasks', 'capture'],
            'severity': 'high' if overdue_count >= 5 else 'medium',
            'confidence': 'high',
            'summary': (
                f"{overdue_count} overdue tasks + {backlog} capture backlog — "
                "execution capacity may be stretched."
            ),
            'evidence': {
                'overdue_tasks': overdue_count,
                'capture_backlog': backlog,
                'total_pending': total_pending,
            },
            'recommended_action': 'Focus on clearing overdue tasks before new intake',
        })

    # Low execution momentum
    if momentum == 'low' and total_pending >= 5 and overdue_count >= 2:
        signals.append({
            'signal_code': 'low_execution_momentum',
            'domains': ['tasks'],
            'severity': 'medium',
            'confidence': 'high' if total_pending >= 5 else 'medium',
            'summary': (
                f"Low completion momentum today with {overdue_count} overdue "
                f"and {total_pending} pending tasks."
            ),
            'evidence': {
                'momentum_signal': momentum,
                'overdue_count': overdue_count,
                'total_pending': total_pending,
            },
        })

    return signals


def _detect_routine_degradation(state):
    """Detect routine breakdown: missed items, streak risk."""
    signals = []
    routine = _get_contract(state, 'routine')
    if not routine:
        return signals

    summary = routine.get('summary', {})
    missed = summary.get('today_missed', 0)
    total = summary.get('today_count', 0)

    if total == 0:
        return signals

    alerts = routine.get('alerts', {})
    missed_items = alerts.get('missed', [])

    # Routine breakdown: majority missed
    if total > 0 and missed >= total * 0.5 and missed >= 2:
        signals.append({
            'signal_code': 'routine_breakdown',
            'domains': ['routine'],
            'severity': 'high' if missed >= total * 0.75 else 'medium',
            'confidence': 'high',
            'summary': f"{missed} of {total} routine items missed today.",
            'evidence': {
                'missed': missed,
                'total': total,
                'missed_items': [m.get('item_name', '') for m in missed_items[:3]],
            },
            'recommended_action': 'Check in on what disrupted the routine',
        })

    return signals


def _detect_relationship_neglect(state):
    """Detect relationship neglect: key contacts not reached."""
    signals = []
    rel = _get_contract(state, 'relationships')
    if not rel:
        return signals

    alerts = rel.get('alerts', {})
    neglected = alerts.get('neglected', [])

    if len(neglected) >= 3:
        severity = 'high' if len(neglected) >= 5 else 'medium'
        signals.append({
            'signal_code': 'relationship_neglect',
            'domains': ['relationships'],
            'severity': severity,
            'confidence': 'medium',  # interaction data may be incomplete
            'summary': f"{len(neglected)} relationship(s) showing signs of drift.",
            'evidence': {
                'neglected_count': len(neglected),
                'names': [n.get('name', '') for n in neglected[:3]],
                'max_days_since': max(
                    (n.get('days_since_contact') or 0 for n in neglected),
                    default=0,
                ),
            },
            'recommended_action': 'Consider reaching out to someone you miss',
        })

    return signals


def _detect_health_attention(state):
    """Detect health attention: missed meds + abnormal labs."""
    signals = []
    med = _get_contract(state, 'medicine')
    medical = _get_contract(state, 'medical')

    # Medication adherence risk
    if med:
        today = med.get('today', {})
        missed = today.get('missed', 0)
        overdue_meds = med.get('alerts', {}).get('overdue', [])

        if missed >= 2 or len(overdue_meds) >= 2:
            signals.append({
                'signal_code': 'medication_adherence_risk',
                'domains': ['medicine'],
                'severity': 'high' if missed >= 3 else 'medium',
                'confidence': 'high',
                'summary': f"{missed} missed dose(s) today + {len(overdue_meds)} overdue.",
                'evidence': {
                    'missed_today': missed,
                    'overdue_doses': len(overdue_meds),
                },
                'recommended_action': 'Take overdue medications if safe to do so',
            })

    # Combined health attention
    med_missed = med.get('today', {}).get('missed', 0) if med else 0
    abnormal = medical.get('alerts', {}).get('abnormal_results', []) if medical else []

    if med_missed >= 1 and len(abnormal) >= 1:
        signals.append({
            'signal_code': 'health_attention_required',
            'domains': ['medicine', 'medical'],
            'severity': 'high',
            'confidence': 'medium',
            'summary': (
                "Missed medications combined with recent abnormal lab results — "
                "health requires focused attention."
            ),
            'evidence': {
                'missed_meds': med_missed,
                'abnormal_lab_count': len(abnormal),
            },
        })

    return signals


def _detect_cognitive_discipline(state):
    """Detect discipline decline: brain training drop + low task momentum."""
    signals = []
    bt = _get_contract(state, 'brain_training')
    tasks = _get_contract(state, 'tasks')

    if not bt:
        return signals

    bt_summary = bt.get('summary', {})
    bt_alerts = bt.get('alerts', {})

    streak_at_risk = bt_alerts.get('streak_at_risk', False)
    declining = bt_alerts.get('declining_performance', False)

    # Cross with task momentum
    task_momentum = 'low'
    if tasks:
        task_momentum = tasks.get('summary', {}).get('momentum_signal', 'low')

    if (streak_at_risk or declining) and task_momentum == 'low':
        signals.append({
            'signal_code': 'discipline_decline',
            'domains': ['brain_training', 'tasks'],
            'severity': 'medium',
            'confidence': 'medium',
            'summary': (
                "Brain training "
                f"{'streak at risk' if streak_at_risk else 'performance declining'}"
                " combined with low task completion momentum."
            ),
            'evidence': {
                'streak_at_risk': streak_at_risk,
                'declining_performance': declining,
                'task_momentum': task_momentum,
            },
        })

    # Standalone streak risk (single-domain but important)
    if streak_at_risk and not declining:
        signals.append({
            'signal_code': 'consistency_risk',
            'domains': ['brain_training'],
            'severity': 'low',
            'confidence': 'high',
            'summary': "Brain training streak at risk — no session logged recently.",
            'evidence': {'streak_at_risk': True},
        })

    return signals


def _detect_system_overload(state):
    """Detect multi-domain pressure: too many alerts simultaneously."""
    signals = []

    # Count domains with active high-severity alerts
    domain_pressure = {}

    tasks = _get_contract(state, 'tasks')
    if tasks and tasks.get('alerts', {}).get('overdue_count', 0) >= 3:
        domain_pressure['tasks'] = 'overdue tasks'

    fin = _get_contract(state, 'finance')
    if fin and fin.get('alerts', {}).get('overdue_bills'):
        domain_pressure['finance'] = 'overdue bills'

    med = _get_contract(state, 'medicine')
    if med and med.get('today', {}).get('missed', 0) >= 2:
        domain_pressure['medicine'] = 'missed medications'

    routine = _get_contract(state, 'routine')
    if routine and routine.get('summary', {}).get('today_missed', 0) >= 2:
        domain_pressure['routine'] = 'missed routines'

    capture = _get_contract(state, 'capture')
    if capture and capture.get('summary', {}).get('backlog_level') == 'high':
        domain_pressure['capture'] = 'high capture backlog'

    if len(domain_pressure) >= 3:
        signals.append({
            'signal_code': 'system_overload',
            'domains': list(domain_pressure.keys()),
            'severity': 'high',
            'confidence': 'high',
            'summary': (
                f"Pressure detected across {len(domain_pressure)} domains: "
                f"{', '.join(domain_pressure.values())}."
            ),
            'evidence': domain_pressure,
            'recommended_action': (
                'Focus on one domain at a time — start with the most urgent'
            ),
        })
    elif len(domain_pressure) == 2:
        signals.append({
            'signal_code': 'multi_domain_pressure',
            'domains': list(domain_pressure.keys()),
            'severity': 'medium',
            'confidence': 'high',
            'summary': (
                f"Pressure in {len(domain_pressure)} domains: "
                f"{', '.join(domain_pressure.values())}."
            ),
            'evidence': domain_pressure,
        })

    return signals


# ======================================================================
# Public API
# ======================================================================

# All detectors, in evaluation order
_DETECTORS = [
    _detect_financial_pressure,
    _detect_execution_breakdown,
    _detect_routine_degradation,
    _detect_relationship_neglect,
    _detect_health_attention,
    _detect_cognitive_discipline,
    _detect_system_overload,
]


def generate_cross_domain_signals(user_state: dict) -> list:
    """Generate cross-domain signals from full SAE state.

    Args:
        user_state: Full UserState.state_data dict (keyed by domain name).

    Returns:
        List of signal dicts, sorted by severity (high first), then confidence.
        Deduplicated by signal_code.
    """
    all_signals = []
    seen_codes = set()

    for detector in _DETECTORS:
        try:
            results = detector(user_state)
            for signal in results:
                code = signal.get('signal_code')
                if code and code not in seen_codes:
                    seen_codes.add(code)
                    all_signals.append(signal)
        except Exception:
            logger.warning(
                "Cross-domain signal detector %s failed",
                detector.__name__,
                exc_info=True,
            )

    # Sort by severity (high first), then confidence (high first)
    all_signals.sort(key=lambda s: (
        _SEVERITY_ORDER.get(s.get('severity', 'low'), 2),
        _CONFIDENCE_ORDER.get(s.get('confidence', 'low'), 2),
    ))

    return all_signals


def generate_signal_summary(signals: list) -> dict:
    """Generate an aggregation summary of cross-domain signals.

    Args:
        signals: Output from generate_cross_domain_signals().

    Returns:
        Dict with top_signal, signal_count, severity breakdown.
    """
    if not signals:
        return {
            'top_signal': None,
            'signal_count': 0,
            'high_severity_count': 0,
            'medium_severity_count': 0,
            'domains_affected': [],
        }

    high = [s for s in signals if s.get('severity') == 'high']
    medium = [s for s in signals if s.get('severity') == 'medium']

    # Unique domains across all signals
    all_domains = set()
    for s in signals:
        all_domains.update(s.get('domains', []))

    return {
        'top_signal': signals[0].get('signal_code'),
        'top_signal_summary': signals[0].get('summary'),
        'signal_count': len(signals),
        'high_severity_count': len(high),
        'medium_severity_count': len(medium),
        'domains_affected': sorted(all_domains),
    }
