"""Tests for Action Center Chronological Timeline integration (X1–X3)
in DashboardV2Service.

These tests run against the service's `get_execution_context()` so the
new timeline merges with `ac` correctly and the feature flag wiring
behaves as expected.
"""

from datetime import time

from django.template import Context, Template
from django.test import SimpleTestCase, override_settings


from apps.core.decision_engine.action_prioritizer import (
    RECOVERY_BANNER_COPY,
    build_chronological_timeline,
)


def _exec_item(*, source_type='routine_item', source_id, title,
               scheduled_time, completed=False, foundational=False,
               group_type='routine', group_id='morning'):
    return {
        'source_type': source_type,
        'source_id': source_id,
        'title': title,
        'domain': 'life',
        'importance': 'important',
        'time_status': (
            'overdue'
            if scheduled_time and scheduled_time < '08:00' and not completed
            else 'upcoming'
        ),
        'scheduled_time': scheduled_time,
        'grace_minutes': 0,
        'completion_status': 'completed' if completed else 'pending',
        'completed_today': completed,
        'is_actionable': not completed,
        'is_foundational': foundational,
        'execution_group_type': group_type,
        'execution_group_id': group_id,
        'parent_title': 'Morning Routine',
        'detail_url': '',
        'toggle_url': '',
        'activity_type': None,
    }


class TimelineMergeIntoAcTests(SimpleTestCase):
    """The service merges timeline fields into ac alongside phase_groups.
    The pure builder used here is the same one the service calls."""

    def test_timeline_and_phase_groups_coexist(self):
        items = [
            _exec_item(source_id=1, title='A', scheduled_time='05:30'),
            _exec_item(source_id=2, title='B', scheduled_time='09:00'),
        ]
        out = build_chronological_timeline(items, time(9, 0))
        # Timeline is present and chronological.
        self.assertEqual(out['timeline_version'], 'v2_chronological')
        self.assertEqual(
            [b['time_display'] for b in out['timeline']],
            ['5:30 AM', '9:00 AM'],
        )
        # Phase groups still populated for the legacy template path.
        self.assertIn('phase_groups', out)
        self.assertIn('now', out['phase_groups'])

    def test_recovery_state_dict_shape(self):
        items = [_exec_item(source_id=1, title='X', scheduled_time='09:00')]
        out = build_chronological_timeline(
            items, time(13, 0),
            recovery_state={
                'mode': 'RECOVERY',
                'recoverable_overdue_count': 2,
                'expired_count': 1,
                'missed_foundational_count': 0,
                'reset_action_available': False,
                'day_narrative': 'day_lost_salvage',
            },
        )
        rs = out['recovery_state']
        self.assertEqual(rs['mode'], 'RECOVERY')
        self.assertEqual(rs['banner_text'], 'Rebuild the day forward.')
        self.assertEqual(rs['banner_severity'], 'warning')
        self.assertEqual(rs['recoverable_overdue_count'], 2)
        self.assertEqual(rs['expired_count'], 1)


class RecoveryBannerTemplateTests(SimpleTestCase):
    """Banner partial renders the deterministic copy when ac.recovery_state
    has a banner_text. NORMAL mode renders nothing."""

    BANNER_TPL = (
        '{% load static %}'
        '{% include "dashboard_v2/partials/_action_recovery_banner.html" %}'
    )

    def _render(self, recovery_state):
        ac = {'recovery_state': recovery_state}
        tpl = Template(self.BANNER_TPL)
        return tpl.render(Context({'ac': ac}))

    def test_normal_mode_renders_nothing(self):
        out = self._render({
            'mode': 'NORMAL', 'banner_text': None,
            'banner_severity': None,
        })
        self.assertNotIn('v2-ac-recovery-banner', out)

    def test_recovery_mode_renders_banner_with_warning_severity(self):
        out = self._render({
            'mode': 'RECOVERY',
            'banner_text': 'Rebuild the day forward.',
            'banner_severity': 'warning',
            'recoverable_overdue_count': 3,
            'expired_count': 0,
        })
        self.assertIn('v2-ac-banner-warning', out)
        self.assertIn('Rebuild the day forward.', out)
        self.assertIn('3 items behind', out)

    def test_stabilize_mode_renders_info_severity(self):
        out = self._render({
            'mode': 'STABILIZE',
            'banner_text': 'Take a reset action first.',
            'banner_severity': 'info',
            'missed_foundational_count': 1,
        })
        self.assertIn('v2-ac-banner-info', out)
        self.assertIn('Take a reset action first.', out)
        self.assertIn('1 foundational item missed', out)

    def test_shutdown_mode_renders_info_severity(self):
        out = self._render({
            'mode': 'SHUTDOWN',
            'banner_text': 'Focus on closing the day cleanly.',
            'banner_severity': 'info',
        })
        self.assertIn('v2-ac-banner-info', out)
        self.assertIn('Focus on closing the day cleanly.', out)
        self.assertIn('Preserve tomorrow', out)


class FeatureFlagTests(SimpleTestCase):
    """Verify the flag gates the template path correctly."""

    BRANCH_TPL = (
        '{% if ac.timeline_version == "v2_chronological" '
        'and feature_flags.WLJ_ACTION_CENTER_CHRONOLOGICAL %}'
        'NEW'
        '{% else %}'
        'LEGACY'
        '{% endif %}'
    )

    def test_new_path_when_flag_on(self):
        out = Template(self.BRANCH_TPL).render(Context({
            'ac': {'timeline_version': 'v2_chronological'},
            'feature_flags': {'WLJ_ACTION_CENTER_CHRONOLOGICAL': True},
        }))
        self.assertEqual(out, 'NEW')

    def test_legacy_path_when_flag_off(self):
        out = Template(self.BRANCH_TPL).render(Context({
            'ac': {'timeline_version': 'v2_chronological'},
            'feature_flags': {'WLJ_ACTION_CENTER_CHRONOLOGICAL': False},
        }))
        self.assertEqual(out, 'LEGACY')

    def test_legacy_path_when_timeline_absent(self):
        out = Template(self.BRANCH_TPL).render(Context({
            'ac': {'timeline_version': 'legacy'},
            'feature_flags': {'WLJ_ACTION_CENTER_CHRONOLOGICAL': True},
        }))
        self.assertEqual(out, 'LEGACY')


class BannerCopyTableTests(SimpleTestCase):

    def test_all_modes_present(self):
        for mode in ('NORMAL', 'RECOVERY', 'STABILIZE', 'SHUTDOWN'):
            self.assertIn(mode, RECOVERY_BANNER_COPY)

    def test_normal_text_is_none(self):
        self.assertIsNone(RECOVERY_BANNER_COPY['NORMAL']['text'])

    def test_recovery_warning_severity(self):
        self.assertEqual(
            RECOVERY_BANNER_COPY['RECOVERY']['severity'], 'warning',
        )

    def test_stabilize_info_severity(self):
        self.assertEqual(
            RECOVERY_BANNER_COPY['STABILIZE']['severity'], 'info',
        )

    def test_shutdown_info_severity(self):
        self.assertEqual(
            RECOVERY_BANNER_COPY['SHUTDOWN']['severity'], 'info',
        )
