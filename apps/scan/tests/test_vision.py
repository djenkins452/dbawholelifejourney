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
        self.assertEqual(actions[0]['module'], 'Life.Documents')
        # Should offer Save to Documents, Add to Journal, and Skip
        self.assertEqual(len(actions[0]['actions']), 3)

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

    def test_inventory_item_actions(self):
        """Test that inventory_item category generates correct actions."""
        items = [{'label': 'DeWalt Drill', 'details': {'category': 'Tools', 'brand': 'DeWalt'}}]
        actions = self.service._build_actions('inventory_item', items)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['module'], 'Life.Inventory')
        self.assertIn('inventory', actions[0]['question'].lower())
        # Should have add_inventory and skip
        action_ids = [a['id'] for a in actions[0]['actions']]
        self.assertIn('add_inventory', action_ids)
        self.assertIn('skip', action_ids)
        # URL should include name and category
        add_action = [a for a in actions[0]['actions'] if a['id'] == 'add_inventory'][0]
        self.assertIn('name=DeWalt', add_action['url'])
        self.assertIn('category=Tools', add_action['url'])

    def test_recipe_actions(self):
        """Test that recipe category generates correct actions."""
        items = [{'label': 'Chocolate Chip Cookies', 'details': {'cuisine': 'American', 'course': 'dessert'}}]
        actions = self.service._build_actions('recipe', items)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['module'], 'Life.Recipes')
        self.assertIn('recipe', actions[0]['question'].lower())
        # Should have save_recipe and skip
        action_ids = [a['id'] for a in actions[0]['actions']]
        self.assertIn('save_recipe', action_ids)
        self.assertIn('skip', action_ids)

    def test_pet_actions(self):
        """Test that pet category generates correct actions."""
        items = [{'label': 'Golden Retriever', 'details': {'species': 'dog', 'breed': 'Golden Retriever'}}]
        actions = self.service._build_actions('pet', items)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['module'], 'Life.Pets')
        self.assertIn('pet', actions[0]['question'].lower())
        # Should have add_pet, add_journal, and skip
        action_ids = [a['id'] for a in actions[0]['actions']]
        self.assertIn('add_pet', action_ids)
        self.assertIn('add_journal', action_ids)
        self.assertIn('skip', action_ids)

    def test_maintenance_actions(self):
        """Test that maintenance category generates correct actions."""
        items = [{'label': 'HVAC Filter', 'details': {}}]
        actions = self.service._build_actions('maintenance', items)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['module'], 'Life.Maintenance')
        self.assertIn('maintenance', actions[0]['question'].lower())
        # Should have add_maintenance, add_inventory, and skip
        action_ids = [a['id'] for a in actions[0]['actions']]
        self.assertIn('add_maintenance', action_ids)
        self.assertIn('add_inventory', action_ids)
        self.assertIn('skip', action_ids)

    def test_workout_equipment_includes_inventory_option(self):
        """Test that workout equipment also offers Add to Inventory."""
        items = [{'label': 'Dumbbells', 'details': {}}]
        actions = self.service._build_actions('workout_equipment', items)

        # Should have log_workout, add_inventory, and skip
        action_ids = [a['id'] for a in actions[0]['actions']]
        self.assertIn('log_workout', action_ids)
        self.assertIn('add_inventory', action_ids)
        self.assertIn('skip', action_ids)

    def test_unknown_includes_inventory_option(self):
        """Test that unknown category offers Add to Inventory option."""
        items = []
        actions = self.service._build_actions('unknown', items)

        # Should have retry, add_inventory, add_note, and skip
        action_ids = [a['id'] for a in actions[0]['actions']]
        self.assertIn('retry', action_ids)
        self.assertIn('add_inventory', action_ids)
        self.assertIn('add_note', action_ids)
        self.assertIn('skip', action_ids)


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


class SourceParamTrackingTests(TestCase):
    """Tests for source=ai_camera parameter in action URLs."""

    def setUp(self):
        self.service = VisionService()

    def test_add_source_param_to_url_without_params(self):
        """Test adding source param to URL without existing params."""
        url = '/journal/entry/create/'
        result = self.service._add_source_param(url)
        self.assertEqual(result, '/journal/entry/create/?source=ai_camera')

    def test_add_source_param_to_url_with_params(self):
        """Test adding source param to URL with existing params."""
        url = '/journal/entry/create/?prefill_title=Test'
        result = self.service._add_source_param(url)
        self.assertEqual(result, '/journal/entry/create/?prefill_title=Test&source=ai_camera')

    def test_food_actions_include_source_param(self):
        """Test that food actions include source=ai_camera in URL."""
        items = [{'label': 'Grilled Chicken', 'details': {'estimated_calories': '300'}}]
        actions = self.service._build_actions('food', items)

        action_url = actions[0]['actions'][0]['url']
        self.assertIn('source=ai_camera', action_url)

    def test_medicine_actions_include_source_param(self):
        """Test that medicine actions include source=ai_camera in URL."""
        items = [{'label': 'Aspirin 325mg', 'details': {'dosage': '325mg'}}]
        actions = self.service._build_actions('medicine', items)

        action_url = actions[0]['actions'][0]['url']
        self.assertIn('source=ai_camera', action_url)

    def test_supplement_actions_include_source_param(self):
        """Test that supplement actions include source=ai_camera in URL."""
        items = [{'label': 'Vitamin D3', 'details': {}}]
        actions = self.service._build_actions('supplement', items)

        action_url = actions[0]['actions'][0]['url']
        self.assertIn('source=ai_camera', action_url)

    def test_receipt_actions_include_source_param(self):
        """Test that receipt actions include source=ai_camera in URL."""
        items = [{'label': 'Receipt', 'details': {'merchant': 'Walmart'}}]
        actions = self.service._build_actions('receipt', items)

        action_url = actions[0]['actions'][0]['url']
        self.assertIn('source=ai_camera', action_url)

    def test_document_actions_include_source_param(self):
        """Test that document actions include source=ai_camera in URL."""
        items = [{'label': 'Lab Results', 'details': {}}]
        actions = self.service._build_actions('document', items)

        action_url = actions[0]['actions'][0]['url']
        self.assertIn('source=ai_camera', action_url)

    def test_workout_actions_include_source_param(self):
        """Test that workout actions include source=ai_camera in URL."""
        items = [{'label': 'Dumbbells', 'details': {}}]
        actions = self.service._build_actions('workout_equipment', items)

        action_url = actions[0]['actions'][0]['url']
        self.assertIn('source=ai_camera', action_url)

    def test_unknown_add_note_action_includes_source_param(self):
        """Test that unknown category 'Add as Journal Note' includes source=ai_camera."""
        items = []
        actions = self.service._build_actions('unknown', items)

        # Find the 'add_note' action
        add_note_action = None
        for action in actions[0]['actions']:
            if action['id'] == 'add_note':
                add_note_action = action
                break

        self.assertIsNotNone(add_note_action)
        self.assertIn('source=ai_camera', add_note_action['url'])

    def test_skip_action_has_no_url(self):
        """Test that skip action has empty URL (no source param needed)."""
        items = [{'label': 'Test', 'details': {}}]
        actions = self.service._build_actions('food', items)

        skip_action = None
        for action in actions[0]['actions']:
            if action['id'] == 'skip':
                skip_action = action
                break

        self.assertIsNotNone(skip_action)
        self.assertEqual(skip_action['url'], '')
