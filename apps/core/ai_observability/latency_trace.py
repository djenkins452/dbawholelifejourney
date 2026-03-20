"""
Latency Trace — Lightweight per-request latency instrumentation for Beth.

Records timestamped stages through the message pipeline and produces
a structured latency report. Designed for production diagnostics —
minimal overhead, fire-and-forget persistence, never breaks the
critical path.

Usage in pipeline code:

    from apps.core.ai_observability.latency_trace import LatencyTrace

    trace = LatencyTrace(user_id=user.id)
    trace.start('ROUTER_CLASSIFICATION')
    result = classify_and_route(msg, user)
    trace.end('ROUTER_CLASSIFICATION')
    ...
    trace.set_meta('model', settings.OPENAI_MODEL)
    trace.set_meta('prompt_tokens', 6120)
    ...
    trace.report()  # Logs structured report + persists to DB

Project: Whole Life Journey
Path: apps/core/ai_observability/latency_trace.py
"""

import logging
import time
from collections import OrderedDict

logger = logging.getLogger('wlj.latency')


class LatencyTrace:
    """
    Lightweight per-request latency tracer.

    Records start/end timestamps for named stages, computes durations,
    and emits a structured latency report to logs + optional DB persistence.

    Thread-safe for the request thread (not designed for cross-thread use;
    each thread should have its own LatencyTrace if needed).
    """

    def __init__(self, user_id=None, path='non_stream'):
        self.user_id = user_id
        self.path = path  # 'non_stream' or 'stream'
        self._stages = OrderedDict()  # {label: {'start': float, 'end': float}}
        self._meta = {}  # Arbitrary key-value metadata (model, tokens, etc.)
        self._total_start = time.monotonic()

    def start(self, label):
        """Mark the start of a named stage."""
        self._stages[label] = {'start': time.monotonic(), 'end': None}

    def end(self, label):
        """Mark the end of a named stage. No-op if label not started."""
        if label in self._stages:
            self._stages[label]['end'] = time.monotonic()

    def set_meta(self, key, value):
        """Store arbitrary metadata (model name, token counts, etc.)."""
        self._meta[key] = value

    def set_token_report(self, component, count):
        """Record per-component token count for the assembled prompt."""
        if '_token_report' not in self._meta:
            self._meta['_token_report'] = {}
        self._meta['_token_report'][component] = count

    def set_governance_decision(self, decision_type, detail=None):
        """Record a token governance decision (intent_bypassed, framework_skipped, etc.)."""
        if '_governance' not in self._meta:
            self._meta['_governance'] = []
        entry = decision_type if not detail else f"{decision_type}:{detail}"
        self._meta['_governance'].append(entry)

    def get_duration_ms(self, label):
        """Get duration of a completed stage in milliseconds, or None."""
        stage = self._stages.get(label)
        if stage and stage['start'] is not None and stage['end'] is not None:
            return (stage['end'] - stage['start']) * 1000
        return None

    def get_total_ms(self):
        """Get total elapsed time since trace creation."""
        return (time.monotonic() - self._total_start) * 1000

    def report(self):
        """
        Emit a structured latency report to logs and persist to DB.

        Log format is a multi-line block designed for production log search:
            BETH_LATENCY_REPORT user=<id> path=<stream|non_stream>
            Total: 31200ms
            ROUTER_CLASSIFICATION: 50ms
            COS_CONTEXT_BUILD_TOTAL: 14800ms
              COS_BUILDER_health: 2100ms
              COS_BUILDER_tasks: 1800ms
              ...
        """
        total_ms = self.get_total_ms()

        lines = [
            f"BETH_LATENCY_REPORT user={self.user_id} path={self.path} total={total_ms:.0f}ms",
        ]

        # Separate builder sub-stages from top-level stages
        top_stages = []
        builder_stages = []
        for label, data in self._stages.items():
            dur = self.get_duration_ms(label)
            dur_str = f"{dur:.0f}ms" if dur is not None else "OPEN"
            if label.startswith('COS_BUILDER_'):
                builder_stages.append((label, dur_str, dur))
            else:
                top_stages.append((label, dur_str, dur))

        for label, dur_str, _ in top_stages:
            lines.append(f"  {label}: {dur_str}")
            # Inline builder breakdown under COS_CONTEXT_BUILD_TOTAL
            if label == 'COS_CONTEXT_BUILD_TOTAL' and builder_stages:
                # Sort builders by duration descending (slowest first)
                sorted_builders = sorted(
                    builder_stages,
                    key=lambda x: x[2] if x[2] is not None else 0,
                    reverse=True,
                )
                for blabel, bdur, _ in sorted_builders:
                    short_name = blabel.replace('COS_BUILDER_', '')
                    lines.append(f"    {short_name}: {bdur}")

        # Token report (per-component breakdown)
        token_report = self._meta.get('_token_report')
        if token_report:
            lines.append("  TOKEN_REPORT:")
            total_tokens = 0
            for comp, count in sorted(token_report.items(), key=lambda x: -x[1]):
                lines.append(f"    {comp}: {count}")
                total_tokens += count
            lines.append(f"    TOTAL: {total_tokens}")

        # Governance decisions
        governance = self._meta.get('_governance')
        if governance:
            lines.append(f"  GOVERNANCE: {', '.join(governance)}")

        # Metadata (model, tokens, etc.) — exclude internal keys
        display_meta = {
            k: v for k, v in self._meta.items()
            if not k.startswith('_')
        }
        if display_meta:
            meta_parts = [f"{k}={v}" for k, v in display_meta.items()]
            lines.append(f"  META: {', '.join(meta_parts)}")

        report_text = "\n".join(lines)
        logger.warning(report_text)

        # Persist to DB (fire-and-forget)
        self._persist(total_ms)

        return report_text

    def to_dict(self):
        """Return structured dict for API/JSON consumption."""
        result = {
            'user_id': self.user_id,
            'path': self.path,
            'total_ms': round(self.get_total_ms(), 1),
            'stages': {},
            'meta': dict(self._meta),
        }
        for label, data in self._stages.items():
            dur = self.get_duration_ms(label)
            result['stages'][label] = round(dur, 1) if dur is not None else None
        return result

    def _persist(self, total_ms):
        """Fire-and-forget DB persistence of the latency snapshot."""
        try:
            from apps.core.ai_observability.models import ChatLatencySnapshot

            stages_dict = {}
            for label, data in self._stages.items():
                dur = self.get_duration_ms(label)
                if dur is not None:
                    stages_dict[label] = round(dur, 1)

            ChatLatencySnapshot.objects.create(
                user_id=self.user_id,
                path=self.path,
                total_ms=round(total_ms, 1),
                stages=stages_dict,
                meta=dict(self._meta),
            )
        except Exception as e:
            logger.debug("Latency snapshot persist failed: %s", e)
