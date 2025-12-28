"""
Vision Service Tests - Tests for the OpenAI Vision integration.

Tests cover:
- Service availability
- Image analysis
- Response parsing
- Error handling
- Action building
"""

import json
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.scan.services.vision import VisionService, vision_service, ScanResult


class VisionServiceTests(TestCase):
    """Tests for the VisionService class."""

    def test_service_unavailable_without_api_key(self):
        """Test that service is unavailable without API key."""
        with override_settings(OPENAI_API_KEY=None):
            service = VisionService()
            self.assertFalse(service.is_available)

    @patch('apps.scan.services.vision.VisionService._initialize_client')
    def test_service_available_with_api_key(self, mock_init):
        """Test that service is available with API key."""
        with override_settings(OPENAI_API_KEY='test-key'):
            service = VisionService()
            service.client = MagicMock()  # Simulate successful init
            self.assertTrue(service.is_available)

    def test_error_result_on_unavailable_service(self):
        """Test that error result is returned when service is unavailable."""
        service = VisionService()
        service.client = None  # Force unavailable

        result = service.analyze_image(
            image_base64='test',
            request_id='test-id',
            image_format='jpeg'
        )

        self.assertIsInstance(result, ScanResult)
        self.assertEqual(result.top_category, 'unknown')
        self.assertIsNotNone(result.error)
        self.assertIn('not configured', result.error)

    @patch('openai.OpenAI')
    def test_analyze_image_success(self, mock_openai_class):
        """Test successful image analysis."""
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            'top_category': 'medicine',
            'confidence': 0.95,
            'items': [
                {
                    'label': 'Aspirin 325mg',
                    'details': {'dosage': '325mg'},
                    'confidence': 0.93
                }
            ],
            'safety_notes': ['Consult your doctor']
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        with override_settings(OPENAI_API_KEY='test-key'):
            service = VisionService()
            service.client = mock_client

            result = service.analyze_image(
                image_base64='dGVzdA==',  # base64 of 'test'
                request_id=str(uuid.uuid4()),
                image_format='jpeg'
            )

        self.assertIsInstance(result, ScanResult)
        self.assertEqual(result.top_category, 'medicine')
        self.assertEqual(result.confidence, 0.95)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0]['label'], 'Aspirin 325mg')
        self.assertIsNone(result.error)

    @patch('openai.OpenAI')
    def test_analyze_image_handles_missing_fields(self, mock_openai_class):
        """Test that missing fields in response are handled gracefully."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            # Missing top_category, confidence, items, safety_notes
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        with override_settings(OPENAI_API_KEY='test-key'):
            service = VisionService()
            service.client = mock_client

            result = service.analyze_image(
                image_base64='dGVzdA==',
                request_id=str(uuid.uuid4()),
                image_format='jpeg'
            )

        # Should have default values
        self.assertEqual(result.top_category, 'unknown')
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.items, [])
        self.assertEqual(result.safety_notes, [])

    @patch('openai.OpenAI')
    def test_analyze_image_handles_json_error(self, mock_openai_class):
        """Test that JSON parse errors are handled."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = 'Not valid JSON at all'

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        with override_settings(OPENAI_API_KEY='test-key'):
            service = VisionService()
            service.client = mock_client

            result = service.analyze_image(
                image_base64='dGVzdA==',
                request_id=str(uuid.uuid4()),
                image_format='jpeg'
            )

        self.assertEqual(result.top_category, 'unknown')
        self.assertIsNotNone(result.error)
        self.assertIn('parse', result.error.lower())

    @patch('openai.OpenAI')
    def test_analyze_image_handles_api_error(self, mock_openai_class):
        """Test that API errors are handled gracefully."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception('API Error')
        mock_openai_class.return_value = mock_client

        with override_settings(OPENAI_API_KEY='test-key'):
            service = VisionService()
            service.client = mock_client

            result = service.analyze_image(
                image_base64='dGVzdA==',
                request_id=str(uuid.uuid4()),
                image_format='jpeg'
            )

        self.assertEqual(result.top_category, 'unknown')
        self.assertIsNotNone(result.error)


class ActionBuildingTests(TestCase):
    """Tests for the action building logic."""

    def setUp(self):
        self.service = VisionService()

    def test_food_actions(self):
        """Test that food category generates correct actions."""
        items = [{'label': 'Grilled Chicken', 'details': {'estimated_calories': '300'}}]
        actions = self.service._build_actions('food', items)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['module'], 'Health.FoodLog')
        self.assertIn('log', actions[0]['question'].lower())
        self.assertTrue(len(actions[0]['actions']) >= 2)  # Log + Skip

    def test_medicine_actions(self):
        """Test that medicine category generates correct actions."""
        items = [{'label': 'Lisinopril 10mg', 'details': {'dosage': '10mg'}}]
        actions = self.service._build_actions('medicine', items)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['module'], 'Health.Medicine')
        self.assertIn('medicine', actions[0]['question'].lower())

    def test_supplement_actions(self):
        """Test that supplement category generates correct actions."""
        items = [{'label': 'Vitamin D3', 'details': {}}]
        actions = self.service._build_actions('supplement', items)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['module'], 'Health.Medicine')
        self.assertIn('supplement', actions[0]['question'].lower())

    def test_receipt_actions(self):
        """Test that receipt category generates correct actions."""
        items = [{'label': 'Grocery receipt', 'details': {'merchant': 'Walmart'}}]
        actions = self.service._build_actions('receipt', items)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['module'], 'Journal')

    def test_document_actions(self):
        """Test that document category generates correct actions."""
        items = [{'label': 'Lab Results', 'details': {}}]
        actions = self.service._build_actions('document', items)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['module'], 'Journal')

    def test_workout_equipment_actions(self):
        """Test that workout equipment category generates correct actions."""
        items = [{'label': 'Dumbbells', 'details': {}}]
        actions = self.service._build_actions('workout_equipment', items)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['module'], 'Health.Fitness')
        self.assertIn('workout', actions[0]['question'].lower())

    def test_unknown_actions(self):
        """Test that unknown category generates retry options."""
        items = []
        actions = self.service._build_actions('unknown', items)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['module'], 'Unknown')
        self.assertIn("couldn't identify", actions[0]['question'].lower())

        # Should have retry, add note, and skip
        action_ids = [a['id'] for a in actions[0]['actions']]
        self.assertIn('retry', action_ids)
        self.assertIn('skip', action_ids)

    def test_empty_items_handled(self):
        """Test that empty items list is handled."""
        actions = self.service._build_actions('food', [])

        self.assertEqual(len(actions), 1)
        # Should still work with generic label
        self.assertIn('meal', actions[0]['question'].lower())


class ScanResultTests(TestCase):
    """Tests for the ScanResult class."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = ScanResult(
            request_id='test-123',
            top_category='food',
            confidence=0.9,
            items=[{'label': 'Pizza', 'details': {}, 'confidence': 0.88}],
            safety_notes=['Be careful'],
            next_best_actions=[{
                'module': 'Health.FoodLog',
                'question': 'Log this?',
                'actions': []
            }]
        )

        d = result.to_dict()

        self.assertEqual(d['request_id'], 'test-123')
        self.assertEqual(d['top_category'], 'food')
        self.assertEqual(d['confidence'], 0.9)
        self.assertEqual(len(d['items']), 1)
        self.assertEqual(d['safety_notes'], ['Be careful'])
        self.assertEqual(len(d['next_best_actions']), 1)
        self.assertIsNone(d['error'])

    def test_to_dict_with_error(self):
        """Test conversion to dictionary with error."""
        result = ScanResult(
            request_id='test-123',
            top_category='unknown',
            confidence=0.0,
            items=[],
            safety_notes=[],
            next_best_actions=[],
            error='Something went wrong'
        )

        d = result.to_dict()

        self.assertEqual(d['error'], 'Something went wrong')
