# ==============================================================================
# File: intent_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Intent recognition and structured data extraction using OpenAI
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-04
# ==============================================================================
"""
Intent Recognition Service

Uses OpenAI's function calling (tools) feature to recognize user intent
and extract structured data from natural language input.

Example:
    User: "my heart rate is 60"
    Intent: log_heart_rate
    Parameters: {"bpm": 60, "context": "resting"}
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .intents import ALL_INTENT_TOOLS, INTENT_HANDLERS
from .intents.health_intents import HEALTH_VALIDATION_RANGES

logger = logging.getLogger(__name__)


@dataclass
class IntentResult:
    """Result of intent recognition."""
    intent_type: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    requires_confirmation: bool = False
    confirmation_message: str = ""
    raw_response: Optional[str] = None


@dataclass
class ActionResult:
    """Result of executing an intent action."""
    success: bool
    message: str
    created_object: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    action_type: Optional[str] = None


class IntentService:
    """
    Recognizes user intent and extracts structured data using OpenAI function calling.

    The service:
    1. Sends user message to OpenAI with function tool definitions
    2. Parses the function call response to extract intent and parameters
    3. Validates extracted parameters against known ranges
    4. Returns structured IntentResult for action execution

    Usage:
        intent_service = IntentService()
        result = intent_service.recognize_intent("my heart rate is 60", user)
        if result.intent_type != 'no_action':
            action_result = intent_service.execute_intent(result, user)
    """

    def __init__(self):
        self.client = None
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        self._initialize_client()

    def _initialize_client(self):
        """Initialize OpenAI client if API key is available."""
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key)
            except ImportError:
                logger.warning("OpenAI package not installed")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")

    @property
    def is_available(self) -> bool:
        """Check if intent service is available."""
        return self.client is not None

    def recognize_intent(self, user_message: str, user) -> IntentResult:
        """
        Recognize user intent from natural language message.

        Args:
            user_message: The user's natural language input
            user: The User model instance

        Returns:
            IntentResult with intent_type, parameters, and confirmation needs
        """
        if not self.is_available:
            logger.warning("Intent service not available - returning no_action")
            return IntentResult(intent_type='no_action')

        try:
            # Build the system prompt for intent recognition
            system_prompt = self._build_intent_system_prompt()

            # Call OpenAI with function tools
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                tools=ALL_INTENT_TOOLS,
                tool_choice="auto",
                max_tokens=200,
                temperature=0.1,  # Low temperature for consistent parsing
            )

            # Parse the response
            message = response.choices[0].message

            # Check if a function was called
            if message.tool_calls:
                tool_call = message.tool_calls[0]
                function_name = tool_call.function.name
                try:
                    parameters = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    parameters = {}

                logger.info(f"Intent recognized: {function_name} with params: {parameters}")

                # Check if confirmation is needed based on validation
                requires_confirmation, confirmation_message = self._check_validation(
                    function_name, parameters, user
                )

                return IntentResult(
                    intent_type=function_name,
                    parameters=parameters,
                    confidence=1.0,
                    requires_confirmation=requires_confirmation,
                    confirmation_message=confirmation_message,
                    raw_response=message.content
                )
            else:
                # No function called - regular chat message
                return IntentResult(
                    intent_type='no_action',
                    raw_response=message.content
                )

        except Exception as e:
            logger.error(f"Intent recognition error: {e}", exc_info=True)
            return IntentResult(intent_type='no_action')

    def _build_intent_system_prompt(self) -> str:
        """Build the system prompt for intent recognition."""
        return """You are an intent recognition system for a personal wellness app called "Whole Life Journey".

Your job is to identify when the user wants to log health data or perform an action, and extract the relevant parameters.

IMPORTANT RULES:
1. Only call a function if the user clearly intends to log data or perform an action
2. For heart rate: Extract BPM value. Default context to 'resting' unless user specifies otherwise
3. For blood pressure: Extract systolic (top) and diastolic (bottom) numbers
4. For weight: Extract value and unit (default 'lb' if not specified)
5. For glucose: Extract value and unit (default 'mg/dL' if not specified)
6. For blood oxygen: Extract SpO2 percentage value
7. For food: Extract food name and quantity (default 1)
8. For medicine: Extract medicine name and optional dose label
9. For fasting: Determine start or end intent, and fasting type if starting

If the user's message is conversational and doesn't indicate logging intent, do NOT call any function.
Let the message pass through for normal chat handling.

Examples of messages that SHOULD trigger functions:
- "my heart rate is 60" → log_heart_rate(bpm=60, context="resting")
- "BP is 120/80" → log_blood_pressure(systolic=120, diastolic=80)
- "I weigh 175" → log_weight(value=175, unit="lb")
- "blood sugar is 105" → log_glucose(value=105, unit="mg/dL")
- "oxygen is 98%" → log_blood_oxygen(spo2=98)
- "I ate a banana" → log_food(food_name="banana", quantity=1)
- "took my metformin" → take_medicine(medicine_name="metformin")
- "starting a fast" → start_fast(fasting_type="16:8")
- "ending my fast" → end_fast()

Examples of messages that should NOT trigger functions:
- "how are you?"
- "what's my heart rate history?"
- "tell me about fasting"
- "should I take my medicine?"
"""

    def _check_validation(self, intent_type: str, parameters: dict, user) -> tuple:
        """
        Check if extracted values need user confirmation.

        Returns (requires_confirmation, confirmation_message) tuple.
        """
        # Check user preference for confirmation
        prefs = user.preferences
        always_confirm = getattr(prefs, 'assistant_confirm_actions', False)

        if always_confirm:
            confirmation_message = self._build_confirmation_message(intent_type, parameters)
            return True, confirmation_message

        # Check for unusual values that warrant questioning
        if intent_type == 'log_heart_rate':
            bpm = parameters.get('bpm', 0)
            ranges = HEALTH_VALIDATION_RANGES['heart_rate']
            if bpm < ranges['normal_min'] or bpm > ranges['normal_max']:
                status = "quite low" if bpm < ranges['normal_min'] else "quite high"
                context_q = "Were you exercising?" if bpm > ranges['normal_max'] else "Were you resting?"
                msg = f"{bpm} BPM is {status}. {context_q} Should I log it?"
                return True, msg

        elif intent_type == 'log_blood_pressure':
            systolic = parameters.get('systolic', 0)
            diastolic = parameters.get('diastolic', 0)
            ranges = HEALTH_VALIDATION_RANGES['blood_pressure']
            if (systolic < ranges['systolic_min'] or systolic > ranges['systolic_max'] or
                    diastolic < ranges['diastolic_min'] or diastolic > ranges['diastolic_max']):
                status = "outside normal range"
                msg = f"{systolic}/{diastolic} is {status}. Should I log it?"
                return True, msg

        elif intent_type == 'log_weight':
            value = parameters.get('value', 0)
            ranges = HEALTH_VALIDATION_RANGES['weight']
            if value < ranges['normal_min'] or value > ranges['normal_max']:
                status = "unusual"
                unit = parameters.get('unit', 'lb')
                msg = f"{value} {unit} seems {status}. Is this correct?"
                return True, msg

        elif intent_type == 'log_glucose':
            value = parameters.get('value', 0)
            ranges = HEALTH_VALIDATION_RANGES['glucose']
            if value < ranges['normal_min'] or value > ranges['normal_max']:
                status = "low" if value < ranges['normal_min'] else "high"
                unit = parameters.get('unit', 'mg/dL')
                context_q = "How are you feeling?" if value < ranges['normal_min'] else "Is this after eating?"
                msg = f"{value} {unit} is {status}. {context_q} Should I log it?"
                return True, msg

        elif intent_type == 'log_blood_oxygen':
            spo2 = parameters.get('spo2', 0)
            ranges = HEALTH_VALIDATION_RANGES['blood_oxygen']
            if spo2 < ranges['normal_min']:
                status = "low"
                msg = f"{spo2}% SpO2 is {status}. Are you feeling okay? Should I log it?"
                return True, msg

        return False, ""

    def _build_confirmation_message(self, intent_type: str, parameters: dict) -> str:
        """Build a confirmation message for an action."""
        if intent_type == 'log_heart_rate':
            bpm = parameters.get('bpm', 0)
            context = parameters.get('context', 'resting')
            return f"I'll log your heart rate as {bpm} BPM ({context}). Confirm?"

        elif intent_type == 'log_blood_pressure':
            systolic = parameters.get('systolic', 0)
            diastolic = parameters.get('diastolic', 0)
            return f"I'll log your blood pressure as {systolic}/{diastolic}. Confirm?"

        elif intent_type == 'log_weight':
            value = parameters.get('value', 0)
            unit = parameters.get('unit', 'lb')
            return f"I'll log your weight as {value} {unit}. Confirm?"

        elif intent_type == 'log_glucose':
            value = parameters.get('value', 0)
            unit = parameters.get('unit', 'mg/dL')
            return f"I'll log your blood glucose as {value} {unit}. Confirm?"

        elif intent_type == 'log_blood_oxygen':
            spo2 = parameters.get('spo2', 0)
            return f"I'll log your blood oxygen as {spo2}%. Confirm?"

        elif intent_type == 'log_food':
            food = parameters.get('food_name', 'food')
            quantity = parameters.get('quantity', 1)
            return f"I'll log {quantity} serving(s) of {food}. Confirm?"

        elif intent_type == 'take_medicine':
            medicine = parameters.get('medicine_name', 'medicine')
            return f"I'll log that you took {medicine}. Confirm?"

        elif intent_type == 'start_fast':
            fasting_type = parameters.get('fasting_type', '16:8')
            return f"I'll start a {fasting_type} fast for you. Confirm?"

        elif intent_type == 'end_fast':
            return "I'll end your current fast. Confirm?"

        return "Confirm this action?"

    def execute_intent(self, intent_result: IntentResult, user) -> ActionResult:
        """
        Execute a recognized intent by calling the appropriate action handler.

        Args:
            intent_result: The IntentResult from recognize_intent()
            user: The User model instance

        Returns:
            ActionResult with success status and details
        """
        from .action_handlers import ActionHandler

        handler = ActionHandler(user)
        intent_type = intent_result.intent_type
        parameters = intent_result.parameters

        try:
            if intent_type == 'log_heart_rate':
                return handler.handle_log_heart_rate(**parameters)

            elif intent_type == 'log_blood_pressure':
                return handler.handle_log_blood_pressure(**parameters)

            elif intent_type == 'log_weight':
                return handler.handle_log_weight(**parameters)

            elif intent_type == 'log_glucose':
                return handler.handle_log_glucose(**parameters)

            elif intent_type == 'log_blood_oxygen':
                return handler.handle_log_blood_oxygen(**parameters)

            elif intent_type == 'log_food':
                return handler.handle_log_food(**parameters)

            elif intent_type == 'take_medicine':
                return handler.handle_take_medicine(**parameters)

            elif intent_type == 'start_fast':
                return handler.handle_start_fast(**parameters)

            elif intent_type == 'end_fast':
                return handler.handle_end_fast(**parameters)

            else:
                return ActionResult(
                    success=False,
                    message="Unknown intent type",
                    error=f"No handler for intent: {intent_type}"
                )

        except Exception as e:
            logger.error(f"Action execution error for {intent_type}: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't complete that action.",
                error=str(e)
            )

    def store_pending_confirmation(self, user, intent_result: IntentResult, ttl: int = 300):
        """
        Store a pending confirmation in cache.

        Args:
            user: The User model instance
            intent_result: The IntentResult waiting for confirmation
            ttl: Time to live in seconds (default 5 minutes)
        """
        cache_key = f"pending_intent_{user.id}"
        cache.set(cache_key, {
            'intent_type': intent_result.intent_type,
            'parameters': intent_result.parameters,
            'timestamp': timezone.now().isoformat()
        }, ttl)

    def get_pending_confirmation(self, user) -> Optional[Dict]:
        """
        Retrieve a pending confirmation from cache.

        Args:
            user: The User model instance

        Returns:
            Dict with intent_type and parameters, or None
        """
        cache_key = f"pending_intent_{user.id}"
        return cache.get(cache_key)

    def clear_pending_confirmation(self, user):
        """Clear any pending confirmation for a user."""
        cache_key = f"pending_intent_{user.id}"
        cache.delete(cache_key)

    def handle_confirmation_response(self, user, response: str) -> Optional[ActionResult]:
        """
        Handle user's response to a confirmation request.

        Args:
            user: The User model instance
            response: User's response (yes/no/confirm/cancel etc.)

        Returns:
            ActionResult if confirmed and executed, None if declined or no pending
        """
        pending = self.get_pending_confirmation(user)
        if not pending:
            return None

        # Check for affirmative response
        response_lower = response.lower().strip()
        affirmative_responses = {'yes', 'y', 'confirm', 'ok', 'sure', 'do it', 'log it', 'go ahead'}
        negative_responses = {'no', 'n', 'cancel', 'nevermind', 'stop', 'dont', "don't"}

        if response_lower in affirmative_responses:
            # Execute the pending intent
            intent_result = IntentResult(
                intent_type=pending['intent_type'],
                parameters=pending['parameters']
            )
            self.clear_pending_confirmation(user)
            return self.execute_intent(intent_result, user)

        elif response_lower in negative_responses:
            self.clear_pending_confirmation(user)
            return ActionResult(
                success=True,
                message="Okay, I won't log that.",
                action_type='cancelled'
            )

        # Response not recognized - keep pending
        return None


# Singleton instance
intent_service = IntentService()
