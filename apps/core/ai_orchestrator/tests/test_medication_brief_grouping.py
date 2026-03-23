"""Tests for medication grouping in daily scan brief.

Validates _group_medications_for_brief produces correct window-grouped
summaries for the CoS daily scan brief. Medical domain ONLY — routines,
faith, journal, goals must be unaffected.
"""

from django.test import SimpleTestCase

from apps.core.ai_orchestrator.cos_context import _group_medications_for_brief


class TestMedicationBriefGroupingCompleted(SimpleTestCase):
    """Test completed mode grouping."""

    def test_all_taken_one_window(self):
        meds = [
            {'medicine_name': 'Metformin', 'window_label': 'morning', 'status': 'taken'},
            {'medicine_name': 'Lantus', 'window_label': 'morning', 'status': 'taken'},
        ]
        completed, outstanding = _group_medications_for_brief(meds, mode='completed')
        self.assertEqual(len(completed), 1)
        self.assertIn('Morning medicines', completed[0])
        self.assertIn('2/2', completed[0])
        self.assertEqual(outstanding, [])

    def test_partial_taken(self):
        meds = [
            {'medicine_name': 'Metformin', 'window_label': 'morning', 'status': 'taken'},
            {'medicine_name': 'Lantus', 'window_label': 'morning', 'status': 'upcoming'},
        ]
        completed, _ = _group_medications_for_brief(meds, mode='completed')
        self.assertEqual(len(completed), 1)
        self.assertIn('1/2 taken', completed[0])

    def test_none_taken(self):
        meds = [
            {'medicine_name': 'Metformin', 'window_label': 'morning', 'status': 'upcoming'},
        ]
        completed, _ = _group_medications_for_brief(meds, mode='completed')
        self.assertEqual(completed, [])

    def test_multiple_windows(self):
        meds = [
            {'medicine_name': 'Metformin', 'window_label': 'morning', 'status': 'taken'},
            {'medicine_name': 'Lantus', 'window_label': 'morning', 'status': 'taken'},
            {'medicine_name': 'Melatonin', 'window_label': 'nightly', 'status': 'taken'},
        ]
        completed, _ = _group_medications_for_brief(meds, mode='completed')
        self.assertEqual(len(completed), 2)
        names = ' '.join(completed)
        self.assertIn('Morning medicines', names)
        self.assertIn('Night medicines', names)

    def test_empty_input(self):
        completed, outstanding = _group_medications_for_brief([], mode='completed')
        self.assertEqual(completed, [])
        self.assertEqual(outstanding, [])


class TestMedicationBriefGroupingOutstanding(SimpleTestCase):
    """Test outstanding mode grouping."""

    def test_overdue_window(self):
        meds = [
            {'medicine_name': 'Metformin', 'window_label': 'morning', 'status': 'overdue'},
            {'medicine_name': 'Lantus', 'window_label': 'morning', 'status': 'overdue'},
        ]
        _, outstanding = _group_medications_for_brief(meds, mode='outstanding')
        self.assertEqual(len(outstanding), 1)
        self.assertIn('Morning medicines OVERDUE', outstanding[0])
        self.assertIn('2/2', outstanding[0])

    def test_not_started_window(self):
        meds = [
            {'medicine_name': 'Melatonin', 'window_label': 'nightly', 'status': 'upcoming'},
        ]
        _, outstanding = _group_medications_for_brief(meds, mode='outstanding')
        self.assertEqual(len(outstanding), 1)
        self.assertIn('Night medicines', outstanding[0])
        self.assertIn('not started', outstanding[0])

    def test_partial_window_not_outstanding(self):
        """If some meds are taken, window is not 'not started'."""
        meds = [
            {'medicine_name': 'Metformin', 'window_label': 'morning', 'status': 'taken'},
            {'medicine_name': 'Lantus', 'window_label': 'morning', 'status': 'upcoming'},
        ]
        _, outstanding = _group_medications_for_brief(meds, mode='outstanding')
        # Partial taken windows have taken_count > 0, so they don't match "not started"
        self.assertEqual(outstanding, [])

    def test_all_taken_not_outstanding(self):
        meds = [
            {'medicine_name': 'Metformin', 'window_label': 'morning', 'status': 'taken'},
        ]
        _, outstanding = _group_medications_for_brief(meds, mode='outstanding')
        self.assertEqual(outstanding, [])

    def test_missing_window_label(self):
        """Meds with empty window_label get grouped under 'other'."""
        meds = [
            {'medicine_name': 'Aspirin', 'window_label': '', 'status': 'overdue'},
        ]
        _, outstanding = _group_medications_for_brief(meds, mode='outstanding')
        self.assertEqual(len(outstanding), 1)
        self.assertIn('OVERDUE', outstanding[0])
