# ==============================================================================
# File: intent_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Intent recognition and structured data extraction using OpenAI
# Owner: Danny Jenkins (admin@wholelifejourney.com)
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
    confirmation_detail: Optional[Dict[str, Any]] = None


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
        self.model = getattr(settings, 'OPENAI_INTENT_MODEL', settings.OPENAI_MODEL)
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

    def recognize_intent(self, user_message: str, user, conversation_history: list = None,
                         page_context: dict = None) -> IntentResult:
        """
        Recognize user intent from natural language message.

        Args:
            user_message: The user's natural language input
            user: The User model instance
            conversation_history: Optional list of recent message dicts for context resolution.
            page_context: Optional dict with url, module, page_title, help_context_id
                          for UI context grounding (domain preference).

        Returns:
            IntentResult with intent_type, parameters, and confirmation needs
            Note: For single intents. Use recognize_intents() for multiple.
        """
        results = self.recognize_intents(
            user_message, user, conversation_history=conversation_history,
            page_context=page_context,
        )
        return results[0] if results else IntentResult(intent_type='no_action')

    # ── Correction detection ──────────────────────────────────────
    # Phrases indicating the user is CORRECTING or CHALLENGING CoS's
    # information — not requesting an action.  If any of these match,
    # intent recognition returns no_action immediately so the message
    # goes to the conversational LLM (which can look up real data).
    #
    # Root cause: "You won't find them for today any longer" was
    # misinterpreted as mutate_task(action='delete') by OpenAI, blocked
    # by the safety engine, and the canned response suggested deletion
    # — the exact opposite of what the user wanted.
    _CORRECTION_PATTERNS = [
        # Challenging accuracy
        'you better check', 'better double check', 'double check that',
        'check again', 'look again', 'try again',
        "that's wrong", "that's not right", "that's incorrect",
        "that's not correct", "that is wrong", "that is not right",
        "you're wrong", "you are wrong",
        "no that's wrong", "no that's not",
        # Stating something can't be found / doesn't exist
        "you won't find", "won't find them", "won't find it",
        "can't find them", "can't find it",
        "don't see them", "don't see it",
        "shouldn't be there", "shouldn't be on",
        "not for today", "not due today", "not on my list",
        "no longer due", "no longer on",
        # Asking where info came from
        "where are you getting", "where did you get",
        "where are you finding", "where did you find",
        "where is that coming from", "where did that come from",
        # Correcting a previous statement
        "I didn't say", "I never said", "I didn't ask",
        "I never asked", "I didn't mean",
        # Telling CoS she's wrong about data
        "not anymore", "not any more",
        "any longer",  # "won't find them for today any longer"
    ]

    def _is_correction_message(self, user_message: str) -> bool:
        """Return True if the message is a user correction, not an action request."""
        msg_lower = user_message.lower()
        return any(pattern in msg_lower for pattern in self._CORRECTION_PATTERNS)

    def recognize_intents(self, user_message: str, user, conversation_history: list = None,
                          page_context: dict = None, domain: str = None) -> List[IntentResult]:
        """
        Recognize one or more user intents from natural language message.

        Supports multi-command messages like "update my oxygen to 95 and my weight to 350"
        which will return multiple IntentResults.

        Args:
            user_message: The user's natural language input
            user: The User model instance
            conversation_history: Optional list of recent message dicts
                [{"role": "user"|"assistant", "content": "..."}] for resolving
                anaphoric references ("the other one", "that event", "it").
            page_context: Optional dict with url, module, page_title, help_context_id
                          for UI context grounding (domain preference).
            domain: Optional router-inferred domain for scoped tool loading.
                    When set, only domain-relevant tools are sent (~2-6K tokens
                    instead of ~19K). None sends all tools.

        Returns:
            List of IntentResult objects (may be empty if no intents recognized)
        """
        if not self.is_available:
            logger.warning("Intent service not available - returning empty list")
            return [IntentResult(intent_type='no_action')]

        # ── Correction filter: skip intent recognition entirely ──
        # When the user is correcting or challenging CoS's information
        # (e.g. "You won't find them for today any longer"), send to the
        # conversational LLM — never interpret as an action request.
        if self._is_correction_message(user_message):
            logger.info(
                "[INTENT_CORRECTION_FILTER] Skipping intent recognition — "
                "user is correcting info: %r",
                user_message[:100],
            )
            return [IntentResult(intent_type='no_action')]

        try:
            # Build the system prompt for intent recognition
            # Pass user so today's date is computed in user's local timezone,
            # not server UTC (scheduling reliability contract — Part 1).
            system_prompt = self._build_intent_system_prompt(user=user, page_context=page_context)

            # Build message array with optional conversation history for
            # anaphora resolution ("the other one", "that event", "it").
            _messages = [{"role": "system", "content": system_prompt}]
            if conversation_history:
                _messages.extend(conversation_history)
            _messages.append({"role": "user", "content": user_message})

            # Call OpenAI with function tools - parallel_tool_calls enabled by default
            # Phase 5: Load only domain-relevant tools to reduce ~19K → ~2-6K tokens
            from apps.ai.intents import get_scoped_intent_tools
            _tools = get_scoped_intent_tools(domain)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=_messages,
                tools=_tools,
                tool_choice="auto",
                max_tokens=500,  # Increased for multiple tool calls
                temperature=0.1,  # Low temperature for consistent parsing
            )

            # --- Owner Finance telemetry (best-effort) ---
            try:
                usage = getattr(response, 'usage', None)
                if usage:
                    from apps.owner_finance.services.telemetry import log_llm_usage
                    log_llm_usage(
                        user=user,
                        feature='INTENT',
                        model_name=self.model,
                        input_tokens=getattr(usage, 'prompt_tokens', 0),
                        output_tokens=getattr(usage, 'completion_tokens', 0),
                    )
            except Exception:
                pass  # telemetry must never break intent recognition

            # Parse the response
            message = response.choices[0].message

            # Check if any functions were called
            if message.tool_calls:
                results = []
                for tool_call in message.tool_calls:
                    function_name = tool_call.function.name
                    try:
                        parameters = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        logger.warning(
                            "Failed to parse tool call args for %s: %s",
                            function_name, tool_call.function.arguments,
                        )
                        continue  # Skip malformed tool call

                    # --- Mutation verb enforcement ---
                    # If the LLM selected read_calendar_events but the user's
                    # message contains a mutation verb, reroute to
                    # mutate_calendar_event with event_query.
                    if function_name == 'read_calendar_events':
                        rerouted = self._enforce_mutation_routing(
                            user_message, parameters,
                        )
                        if rerouted is not None:
                            function_name = rerouted['intent_type']
                            parameters = rerouted['parameters']
                            logger.info(
                                "Mutation verb enforcement: rerouted "
                                "read_calendar_events → %s params=%s",
                                function_name, parameters,
                            )

                    # --- Domain-lock safeguard ---
                    # Prevent cross-domain misrouting: if the router
                    # detected a specific domain AND the LLM selected an
                    # intent from a different domain, reject the intent.
                    # This stops "move workout" from triggering "rename
                    # assistant" (set_cos_name) when the domain is 'tasks'.
                    if domain and function_name in INTENT_HANDLERS:
                        intent_domain = INTENT_HANDLERS.get(function_name)
                        if intent_domain and intent_domain != domain:
                            # Cross-domain: only allow if it's a system
                            # intent (undo/edit) or calibration intent
                            # (these are legitimately cross-cutting).
                            _cross_cutting = {
                                'system', 'calibration', 'learning_mode',
                            }
                            if intent_domain not in _cross_cutting:
                                logger.warning(
                                    "DOMAIN_LOCK_REJECT intent=%s "
                                    "intent_domain=%s router_domain=%s "
                                    "msg=%r — cross-domain mismatch, "
                                    "rejecting intent",
                                    function_name, intent_domain, domain,
                                    user_message[:80],
                                )
                                continue  # Skip this misrouted intent

                    # --- Keyword safeguard for set_cos_name ---
                    # Require explicit name-change language in the user's
                    # message before allowing assistant rename. This
                    # prevents any residual misclassification.
                    if function_name == 'set_cos_name':
                        _name_verbs = {
                            'call yourself', 'your name', 'rename',
                            'change your name', 'name is now',
                            'call you', 'named',
                        }
                        _msg_lower = (user_message or '').lower()
                        if not any(v in _msg_lower for v in _name_verbs):
                            logger.warning(
                                "SET_COS_NAME_REJECTED msg=%r — no "
                                "name-change language detected",
                                user_message[:80],
                            )
                            continue  # Reject: not a rename request

                    logger.info(f"Intent recognized: {function_name} with params: {parameters}")

                    # Check if confirmation is needed based on validation
                    requires_confirmation, confirmation_message = self._check_validation(
                        function_name, parameters, user
                    )

                    results.append(IntentResult(
                        intent_type=function_name,
                        parameters=parameters,
                        confidence=1.0,
                        requires_confirmation=requires_confirmation,
                        confirmation_message=confirmation_message,
                        raw_response=message.content
                    ))

                return results
            else:
                # No function called — check for action verb + domain
                # keyword before giving up.  This is the deterministic
                # backstop: if the user clearly wants to create, mutate,
                # or complete something and the domain is resolvable
                # (from the message or conversation history), we retry
                # with forced function calling.
                detection = self._detect_mutation_domain(
                    user_message, conversation_history,
                )
                if detection:
                    forced_fn, verb, keyword = detection
                    logger.info(
                        "[INTENT_RETRY] no_action but verb=%r "
                        "keyword=%r → forcing %s",
                        verb, keyword, forced_fn,
                    )
                    retry_results = self._retry_with_forced_mutation(
                        _messages, forced_fn, user, user_message,
                    )
                    if retry_results:
                        logger.info(
                            "[INTENT_RETRY] Retry succeeded: %s",
                            [r.intent_type for r in retry_results],
                        )
                        return retry_results
                    logger.warning(
                        "[INTENT_RETRY] Retry returned no results "
                        "for forced %s",
                        forced_fn,
                    )

                return [IntentResult(
                    intent_type='no_action',
                    raw_response=message.content
                )]

        except Exception as e:
            logger.error(f"Intent recognition error: {e}", exc_info=True)
            return [IntentResult(intent_type='no_action')]

    def _build_intent_system_prompt(self, user=None, page_context: dict = None) -> str:
        """Build the system prompt for intent recognition.

        Args:
            user: Optional User instance. When provided, today's date is
                  computed in the user's local timezone (via
                  get_current_local_datetime) instead of server UTC.
                  This is REQUIRED for correct relative-date resolution.
            page_context: Optional dict with url, module, page_title,
                          help_context_id for UI context grounding.
        """
        if user is not None:
            from apps.core.utils import get_current_local_datetime
            user_now = get_current_local_datetime(user)
            today = user_now.date()
            logger.debug(
                "Intent prompt: using user-local date %s (tz=%s)",
                today.isoformat(), user_now.tzinfo,
            )
        else:
            today = timezone.now().date()
            logger.warning(
                "Intent prompt: no user supplied — falling back to UTC date %s. "
                "This may cause incorrect relative-date resolution.",
                today.isoformat(),
            )
        today_str = today.strftime('%Y-%m-%d')
        weekday = today.strftime('%A')

        prompt = f"""You are an intent recognition system for a personal life management platform called "Whole Life Journey".

TODAY'S DATE: {today_str} ({weekday})

Your job is to identify when the user wants to perform an action (log data, create entries, save items), and extract the relevant parameters.

IMPORTANT RULES:
1. Only call a function if the user clearly intends to perform an action
2. Call the appropriate function based on the user's intent - not just health actions
3. When the user says "today", use {today_str}. When they say "tomorrow", calculate the next day from {today_str}
4. ALWAYS resolve relative dates (today, tomorrow, next Monday, etc.) to YYYY-MM-DD format using today's date above
5. CONTEXT RESOLUTION: When conversation history is provided, use it to resolve references like "the other one", "that event", "it", "those", "the duplicate", etc. Extract the actual entity name/details for function parameters — do NOT pass pronouns like "it" as event_query or task_query. If a previous message mentions specific events, tasks, or items, use that context to determine which entity the user is referring to and construct the appropriate function call.
6. ACTION OBLIGATION: When action verbs are present AND the domain context is clear (calendar event or task — either from the current message or conversation history), you MUST call the appropriate function. This covers: (a) CREATION verbs (add, create, make, schedule, remind, book, plan) → call create_task or create_event, (b) MUTATION verbs (remove, delete, cancel, move, change, reschedule, update, rename, edit) → call mutate_calendar_event or mutate_task, (c) COMPLETION verbs (complete, finish, done, mark done) → call complete_task. Never decline an action request when a resolvable domain is identified. If unsure which specific item, use your best inference from context.

HEALTH LOGGING:
- Heart rate: Extract BPM value. Default context to 'resting' unless specified
- Blood pressure: Extract systolic (top) and diastolic (bottom) numbers
- Weight: Extract value and unit (default 'lb' if not specified)
- Glucose: Extract value and unit (default 'mg/dL' if not specified)
- Blood oxygen: Extract SpO2 percentage value
- Food: Extract food name and quantity (default 1)
- Medication: Extract medication name and optional dose label
- Email intake list: Extract recipient email address; default to user's own email if not specified
- Fasting: Determine start or end intent, and fasting type if starting

FAITH ACTIONS:
- Save verse: When user wants to save, bookmark, or remember a Bible verse
- Log prayer: When user wants to add a prayer request
- Mark prayer answered: When user says a prayer was answered
- Add faith milestone: When user shares a meaningful spiritual moment

JOURNAL ACTIONS:
- Create journal entry: When user wants to write or log a journal entry
- Add gratitude: When user wants to log something they're grateful for

PURPOSE ACTIONS:
- Create goal: When user wants to set a new goal or aspiration
- Update goal progress: When user reports progress on an existing goal
- Set intention: When user expresses who they want to become or a way of being
- Log habit: When user says they completed a daily habit or practice

LIFE/TASK ACTIONS:
- Create task: When user wants to add a task or to-do item
- Complete task: When user marks a task as done
- Create event: When user wants to schedule something on their calendar
- Add reminder: When user wants to remember an important date (birthday, anniversary)

FITNESS ACTIONS:
- Log workout: When user says they finished a workout, gym session, or lists exercises they did
- Log exercise set: When user gives specific set/rep/weight data for an exercise
- Log cardio: When user mentions completing a run, walk, bike ride, swim, or other cardio

MULTI-COMMAND SUPPORT:
When the user mentions MULTIPLE actions in one message, call ALL relevant functions.
Do NOT only process the first action - process ALL actions mentioned.

If the user's message is purely conversational, do NOT call any function.

Examples of messages that SHOULD trigger functions:

HEALTH:
- "my heart rate is 60" → log_heart_rate(bpm=60, context="resting")
- "BP is 120/80" → log_blood_pressure(systolic=120, diastolic=80)
- "I weigh 175" → log_weight(value=175, unit="lb")
- "blood sugar is 105" → log_glucose(value=105, unit="mg/dL")
- "oxygen is 98%" → log_blood_oxygen(spo2=98)
- "I ate a banana" → log_food(food_name="banana", quantity=1)
- "I had eggs and toast for breakfast" → log_food(food_name="eggs and toast", quantity=1, meal_type="breakfast")
- "took my metformin" → take_medication(medicine_name="metformin")
- "I took my 8am meds at 10am" → take_medication(medicine_name="8am meds")
- "took my creatine" → take_supplement(supplement_name="creatine")
- "I took my vitamin D" → take_supplement(supplement_name="vitamin D")
- "took my fish oil" → take_supplement(supplement_name="fish oil")
- "took my evening meds" → take_intake_by_time(time_of_day="evening")
- "mark morning medicines taken" → take_intake_by_time(time_of_day="morning")
- "took all my nightly pills" → take_intake_by_time(time_of_day="nightly")
- "took my morning supplements" → take_intake_by_time(time_of_day="morning")
- "I took my two evening medicines, mark them took at scheduled time" → take_intake_by_time(time_of_day="evening", use_scheduled_time=true)
- "email me my list of medicines" → email_intake_list()
- "send my medicine list to dannyjenkins71@gmail.com" → email_intake_list(recipient_email="dannyjenkins71@gmail.com")
- "email my medications to my doctor at doc@example.com" → email_intake_list(recipient_email="doc@example.com")
- "I need a list of my medicines emailed to me" → email_intake_list()
- "send me my medication list" → email_intake_list()
- "starting a fast" → start_fast(fasting_type="16:8")
- "ending my fast" → end_fast()

FAITH:
- "save John 3:16" → save_verse(reference="John 3:16")
- "bookmark Romans 8:28" → save_verse(reference="Romans 8:28")
- "remember Psalm 23" → save_verse(reference="Psalm 23")
- "keep Philippians 4:13" → save_verse(reference="Philippians 4:13")
- "pray for my mom's health" → log_prayer(title="Mom's health", is_personal=false)
- "add prayer for my job interview" → log_prayer(title="Job interview")
- "God answered my prayer about the job" → mark_prayer_answered(prayer_keyword="job")
- "today was a spiritual breakthrough" → add_faith_milestone(title="Spiritual breakthrough")

IMPORTANT — save_verse requires an EXPLICIT save/bookmark/keep action word. These are NOT save_verse:
- "the screen has Matthew 13:1-30" → NO function (stating what's on screen)
- "you did not pick from Matthew 13:1-30" → NO function (correcting the AI)
- "help me understand Psalm 23" → NO function (asking for explanation)
- "what does Romans 8:28 mean?" → NO function (asking about content)
- "I'm reading John 3 right now" → NO function (mentioning, not saving)
- "today's reading is Matthew 5" → NO function (context, not saving)

JOURNAL:
- "I'm grateful for my family" → add_gratitude(gratitude="my family")
- "thankful for a good night's sleep" → add_gratitude(gratitude="a good night's sleep")
- "I want to journal about today" → create_journal_entry(title="Today's reflection")

PURPOSE:
- "I want to lose 30 pounds" → create_goal(title="Lose 30 pounds", domain="health")
- "I made progress on my weight goal — down 5 lbs" → update_goal_progress(goal_keyword="weight", progress_notes="Down 5 lbs")
- "I want to be more patient with my kids" → set_intention(intention="Be more patient with my kids")
- "did my Bible reading today" → log_habit(habit_keyword="Bible reading", completed=true)
- "completed my morning routine" → log_habit(habit_keyword="morning routine", completed=true)

LIFE/TASKS:
- "add task to call mom" → create_task(title="Call mom")
- "remind me to buy groceries" → create_task(title="Buy groceries")
- "add a task today at 10am to buy new battery for the Jeep" → create_task(title="Buy new battery for the Jeep", due_date="today", scheduled_time="10:00")
- "add task to file taxes by Friday at 3pm" → create_task(title="File taxes", due_date="friday", scheduled_time="15:00")
- "add a task today at 5pm - 6pm to Gather Tax Papers" → create_task(title="Gather Tax Papers", due_date="today", scheduled_time="17:00", end_time="18:00")
- "task from 2pm to 3:30pm tomorrow: Team sync" → create_task(title="Team sync", due_date="tomorrow", scheduled_time="14:00", end_time="15:30")
- "add a foundational task to work out tomorrow" → create_task(title="Work out", due_date="tomorrow", commitment_level="foundational")
- "create a flexible reminder to check the mail" → create_task(title="Check the mail", commitment_level="flexible")
- "I finished the laundry task" → complete_task(task_keyword="laundry")
- "skip the grocery task" → skip_task(task_keyword="grocery")
- "I'm going to pass on the dentist task" → skip_task(task_keyword="dentist")
- "skip my workout task, not feeling well" → skip_task(task_keyword="workout", reason="not feeling well")
- "what time is my jeep task?" → read_task(task_keyword="jeep")
- "show me my tasks for today" → read_task(date_filter="today")
- "when is the grocery task due?" → read_task(task_keyword="grocery")
- "what tasks do I have this week?" → read_task(date_filter="this_week")
- "anything left for me to do today?" → NO ACTION (this is a conversational check-in, not a task lookup)
- "how's my day going?" → NO ACTION (conversational — let the assistant answer naturally)
- "what's on my plate?" → NO ACTION (conversational check-in)
- "remember my wife's birthday is March 15" → add_reminder(title="Wife's Birthday", event_type="birthday", event_date="03-15")
- "add Quiet Time to my daily routine at 5:30am" → create_routine_task(title="Quiet Time", scheduled_time="05:30")
- "I want a daily workout at 6am" → create_routine_task(title="Workout", scheduled_time="06:00", duration_minutes=45)
- "schedule my evening walk every day at 7pm" → create_routine_task(title="Evening Walk", scheduled_time="19:00", duration_minutes=30)

EVENT HISTORY & DATA LOOKUP (query_event_history) — use when user asks about past events, specific data, missed items, or wants to look up any recorded data:

Data lookup (query_type="lookup"):
- "how did I sleep last night?" → query_event_history(query_type="lookup", domain="sleep", count=1)
- "what's my weight?" → query_event_history(query_type="lookup", domain="weight", count=1)
- "what was my blood pressure?" → query_event_history(query_type="lookup", domain="blood_pressure", count=1)
- "how was my glucose after lunch?" → query_event_history(query_type="lookup", domain="glucose", count=1)
- "how many steps did I get yesterday?" → query_event_history(query_type="lookup", domain="steps", target_date="yesterday")
- "how much water did I drink today?" → query_event_history(query_type="lookup", domain="water", target_date="today")
- "what did I eat yesterday?" → query_event_history(query_type="lookup", domain="nutrition", target_date="yesterday")
- "how long was my last fast?" → query_event_history(query_type="lookup", domain="fasting", count=1)
- "did I journal yesterday?" → query_event_history(query_type="lookup", domain="journal", target_date="yesterday")
- "what did I spend today?" → query_event_history(query_type="lookup", domain="finance", target_date="today")
- "show me my recent heart rate" → query_event_history(query_type="lookup", domain="heart_rate", count=3)
- "last 3 weight entries" → query_event_history(query_type="lookup", domain="weight", count=3)
- "my prayer requests" → query_event_history(query_type="lookup", domain="faith", count=5)
- "how are my habits going?" → query_event_history(query_type="lookup", domain="habits", lookback_days=7)

Missed items (query_type="missed"):
- "what did I miss?" → query_event_history(query_type="missed", domain="all", lookback_days=7)
- "which medication did I miss?" → query_event_history(query_type="missed", domain="medication", lookback_days=7)
- "it says I missed 5 doses" → query_event_history(query_type="missed", domain="medication", lookback_days=8)

Timeline (query_type="timeline"):
- "what happened yesterday?" → query_event_history(query_type="timeline", target_date="yesterday")

Slippage (query_type="slippage"):
- "when did my routine start slipping?" → query_event_history(query_type="slippage", domain="routine", lookback_days=14)

NOTE: This is READ-ONLY. Do NOT use for logging, marking complete, or any mutation. The user is asking about recorded data.

ROUTINE RECOVERY (reschedule_routine_item) — use when user wants to move a missed routine item to later today:
- "move my workout to 7pm" → reschedule_routine_item(item_keyword="workout", new_time="19:00")
- "I'll do prayer time at noon" → reschedule_routine_item(item_keyword="prayer", new_time="12:00")
- "reschedule quiet time to 5:30pm" → reschedule_routine_item(item_keyword="quiet time", new_time="17:30")
NOTE: This is for ROUTINE ITEMS only (recurring daily habits), not tasks. For task rescheduling, use mutate_task.

TASK UPDATES (mutate_task) — use for ANY task mutation verb:
When the user says move, reschedule, push, postpone, change, rename, update, or delete referring to a task, call mutate_task DIRECTLY. Do NOT use read_task for these.
- "move those two tasks to tomorrow" → mutate_task(action="update", task_query="office", new_due_date="tomorrow", apply_to_all=true)
- "push the grocery task to next week" → mutate_task(action="update", task_query="grocery", new_due_date="next week")
- "move my desk task to tomorrow afternoon" → mutate_task(action="update", task_query="desk", new_due_date="tomorrow", new_scheduled_time="13:00")
- "change my tax task to 3pm - 4pm" → mutate_task(action="update", task_query="tax", new_scheduled_time="15:00", new_end_time="16:00")
- "reschedule the battery task to Friday" → mutate_task(action="update", task_query="battery", new_due_date="friday")
- "rename my call task to 'Call Mom back'" → mutate_task(action="update", task_query="call", new_title="Call Mom back")
- "delete the laundry task" → mutate_task(action="delete", task_query="laundry")
- "remove my dentist task" → mutate_task(action="delete", task_query="dentist")
- "delete Approve Payroll completely" → mutate_task(action="delete", task_query="Approve Payroll", delete_series=true)
- "remove the recurring grocery task permanently" → mutate_task(action="delete", task_query="grocery", delete_series=true)
- "stop this recurring task from coming back" → mutate_task(action="delete", task_query=<from context>, delete_series=true)
- "move all my tasks to tomorrow" → mutate_task(action="update", task_query="", new_due_date="tomorrow", apply_to_all=true)
- "make my Charge Watch task foundational" → mutate_task(action="update", task_query="Charge Watch", new_commitment_level="foundational")
- "change my workout to flexible" → mutate_task(action="update", task_query="workout", new_commitment_level="flexible")
- "set the grocery task as important" → mutate_task(action="update", task_query="grocery", new_commitment_level="important")

CRITICAL ROUTING RULE: If the user's message contains a mutation verb (move, reschedule, push, postpone, change, rename, update, delete, remove) referring to tasks, you MUST call mutate_task — NEVER call read_task for these.

CRITICAL DELETE SAFETY:
- NEVER batch-delete tasks unless the user EXPLICITLY says "delete" or "remove" with clear intent to permanently remove tasks.
- "Don't show me those", "I don't need to see those", "hide completed tasks", "you shouldn't show everything" → these are DISPLAY preferences, NOT delete requests. Do NOT call mutate_task(action="delete") for these. Instead, acknowledge the preference and adjust what you show next time.
- "I already did those" or "those are done" → call complete_task for each, NOT delete.
- Only use mutate_task(action="delete") when the user explicitly says "delete", "remove", or "cancel" a specific task by name.

DELETE CONFIRMATION FLOW (REQUIRED):
- When calling mutate_task(action="delete"), NEVER set delete_confirmed=true on the first call. The system will ask the user to confirm.
- Only set delete_confirmed=true AFTER the user has explicitly confirmed (e.g., "yes", "yes delete it", "go ahead", "confirm").
- Example flow:
  1. User: "delete the laundry task" → mutate_task(action="delete", task_query="laundry") [NO delete_confirmed]
  2. System: "Just to confirm — you want me to delete this task? • Laundry. Say 'yes, delete' to confirm."
  3. User: "yes" → mutate_task(action="delete", task_query="laundry", delete_confirmed=true)

RECURRING TASK DELETION:
- When user says "delete completely", "permanently remove", "get rid of it entirely", or "stop this recurring task", set delete_series=true.
- delete_series=true deletes ALL instances of the recurring series and stops future recurrence.
- If the user just says "delete [task name]" and the task is recurring, the system will ask whether to delete the series or just this instance.
- "delete the series" / "all of them" / "the whole thing" after being asked → mutate_task(action="delete", task_query=..., delete_confirmed=true, delete_series=true)
- "just this one" / "only this instance" → mutate_task(action="delete", task_query=..., delete_confirmed=true, delete_series=false)
- The CoS MUST execute task deletions — NEVER tell the user to "handle it manually" or "do it in the UI". Deletion is a supported UAIO action.

IMPLICIT TASK CORRECTIONS — when the user says a task has wrong details or confirms a change should have happened:
- "those tasks should be tomorrow" → mutate_task(action="update", task_query=<from context>, new_due_date="tomorrow", apply_to_all=true)
- "you didn't actually move them" → mutate_task(action="update", task_query=<from context>, new_due_date=<from prior context>, apply_to_all=true)
- "they are still showing today" → infer the user wanted them moved; use prior context to determine the target date
When the user reports that a previous action didn't work ("you didn't do it", "still showing", "it's still wrong"), re-execute the action — do NOT just apologize.

TIME RANGES — when a user provides a time range (e.g., "5pm - 6pm", "from 2:00 to 3:30", "10am to 11am"):
- For tasks: extract BOTH times as scheduled_time (start) and end_time (end) in HH:MM 24-hour format
- For events: extract BOTH as start_time and end_time
- NEVER drop the end time — if the user gives a range, ALWAYS include both scheduled_time/start_time AND end_time

IMPORTANT — task vs routine vs event:
- "add a task at 10am" → create_task with scheduled_time (one-time task at specific time)
- "add X to my daily routine at 6am" → create_routine_task (recurring daily task)
- "schedule a meeting at 2pm" → create_event (calendar event)
When the user says "add a task" with a time, use create_task with scheduled_time — do NOT use create_event or create_routine_task unless they explicitly say "event", "calendar", "daily routine", or "every day".

TASK vs CALENDAR DISAMBIGUATION for mutations (delete/remove/update):
When the user says "remove" or "delete" something ambiguous (could be a task OR calendar event):
- If the user mentions "from my calendar", "calendar entry", or the item is visible in the calendar section → use mutate_calendar_event
- If the item shows a specific time (e.g., "10:00 PM Take trash out") and appears to be a scheduled calendar entry → prefer mutate_calendar_event
- If the user previously identified the item as a calendar event in the conversation → use mutate_calendar_event
- If the user says "task" explicitly → use mutate_task
- Default: if unclear, try mutate_task first. If it fails with task_not_found, the system will check for matching calendar events automatically.

CALENDAR EVENTS:
- "add to my calendar 5am Wake Up for tomorrow" → create_event(title="Wake Up", start_date="tomorrow", start_time="05:00")
- "schedule a meeting at 2pm today" → create_event(title="Meeting", start_date="today", start_time="14:00")
- "add Bible Study Wednesday 6pm-8pm" → create_event(title="Bible Study", start_date="wednesday", start_time="18:00", end_time="20:00", event_type="faith")
- "put Pickleball on my calendar for Friday 6pm" → create_event(title="Pickleball", start_date="friday", start_time="18:00", event_type="health")
- "add a Strategy Meeting next Wednesday at 7:30am" → create_event(title="Strategy Meeting", start_date="next wednesday", start_time="07:30")
- "schedule a review for next Friday" → create_event(title="Review", start_date="next friday", start_time="09:00")

FITNESS:
- "just finished my workout" → log_workout(name="Workout")
- "I did 10 pushups, 20 squats, and 30 crunches" → log_workout(name="Bodyweight workout", exercises=[{{"name":"pushups","reps":10}},{{"name":"squats","reps":20}},{{"name":"crunches","reps":30}}])
- "did leg day at the gym" → log_workout(name="Leg day")
- "bench press 185 for 8 reps" → log_exercise_set(exercise_name="bench press", weight=185, reps=8)
- "3 sets of 10 at 135 on squat" → log_exercise_set(exercise_name="squat", weight=135, reps=10, set_number=3)
- "ran 3 miles in 30 minutes" → log_cardio(activity="running", duration_minutes=30, distance=3.0, distance_unit="miles")
- "walked for 45 minutes" → log_cardio(activity="walking", duration_minutes=45)
- "biked 10 miles" → log_cardio(activity="cycling", duration_minutes=60, distance=10.0, distance_unit="miles")

IMPORTANT: For create_event and mutate_calendar_event, pass the user's EXACT date phrase including modifiers. Examples:
- User says "Wednesday" → start_date="wednesday" (this week's Wednesday)
- User says "next Wednesday" → start_date="next wednesday" (FOLLOWING week, not this week)
- User says "last Friday" → start_date="last friday" (most recent past Friday)
- User says "in 3 days" → start_date="in 3 days"
NEVER compute YYYY-MM-DD from weekday names — the server resolves all of these. Only use YYYY-MM-DD when the user specifies an exact date like "March 15" or "2026-03-15".

CALENDAR QUERIES (read_calendar_events) — use ONLY for pure read/lookup:
- "what's on my calendar tomorrow?" → read_calendar_events(date_range_start="tomorrow", timezone="America/New_York")
- "do I have anything Wednesday?" → read_calendar_events(date_range_start="wednesday", timezone="America/New_York")
- "show me my meetings" → read_calendar_events(query_text="meeting", timezone="America/New_York")
- "what's scheduled this week?" → read_calendar_events(date_range_start="today", date_range_end="sunday", timezone="America/New_York")

CALENDAR UPDATES (mutate_calendar_event) — use for ANY mutation verb:
When the user says move, change, reschedule, shift, update, rename, or uses "from X to Y", call mutate_calendar_event DIRECTLY with event_query + event_date. Do NOT call read_calendar_events first.
- "Change my Workout next Wednesday from 6:15am to 7:00am" → mutate_calendar_event(action="update", event_query="Workout", event_date="next wednesday", start_time="07:00", idempotency_key="change-workout-wed-7am", timezone="America/New_York")
- "move my Wednesday meeting to Thursday" → mutate_calendar_event(action="update", event_query="meeting", event_date="wednesday", start_date="thursday", idempotency_key="move-meeting-wed-thu", timezone="America/New_York")
- "reschedule Bible Study to 6pm starting March 11th" → mutate_calendar_event(action="update", event_query="Bible Study", start_date="2026-03-11", start_time="18:00", idempotency_key="resched-biblestudy-mar11", timezone="America/New_York")
- "change my 2pm appointment to 3pm" → mutate_calendar_event(action="update", event_query="appointment", start_time="15:00", idempotency_key="change-appt-2pm-3pm", timezone="America/New_York")
- "rename my workout to Chest Day" → mutate_calendar_event(action="update", event_query="workout", title="Chest Day", idempotency_key="rename-workout-chestday", timezone="America/New_York")
- "shift my morning routine to 5am" → mutate_calendar_event(action="update", event_query="morning routine", start_time="05:00", idempotency_key="shift-routine-5am", timezone="America/New_York")

CALENDAR DELETIONS (mutate_calendar_event):
- "cancel my Wednesday event" → mutate_calendar_event(action="delete", event_query="event", event_date="wednesday", idempotency_key="cancel-wed-event", timezone="America/New_York")
- "remove the meeting from my calendar" → mutate_calendar_event(action="delete", event_query="meeting", idempotency_key="remove-meeting", timezone="America/New_York")

IMPLICIT CORRECTIONS — when the user says an event has wrong details:
- "Bible Study is at 6pm, not 7pm" → mutate_calendar_event(action="update", event_query="Bible Study", start_time="18:00", idempotency_key="fix-biblestudy-6pm", timezone="America/New_York")
- "that event should be at 2pm" → mutate_calendar_event(action="update", event_query=<from context>, start_time="14:00", ...)
- "my meeting is actually on Thursday, not Wednesday" → mutate_calendar_event(action="update", event_query="meeting", event_date="wednesday", start_date="thursday", ...)
- "that's not correct, it is at 6pm" → mutate_calendar_event(action="update", event_query=<from context>, start_time="18:00", ...)
When the user says something "is wrong", "is not correct", "should be", "is actually", or provides a correction with "not X, it's Y" — treat this as a mutation, NOT a conversational response.

CRITICAL ROUTING RULE: If the user's message contains a mutation verb (move, change, reschedule, shift, update, rename, cancel, delete, remove) referring to a calendar event, you MUST call mutate_calendar_event — NEVER call read_calendar_events for these. The system resolves the event internally from event_query.

CALENDAR CONFLICT HANDLING:
When you try to create or update an event and the system returns a conflict (requires_decision=True):
1. Present the conflict details to the user exactly as returned (conflicting event names, times, and suggested alternatives)
2. Ask the user what they'd like to do: override the conflict, pick an alternative time, or cancel
3. If user says "override", "proceed anyway", "book it anyway", or similar: retry the SAME create_event or mutate_calendar_event call with force_override=true
4. If user picks a suggested alternative time: create_event with the new start_time
5. NEVER set force_override=true on the first attempt — only after explicit user confirmation

LOGGING LIFE EVENTS (wake up, sleep, arrivals, etc.):
When the user says "add that I woke up at 6:30am" or "log that I went to bed at 10pm" or similar life-tracking statements with "add", "log", or "record", create a calendar event to record it:
- "add that I woke up today at 6:30am" → create_event(title="Woke Up", start_date="{today_str}", start_time="06:30", event_type="personal")
- "log that I went to bed at 10pm" → create_event(title="Bedtime", start_date="{today_str}", start_time="22:00", event_type="personal")
- "record that I arrived at work at 8am" → create_event(title="Arrived at Work", start_date="{today_str}", start_time="08:00", event_type="work")

The key trigger words are "add that", "log that", "record that" — these mean the user wants an ENTRY CREATED, not just a conversational acknowledgment.

Examples of messages that should NOT trigger functions:
- "how are you?"
- "what's my heart rate history?"
- "tell me about fasting"
- "should I take my medicine?"
- "what does John 3:16 say?" (asking about content, not saving)
- "the screen has Matthew 13:1-30" (stating context, not saving)
- "look at Psalm 23" (referencing scripture, not saving)
- "I wake up at 5am every day" (sharing routine info, NOT scheduling an event)
- "my daily schedule is..." (sharing context, NOT creating events — unless they explicitly say "add to calendar")
- "how have my workouts been?" (asking about data, NOT logging a workout)
- "what are my goals?" (asking about goals, NOT creating one)

CLONING / "SAME" EVENTS (scheduling reliability):
When the user references a previous event with "same", "the same", "same workout", "same event", etc. and wants to schedule it on new dates, set clone_from_last=true.
This tells the system to inherit ALL parameters (title, time, duration, location, type) from the most recent scheduling action.

CRITICAL: When cloning, you MUST still provide every date via start_date. But do NOT invent a start_time — leave it omitted so the system can inherit the original time. Only include start_time if the user explicitly states a NEW time.

Examples:
- "Schedule the same workout on Feb 24, 25, 26" → multiple create_event calls, each with clone_from_last=true and the respective start_date, but NO start_time (inherited)
- "Put the same thing on my calendar for next Monday" → create_event(clone_from_last=true, start_date="monday")
- "Same workout but at 7am on Friday" → create_event(clone_from_last=true, start_date="friday", start_time="07:00") — user explicitly overrode time
"""

        # ── UI Context Grounding ──────────────────────────────────────
        # When page_context is available, append domain preference rules
        # so the LLM resolves ambiguous references ("those two", "mark
        # them done") against the user's current page domain.
        if page_context:
            domain_hint = self._resolve_domain_hint(page_context)
            page_title = page_context.get('page_title', '')
            help_context_id = page_context.get('help_context_id', '')
            module = page_context.get('module', '')

            if domain_hint or page_title:
                grounding = f"""

UI CONTEXT GROUNDING:
The user is currently viewing: {page_title}
Page ID: {help_context_id}
Module: {module}
Active domain: {domain_hint or 'general'}
"""
                # Optional visible entity hint
                entity_hint = self._build_visible_entity_hint(page_context)
                if entity_hint:
                    grounding += f"Visible objects: {entity_hint}\n"

                grounding += """
DOMAIN PREFERENCE RULE: When the user's message contains ambiguous references
(pronouns like 'those', 'them', 'the two', 'still pending', 'mark those'),
PREFER interpreting the action in the context of the ACTIVE DOMAIN above.

- On Medications page: "those two still pending" → take_medication (NOT complete_task)
- On Tasks page: "mark those done" → complete_task (NOT take_medication)
- On Fitness page: "log that" → log_workout (NOT log_food)

This rule only applies when the reference is AMBIGUOUS. If the user explicitly
names a different domain (e.g., "create a task to call the pharmacy" while on
the Medications page), honor the explicit domain.
"""
                prompt += grounding

        return prompt

    @staticmethod
    def _resolve_domain_hint(page_context: dict) -> str:
        """Resolve the active domain from page_context using 3-tier priority.

        Priority 1: help_context_id (most specific, stable across URL changes)
        Priority 2: module (Django app name)
        Priority 3: URL pattern fallback

        Returns a human-readable domain string or '' for neutral pages.
        """
        if not page_context:
            return ''

        # Priority 1: help_context_id → domain mapping
        help_id = (page_context.get('help_context_id') or '').upper()
        if help_id:
            HELP_ID_DOMAIN_MAP = {
                # Health / Medicine
                'HEALTH_MEDICINE_HOME': 'intake/health (take_medication, take_intake_by_time)',
                'HEALTH_MEDICINE_DETAIL': 'intake/health (take_medication)',
                'HEALTH_MEDICINE_ADD': 'intake/health',
                'HEALTH_MEDICINE_SCHEDULE': 'intake/health (take_medication, take_intake_by_time)',
                # Health / Fitness
                'HEALTH_FITNESS': 'fitness (log_workout, log_exercise_set, log_cardio)',
                'HEALTH_FITNESS_LOG': 'fitness (log_workout, log_exercise_set)',
                'HEALTH_FITNESS_CARDIO': 'fitness (log_cardio)',
                # Health / Vitals
                'HEALTH_VITALS': 'health vitals (log_heart_rate, log_blood_pressure, log_weight, log_glucose, log_blood_oxygen)',
                'HEALTH_FOOD': 'health nutrition (log_food)',
                'HEALTH_FASTING': 'health fasting (start_fast, end_fast)',
                'HEALTH_HOME': 'health (general health domain)',
                # Life / Tasks
                'LIFE_TASKS': 'life/tasks (create_task, complete_task, mutate_task)',
                'LIFE_TASK_DETAIL': 'life/tasks (complete_task, mutate_task)',
                'LIFE_HOME': 'life (create_task, complete_task)',
                # Calendar
                'LIFE_CALENDAR': 'calendar (create_event, mutate_calendar_event, read_calendar_events)',
                # Faith
                'FAITH_HOME': 'faith (log_prayer, save_verse, add_faith_milestone)',
                'FAITH_PRAYER': 'faith/prayer (log_prayer, mark_prayer_answered)',
                'FAITH_BIBLE': 'faith/bible (save_verse)',
                # Journal
                'JOURNAL_HOME': 'journal (create_journal_entry, add_gratitude)',
                'JOURNAL_ENTRY': 'journal (create_journal_entry)',
                # Purpose
                'PURPOSE_HOME': 'purpose (create_goal, set_intention, log_habit)',
                'PURPOSE_GOALS': 'purpose/goals (create_goal, update_goal_progress)',
                # Dashboard
                'DASHBOARD_HOME': 'dashboard (general — no specific domain preference)',
            }
            domain = HELP_ID_DOMAIN_MAP.get(help_id)
            if domain:
                return domain

        # Priority 2: module → domain mapping
        module = (page_context.get('module') or '').lower()
        if module:
            MODULE_DOMAIN_MAP = {
                'health': 'health (general health domain)',
                'faith': 'faith (log_prayer, save_verse)',
                'journal': 'journal (create_journal_entry, add_gratitude)',
                'purpose': 'purpose (create_goal, set_intention)',
                'life': 'life/tasks (create_task, complete_task)',
                'dashboard': 'dashboard (general)',
                'medical': 'intake/health',
                'finance': 'finance',
                'brain_training': 'brain training',
                'capture': 'capture',
            }
            domain = MODULE_DOMAIN_MAP.get(module)
            if domain:
                return domain

        # Priority 3: URL pattern fallback
        url = (page_context.get('url') or '').lower()
        if url:
            URL_PATTERNS = [
                ('/medication', 'intake/health (take_medication, take_intake_by_time)'),
                ('/fitness', 'fitness (log_workout, log_exercise_set, log_cardio)'),
                ('/vitals', 'health vitals'),
                ('/food', 'health nutrition (log_food)'),
                ('/fasting', 'health fasting (start_fast, end_fast)'),
                ('/task', 'life/tasks (create_task, complete_task, mutate_task)'),
                ('/calendar', 'calendar (create_event, mutate_calendar_event)'),
                ('/prayer', 'faith/prayer (log_prayer, mark_prayer_answered)'),
                ('/bible', 'faith/bible (save_verse)'),
                ('/journal', 'journal (create_journal_entry)'),
            ]
            for pattern, domain in URL_PATTERNS:
                if pattern in url:
                    return domain

        return ''  # Neutral page — no domain preference

    @staticmethod
    def _build_visible_entity_hint(page_context: dict) -> str:
        """Build a lightweight hint about visible entities from page_content.

        Scans page_content for recognizable entity types and returns a
        brief description (e.g., '2 pending medications', 'task: Buy groceries').
        Returns '' if nothing recognizable.
        """
        page_content = page_context.get('page_content', '')
        if not page_content:
            return ''

        # page_content may arrive as a dict from some page contexts — coerce to str
        if not isinstance(page_content, str):
            page_content = str(page_content)

        hints = []
        content_lower = page_content.lower()

        # Medication hints
        if 'medication' in content_lower or 'medicine' in content_lower:
            # Count "pending" or "due" mentions
            pending_count = content_lower.count('pending')
            due_count = content_lower.count('due')
            total = pending_count + due_count
            if total > 0:
                hints.append(f'{total} pending medication{"s" if total != 1 else ""}')
            elif 'medication' in content_lower:
                hints.append('medications')

        # Task hints
        if 'task' in content_lower:
            pending = content_lower.count('pending')
            if pending > 0:
                hints.append(f'{pending} pending task{"s" if pending != 1 else ""}')
            else:
                hints.append('tasks')

        # Prayer hints
        if 'prayer' in content_lower:
            unanswered = content_lower.count('unanswered')
            if unanswered > 0:
                hints.append(f'{unanswered} unanswered prayer{"s" if unanswered != 1 else ""}')

        return ', '.join(hints) if hints else ''

    # Mutation verbs that MUST route to mutate_calendar_event, not read.
    CALENDAR_MUTATION_VERBS = {
        'move', 'change', 'reschedule', 'shift', 'update',
        'rename', 'cancel', 'delete', 'remove',
        'mark', 'label', 'tag', 'categorize', 'set',
    }

    # Domain-aware intent detection for forced retry when no_action is returned.
    # Each domain defines verbs (in the current message) and keywords
    # (in the current message OR conversation history) that must BOTH match.
    # Covers mutations (delete/update/complete) AND creation (add/create/schedule).
    MUTATION_DOMAIN_MAP = {
        'calendar_mutate': {
            'verbs': {
                'delete', 'remove', 'cancel', 'update', 'change',
                'edit', 'reschedule', 'move', 'shift', 'rename',
            },
            'keywords': {
                'calendar', 'event', 'meeting', 'wake up', 'reminder',
                'appointment', 'schedule', 'scheduled',
            },
            'function': 'mutate_calendar_event',
        },
        'calendar_create': {
            'verbs': {
                'add', 'create', 'schedule', 'book', 'plan',
            },
            'keywords': {
                'calendar', 'event', 'meeting', 'appointment',
            },
            'function': 'create_event',
        },
        'task_create': {
            'verbs': {
                'add', 'create', 'make', 'schedule', 'remind',
            },
            'keywords': {
                'task', 'to-do', 'todo', 'to do', 'reminder',
                'remind me',
            },
            'function': 'create_task',
        },
        'task_complete': {
            'verbs': {'complete', 'finish', 'done'},
            'keywords': {'task', 'to-do', 'todo', 'to do'},
            'function': 'complete_task',
        },
        'task_skip': {
            'verbs': {'skip', 'pass'},
            'keywords': {'task', 'to-do', 'todo', 'to do'},
            'function': 'skip_task',
        },
        'task_mutate': {
            'verbs': {
                'delete', 'remove', 'edit', 'update', 'change',
                'reschedule', 'rename',
            },
            'keywords': {'task', 'to-do', 'todo', 'to do'},
            'function': 'mutate_task',
        },
    }
    # Multi-word verb phrases to check beyond single-token split.
    _MULTI_WORD_VERB_PHRASES = {
        'mark done': 'task_complete',
        'mark complete': 'task_complete',
        'mark as done': 'task_complete',
        'mark as complete': 'task_complete',
        'set up': 'task_create',
        'remind me': 'task_create',
        'add a task': 'task_create',
        'add a reminder': 'task_create',
        'add an event': 'calendar_create',
        'add a meeting': 'calendar_create',
        'add an appointment': 'calendar_create',
        'schedule a meeting': 'calendar_create',
        'schedule an event': 'calendar_create',
        'schedule an appointment': 'calendar_create',
    }

    def _enforce_mutation_routing(
        self, user_message: str, read_params: dict,
    ) -> Optional[dict]:
        """
        Post-recognition safety net: if the LLM chose read_calendar_events
        but the user's message contains a mutation verb, reroute to
        mutate_calendar_event with the read params converted to event_query.

        Returns a dict with 'intent_type' and 'parameters', or None if
        no reroute needed.
        """
        msg_lower = user_message.lower()
        tokens = set(msg_lower.split())

        # Check if any mutation verb appears in the message
        if not tokens.intersection(self.CALENDAR_MUTATION_VERBS):
            # Also check multi-word patterns
            mutation_phrases = ['from ', ' to ']
            has_from_to = all(p in msg_lower for p in mutation_phrases)
            if not has_from_to:
                return None

        # Determine action: delete-class verbs vs update-class verbs
        delete_verbs = {'cancel', 'delete', 'remove'}
        if tokens.intersection(delete_verbs):
            action = 'delete'
        else:
            action = 'update'

        # Build mutate params from read params
        mutate_params = {
            'action': action,
            'idempotency_key': f"rerouted-{action}-{hash(user_message) % 100000}",
            'timezone': read_params.get('timezone', 'America/Chicago'),
        }

        # Convert query_text → event_query
        if read_params.get('query_text'):
            mutate_params['event_query'] = read_params['query_text']

        # Convert date_range_start → event_date
        if read_params.get('date_range_start'):
            mutate_params['event_date'] = read_params['date_range_start']

        return {
            'intent_type': 'mutate_calendar_event',
            'parameters': mutate_params,
        }

    def _detect_mutation_domain(
        self,
        user_message: str,
        conversation_history: Optional[list] = None,
    ) -> Optional[tuple]:
        """Detect if a mutation verb + domain keyword are present.

        Checks the current message for mutation verbs, then checks both
        the current message AND conversation history for domain keywords.

        Returns:
            (forced_function_name, verb_matched, keyword_matched) or None.
        """
        msg_lower = user_message.lower()
        msg_tokens = set(msg_lower.split())

        # Build searchable text: current message + all conversation history content
        all_text = msg_lower
        if conversation_history:
            for entry in conversation_history:
                content = (entry.get('content') or '').lower()
                if content:
                    all_text += ' ' + content

        # Check multi-word verb phrases first (more specific)
        for phrase, domain_key in self._MULTI_WORD_VERB_PHRASES.items():
            if phrase in msg_lower:
                domain = self.MUTATION_DOMAIN_MAP.get(domain_key)
                if domain:
                    # Check keywords in all text
                    for kw in domain['keywords']:
                        if kw in all_text:
                            return (domain['function'], phrase, kw)

        # Check single-word verbs per domain
        for domain_key, domain in self.MUTATION_DOMAIN_MAP.items():
            matched_verb = msg_tokens.intersection(domain['verbs'])
            if not matched_verb:
                continue

            verb = next(iter(matched_verb))

            # Check keywords in all text (current message + history)
            for kw in domain['keywords']:
                if kw in all_text:
                    return (domain['function'], verb, kw)

        return None

    def _retry_with_forced_mutation(
        self,
        messages: list,
        forced_function: str,
        user,
        user_message: str,
    ) -> Optional[List[IntentResult]]:
        """Retry intent recognition with forced function calling.

        When the initial call returned no_action but mutation verb + domain
        keyword were detected, this method retries with tool_choice forcing
        the specific function.

        Returns:
            List of IntentResult on success, or None on failure.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=ALL_INTENT_TOOLS,
                tool_choice={
                    "type": "function",
                    "function": {"name": forced_function},
                },
                max_tokens=500,
                temperature=0.1,
            )

            # --- Owner Finance telemetry (best-effort) ---
            try:
                usage = getattr(response, 'usage', None)
                if usage:
                    from apps.owner_finance.services.telemetry import log_llm_usage
                    log_llm_usage(
                        user=user,
                        feature='INTENT_RETRY',
                        model_name=self.model,
                        input_tokens=getattr(usage, 'prompt_tokens', 0),
                        output_tokens=getattr(usage, 'completion_tokens', 0),
                    )
            except Exception:
                pass

            message = response.choices[0].message

            if not message.tool_calls:
                return None

            results = []
            for tool_call in message.tool_calls:
                function_name = tool_call.function.name
                try:
                    parameters = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    logger.warning(
                        "[INTENT_RETRY] Failed to parse tool call args for %s: %s",
                        function_name, tool_call.function.arguments,
                    )
                    continue  # Skip malformed tool call

                requires_confirmation, confirmation_message = self._check_validation(
                    function_name, parameters, user
                )

                results.append(IntentResult(
                    intent_type=function_name,
                    parameters=parameters,
                    confidence=0.8,  # Slightly lower confidence for retried intents
                    requires_confirmation=requires_confirmation,
                    confirmation_message=confirmation_message,
                    raw_response=message.content,
                ))

            return results if results else None

        except Exception as e:
            logger.error(
                "[MUTATION_RETRY] Retry failed for forced %s: %s",
                forced_function, e, exc_info=True,
            )
            return None

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

        # --- Settings mutation confirmation (always required) ---
        # Settings changes like renaming the assistant must ALWAYS
        # require confirmation. This prevents silent mutations from
        # misrouted intents or accidental triggers.
        elif intent_type == 'set_cos_name':
            new_name = parameters.get('name', '').strip()
            if new_name:
                msg = (
                    f'Change my name to "{new_name}"? '
                    f"Reply yes to confirm, or no to cancel."
                )
            else:
                msg = (
                    "Reset my name back to the default? "
                    "Reply yes to confirm, or no to cancel."
                )
            return True, msg

        return False, ""

    def _build_confirmation_message(self, intent_type: str, parameters: dict) -> str:
        """Build a human-sounding confirmation message for an action."""
        if intent_type == 'log_heart_rate':
            bpm = parameters.get('bpm', 0)
            context = parameters.get('context', 'resting')
            return f"Logging {bpm} BPM ({context}) for your heart rate."

        elif intent_type == 'log_blood_pressure':
            systolic = parameters.get('systolic', 0)
            diastolic = parameters.get('diastolic', 0)
            return f"Logging blood pressure: {systolic}/{diastolic}."

        elif intent_type == 'log_weight':
            value = parameters.get('value', 0)
            unit = parameters.get('unit', 'lb')
            return f"Logging your weight as {value} {unit}."

        elif intent_type == 'log_glucose':
            value = parameters.get('value', 0)
            unit = parameters.get('unit', 'mg/dL')
            return f"Logging blood glucose: {value} {unit}."

        elif intent_type == 'log_blood_oxygen':
            spo2 = parameters.get('spo2', 0)
            return f"Logging blood oxygen: {spo2}%."

        elif intent_type == 'log_food':
            food = parameters.get('food_name', 'food')
            quantity = parameters.get('quantity', 1)
            return f"Logging {quantity} serving(s) of {food}."

        elif intent_type == 'take_medication':
            medicine = parameters.get('medicine_name', 'medication')
            return f"Marking {medicine} as taken."

        elif intent_type == 'take_supplement':
            supplement = parameters.get('supplement_name', 'supplement')
            return f"Logging {supplement} as taken."

        elif intent_type == 'take_intake_by_time':
            tod = parameters.get('time_of_day', 'scheduled')
            scheduled = parameters.get('use_scheduled_time', False)
            time_note = " at their scheduled times" if scheduled else ""
            return f"Marking all {tod} intakes as taken{time_note}."

        elif intent_type == 'start_fast':
            fasting_type = parameters.get('fasting_type', '16:8')
            return f"Starting a {fasting_type} fast."

        elif intent_type == 'end_fast':
            return "Ending your current fast."

        # Journal intents
        elif intent_type == 'create_journal_entry':
            body = parameters.get('body', '')[:50]
            return f"Saving a journal entry: \"{body}...\""

        elif intent_type == 'add_gratitude':
            gratitude = parameters.get('gratitude', '')
            return f"Noting gratitude: {gratitude}."

        # Faith intents
        elif intent_type == 'log_prayer':
            title = parameters.get('title', 'prayer')
            return f"Adding prayer: {title}."

        elif intent_type == 'save_verse':
            reference = parameters.get('reference', '')
            return f"Saving {reference} to your collection."

        # Purpose intents
        elif intent_type == 'create_goal':
            title = parameters.get('title', 'goal')
            return f"Creating goal: {title}."

        elif intent_type == 'set_intention':
            intention = parameters.get('intention', '')
            return f"Setting your intention: {intention}."

        # Life intents
        elif intent_type == 'create_task':
            title = parameters.get('title', 'task')
            return f"Adding \"{title}\" to your tasks."

        elif intent_type == 'create_routine_task':
            title = parameters.get('title', 'routine')
            time = parameters.get('scheduled_time', '')
            return f"Adding daily routine: {title} at {time}."

        elif intent_type == 'mutate_task':
            task_query = parameters.get('task_query', 'task')
            action = parameters.get('action', 'update')
            if action == 'delete':
                return f"Removing task \"{task_query}\"."
            else:
                new_date = parameters.get('new_due_date', '')
                date_hint = f" to {new_date}" if new_date else ""
                return f"Updating \"{task_query}\"{date_hint}."

        elif intent_type == 'create_event':
            title = parameters.get('title', 'event')
            return f"Adding {title} to your calendar."

        # Fitness intents
        elif intent_type == 'log_workout':
            name = parameters.get('name', 'workout')
            return f"Logging workout: {name}."

        elif intent_type == 'log_cardio':
            activity = parameters.get('activity', 'cardio')
            duration = parameters.get('duration_minutes', 0)
            return f"Logging {activity} for {duration} minutes."

        return "Confirming this action."

    def execute_intent(self, intent_result: IntentResult, user) -> ActionResult:
        """
        Execute a recognized intent by calling the appropriate action handler.

        Args:
            intent_result: The IntentResult from recognize_intent()
            user: The User model instance

        Returns:
            ActionResult with success status and details
        """
        # Defense-in-depth: Learning Mode gate (primary gate is in execution_engine)
        # Control-plane intents (enter/exit learning mode) always bypass.
        LEARNING_MODE_CONTROL_INTENTS = {'enter_learning_mode', 'exit_learning_mode'}
        try:
            from apps.core.blueprint.learning_mode import is_learning_mode_active
            if (is_learning_mode_active(user)
                    and intent_result.intent_type not in LEARNING_MODE_CONTROL_INTENTS):
                return ActionResult(
                    success=False,
                    message=(
                        "Learning Mode is active.\n"
                        "I'm listening and learning right now, not executing actions.\n"
                        "When you're ready, exit Learning Mode and I'll begin taking action."
                    ),
                    error='learning_mode_active',
                    action_type=intent_result.intent_type,
                )
        except ImportError:
            pass  # Learning Mode module not installed
        except Exception as e:
            logger.error(
                "Learning Mode check CRITICAL FAILURE in execute_intent "
                "(blocking execution for safety): %s", e, exc_info=True,
            )
            return ActionResult(
                success=False,
                message="Unable to verify safety state. Please try again.",
                error='learning_mode_check_failed',
                action_type=intent_result.intent_type,
            )

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

            elif intent_type == 'take_medication':
                return handler.handle_take_medication(**parameters)

            elif intent_type == 'take_supplement':
                return handler.handle_take_supplement(**parameters)

            elif intent_type == 'take_intake_by_time':
                return handler.handle_take_intake_by_time(**parameters)

            elif intent_type == 'email_intake_list':
                return handler.handle_email_intake_list(**parameters)

            elif intent_type == 'start_fast':
                return handler.handle_start_fast(**parameters)

            elif intent_type == 'end_fast':
                return handler.handle_end_fast(**parameters)

            # Journal handlers
            elif intent_type == 'create_journal_entry':
                return handler.handle_create_journal_entry(**parameters)

            elif intent_type == 'add_gratitude':
                return handler.handle_add_gratitude(**parameters)

            # Faith handlers
            elif intent_type == 'log_prayer':
                return handler.handle_log_prayer(**parameters)

            elif intent_type == 'mark_prayer_answered':
                return handler.handle_mark_prayer_answered(**parameters)

            elif intent_type == 'save_verse':
                return handler.handle_save_verse(**parameters)

            elif intent_type == 'add_faith_milestone':
                return handler.handle_add_faith_milestone(**parameters)

            # Purpose handlers
            elif intent_type == 'create_goal':
                return handler.handle_create_goal(**parameters)

            elif intent_type == 'update_goal_progress':
                return handler.handle_update_goal_progress(**parameters)

            elif intent_type == 'set_intention':
                return handler.handle_set_intention(**parameters)

            elif intent_type == 'log_habit':
                return handler.handle_log_habit(**parameters)

            # Life handlers
            elif intent_type == 'create_task':
                return handler.handle_create_task(**parameters)

            elif intent_type == 'create_routine_task':
                return handler.handle_create_routine_task(**parameters)

            elif intent_type == 'complete_task':
                return handler.handle_complete_task(**parameters)

            elif intent_type == 'skip_task':
                return handler.handle_skip_task(**parameters)

            elif intent_type == 'read_task':
                return handler.handle_read_task(**parameters)

            elif intent_type == 'mutate_task':
                return handler.handle_mutate_task(**parameters)

            elif intent_type == 'create_event':
                return handler.handle_create_event(**parameters)

            # Calendar CRUD handlers
            elif intent_type == 'read_calendar_events':
                return handler.handle_read_calendar_events(**parameters)

            elif intent_type == 'mutate_calendar_event':
                return handler.handle_mutate_calendar_event(**parameters)

            # Cross-domain event queries
            elif intent_type == 'query_event_history':
                return handler.handle_query_event_history(**parameters)

            elif intent_type == 'add_reminder':
                return handler.handle_add_reminder(**parameters)
            elif intent_type == 'reschedule_routine_item':
                return handler.handle_reschedule_routine_item(**parameters)

            # Fitness handlers
            elif intent_type == 'log_workout':
                return handler.handle_log_workout(**parameters)

            elif intent_type == 'log_exercise_set':
                return handler.handle_log_exercise_set(**parameters)

            elif intent_type == 'log_cardio':
                return handler.handle_log_cardio(**parameters)

            # Transformation handlers
            elif intent_type == 'log_transformation_protocol':
                return handler.handle_log_transformation_protocol(**parameters)

            elif intent_type == 'log_shopping_item':
                return handler.handle_log_shopping_item(**parameters)

            elif intent_type == 'complete_shopping_item':
                return handler.handle_complete_shopping_item(**parameters)

            # Settings handlers
            elif intent_type == 'set_cos_name':
                return handler.handle_set_cos_name(**parameters)

            # Calibration handlers
            elif intent_type == 'pause_calibration':
                return handler.handle_pause_calibration(**parameters)
            elif intent_type == 'complete_calibration':
                return handler.handle_complete_calibration(**parameters)

            # Learning Mode control-plane handlers
            elif intent_type == 'exit_learning_mode':
                return handler.handle_exit_learning_mode(**parameters)
            elif intent_type == 'enter_learning_mode':
                return handler.handle_enter_learning_mode(**parameters)

            # New health intents (sleep, water, steps, body measurement)
            elif intent_type == 'log_sleep':
                return handler.handle_log_sleep(**parameters)
            elif intent_type == 'log_water':
                return handler.handle_log_water(**parameters)
            elif intent_type == 'log_steps':
                return handler.handle_log_steps(**parameters)
            elif intent_type == 'log_body_measurement':
                return handler.handle_log_body_measurement(**parameters)

            # Finance handlers
            elif intent_type == 'log_transaction':
                return handler.handle_log_transaction(**parameters)
            elif intent_type == 'check_budget':
                return handler.handle_check_budget(**parameters)

            # System handlers (undo/edit)
            elif intent_type == 'undo_last_action':
                return handler.handle_undo_last_action(**parameters)
            elif intent_type == 'edit_last_entry':
                return handler.handle_edit_last_entry(**parameters)

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

    # ── Pending CRUD Action (global confirmation gate) ─────────────

    def store_pending_crud_action(self, user, data: dict, ttl: int = 300):
        """
        Store a pending CRUD action awaiting user confirmation.

        Dual-writes to cache (primary, fast) and DB (audit, durable).
        Adds idempotency key (action_id) and execution guard (executed flag).

        Args:
            user: The User model instance
            data: Dict with intent_type, parameters, confirmation_message,
                  options, etc.
            ttl: Time to live in seconds (default 5 minutes)
        """
        import uuid as _uuid
        action_id = str(_uuid.uuid4())
        data['action_id'] = action_id
        data['executed'] = False
        data['timestamp'] = timezone.now().isoformat()

        # Primary: cache write
        cache_key = f"pending_crud_{user.id}"
        cache.set(cache_key, data, ttl)

        # Secondary: DB write for audit and crash recovery
        try:
            from apps.core.ai_governance.models import PendingAction
            # Expire any stale pending actions for this user
            PendingAction.objects.filter(
                user=user, status='pending', action_type='crud',
            ).update(status='expired')
            PendingAction.objects.create(
                id=action_id,
                user=user,
                action_type='crud',
                intent_type=data.get('intent_type', ''),
                parameters=data.get('parameters', {}),
                options=data.get('options', []),
                confirmation_message=data.get('confirmation_message', ''),
                original_input=data.get('original_input', ''),
                recon_decision=data.get('recon_decision', ''),
                recon_context=data.get('recon_context'),
                expires_at=timezone.now() + timezone.timedelta(seconds=ttl),
            )
        except Exception as e:
            logger.error(
                "[PENDING_ACTION] DB write failed (cache is primary): %s",
                e, exc_info=True,
            )

    def get_pending_crud_action(self, user) -> Optional[Dict]:
        """
        Retrieve a pending CRUD action.

        Reads from cache first (fast), falls back to DB (durable).

        Returns:
            Dict with action details, or None if expired/missing
        """
        cache_key = f"pending_crud_{user.id}"
        result = cache.get(cache_key)
        if result:
            return result

        # Fallback: check DB for crash recovery
        try:
            from apps.core.ai_governance.models import PendingAction
            pending = PendingAction.objects.filter(
                user=user, status='pending', action_type='crud',
            ).order_by('-created_at').first()
            if pending and not pending.is_expired:
                # Reconstruct cache-compatible dict
                data = {
                    'action_id': str(pending.id),
                    'intent_type': pending.intent_type,
                    'parameters': pending.parameters,
                    'options': pending.options,
                    'confirmation_message': pending.confirmation_message,
                    'original_input': pending.original_input,
                    'recon_decision': pending.recon_decision,
                    'recon_context': pending.recon_context,
                    'executed': pending.executed,
                    'timestamp': pending.created_at.isoformat(),
                }
                # Re-populate cache
                remaining_ttl = int(
                    (pending.expires_at - timezone.now()).total_seconds()
                )
                if remaining_ttl > 0:
                    cache.set(cache_key, data, remaining_ttl)
                return data
            elif pending and pending.is_expired:
                # Auto-cleanup: mark expired in DB so it can't resurrect
                pending.status = 'expired'
                pending.save(update_fields=['status'])
        except Exception as e:
            logger.error(
                "[PENDING_ACTION] DB fallback read failed: %s",
                e, exc_info=True,
            )
        return None

    def clear_pending_crud_action(self, user):
        """Clear any pending CRUD action from both cache and database."""
        cache_key = f"pending_crud_{user.id}"
        cache.delete(cache_key)
        try:
            from apps.core.ai_governance.models import PendingAction
            PendingAction.objects.filter(
                user=user, status='pending', action_type='crud',
            ).update(status='cancelled')
        except Exception as e:
            logger.error(
                "[PENDING_ACTION] DB clear failed for user %s: %s",
                user.id, e, exc_info=True,
            )

    # ── Disambiguation (multi-candidate selection) ────────────────

    def store_pending_disambiguation(self, user, data: dict, ttl: int = 300):
        """
        Store a pending disambiguation awaiting user selection.

        After the user selects a candidate, the system constructs the
        appropriate intent and feeds it back through the CRUD gate.
        """
        data['timestamp'] = timezone.now().isoformat()
        cache_key = f"pending_disambiguate_{user.id}"
        cache.set(cache_key, data, ttl)

    def get_pending_disambiguation(self, user) -> Optional[dict]:
        """Retrieve pending disambiguation, or None if expired/missing."""
        cache_key = f"pending_disambiguate_{user.id}"
        return cache.get(cache_key)

    def clear_pending_disambiguation(self, user):
        """Clear any pending disambiguation for a user."""
        cache_key = f"pending_disambiguate_{user.id}"
        cache.delete(cache_key)

    def handle_disambiguation_response(self, user, response: str) -> Optional[ActionResult]:
        """
        Handle user's response to a disambiguation prompt.

        Two-step flow:
        1. User picks a number → system constructs the appropriate intent
        2. Intent is stored as pending CRUD action → user must CONFIRM

        Returns:
            ActionResult with the CRUD confirmation message, or None if unrecognized.
        """
        pending = self.get_pending_disambiguation(user)
        if not pending:
            return ActionResult(
                success=False,
                message="That disambiguation has expired. Please tell me what you'd like to do again.",
                action_type='expired',
            )

        from apps.core.ai_orchestrator.crud_confirmation import (
            parse_disambiguation_response,
            build_crud_confirmation_message,
        )

        candidates = pending.get('candidates', [])
        parsed = parse_disambiguation_response(response, len(candidates))

        if parsed is None:
            return None  # Unrecognized — caller will re-show prompt

        if parsed['action'] == 'cancel':
            self.clear_pending_disambiguation(user)
            logger.info(
                "[DISAMBIGUATE] Cancelled: user=%s original_intent=%s",
                user.id, pending.get('original_intent'),
            )
            return ActionResult(
                success=True,
                message="Action cancelled.",
                action_type='cancelled',
            )

        if parsed['action'] == 'create_new':
            self.clear_pending_disambiguation(user)
            # Feed the original create intent through the CRUD gate
            from apps.core.ai_orchestrator.action_router import EnrichedAction
            enriched = EnrichedAction(
                intent_type=pending['original_intent'],
                parameters=pending['create_params'],
                original_input=pending.get('original_input'),
            )
            msg = build_crud_confirmation_message(enriched, None)
            self.store_pending_crud_action(user, {
                'intent_type': pending['original_intent'],
                'parameters': pending['create_params'],
                'original_intent': pending['original_intent'],
                'original_input': pending.get('original_input'),
                'recon_decision': 'create',
                'recon_context': None,
                'confirmation_message': msg,
            })
            logger.info(
                "[DISAMBIGUATE] Create new: user=%s intent=%s",
                user.id, pending['original_intent'],
            )
            return ActionResult(
                success=False,
                message=msg,
                error='crud_confirmation_required',
                action_type=pending['original_intent'],
            )

        if parsed['action'] == 'select':
            idx = parsed['index']
            selected = candidates[idx]
            self.clear_pending_disambiguation(user)

            model = selected.get('model', '')
            create_params = pending.get('create_params', {})
            original_intent = pending.get('original_intent', '')

            if model == 'Task':
                return self._disambiguate_task_selection(
                    user, selected, create_params, original_intent, pending,
                )
            elif model == 'CalendarEvent':
                return self._disambiguate_event_selection(
                    user, selected, create_params, original_intent, pending,
                )
            else:
                # Fallback: create new for unknown model type
                logger.warning(
                    "[DISAMBIGUATE] Unknown model %s, falling back to create", model,
                )
                from apps.core.ai_orchestrator.action_router import EnrichedAction
                enriched = EnrichedAction(
                    intent_type=original_intent,
                    parameters=create_params,
                    original_input=pending.get('original_input'),
                )
                msg = build_crud_confirmation_message(enriched, None)
                self.store_pending_crud_action(user, {
                    'intent_type': original_intent,
                    'parameters': create_params,
                    'original_intent': original_intent,
                    'original_input': pending.get('original_input'),
                    'recon_decision': 'create',
                    'recon_context': None,
                    'confirmation_message': msg,
                })
                return ActionResult(
                    success=False,
                    message=msg,
                    error='crud_confirmation_required',
                    action_type=original_intent,
                )

        return None

    def _disambiguate_task_selection(self, user, selected, create_params, original_intent, pending):
        """Handle disambiguation selection for a Task candidate."""
        from apps.core.ai_orchestrator.action_router import EnrichedAction
        from apps.core.ai_orchestrator.crud_confirmation import build_crud_confirmation_message
        from apps.core.ai_orchestrator.activity_reconciliation import (
            _parse_time, _times_match, ReconciliationDecision, ReconciliationResult,
        )

        # Load actual task to get current time
        existing_time = None
        try:
            from apps.life.models import Task
            task_obj = Task.objects.get(id=selected['id'], user=user)
            existing_time = task_obj.scheduled_time
        except Exception:
            pass

        new_time = _parse_time(create_params.get('scheduled_time'))
        matched_obj = {
            'model': 'Task', 'id': selected['id'],
            'title': selected['title'],
            'time': str(existing_time) if existing_time else None,
        }

        if _times_match(new_time, existing_time):
            # Same time → SKIP
            time_str = existing_time.strftime('%I:%M %p').lstrip('0') if existing_time else 'today'
            recon = ReconciliationResult(
                decision=ReconciliationDecision.SKIP,
                original_intent=original_intent,
                confidence=1.0,
                matched_object=matched_obj,
                skip_message=(
                    f'You already have "{selected["title"]}" scheduled'
                    + (f' at {time_str}' if existing_time else '')
                    + '. No changes needed.'
                ),
                reason='disambiguated_same_time',
            )
            enriched = EnrichedAction(
                intent_type=original_intent,
                parameters=create_params,
                original_input=pending.get('original_input'),
            )
        else:
            # Different time → RESCHEDULE
            mutate_params = {
                'action': 'update',
                'task_query': selected['title'],
            }
            if create_params.get('scheduled_time'):
                mutate_params['new_scheduled_time'] = create_params['scheduled_time']
            if create_params.get('end_time'):
                mutate_params['new_end_time'] = create_params['end_time']
            if create_params.get('due_date'):
                mutate_params['new_due_date'] = create_params['due_date']
            for k, v in create_params.items():
                if k.startswith('_'):
                    mutate_params[k] = v

            recon = ReconciliationResult(
                decision=ReconciliationDecision.RESCHEDULE,
                original_intent=original_intent,
                confidence=1.0,
                matched_object=matched_obj,
                redirected_intent='mutate_task',
                redirected_params=mutate_params,
                reason='disambiguated_different_time',
            )
            enriched = EnrichedAction(
                intent_type='mutate_task',
                parameters=mutate_params,
                original_input=pending.get('original_input'),
            )

        msg = build_crud_confirmation_message(enriched, recon)
        self.store_pending_crud_action(user, {
            'intent_type': enriched.intent_type,
            'parameters': enriched.parameters,
            'original_intent': original_intent,
            'original_input': pending.get('original_input'),
            'recon_decision': recon.decision.value,
            'recon_context': recon.matched_object,
            'confirmation_message': msg,
        })

        logger.info(
            "[DISAMBIGUATE] Selected task #%s '%s' -> %s, user=%s",
            selected['id'], selected['title'], recon.decision.value, user.id,
        )

        return ActionResult(
            success=False,
            message=msg,
            error='crud_confirmation_required',
            action_type=enriched.intent_type,
        )

    def _disambiguate_event_selection(self, user, selected, create_params, original_intent, pending):
        """Handle disambiguation selection for a CalendarEvent candidate."""
        from apps.core.ai_orchestrator.action_router import EnrichedAction
        from apps.core.ai_orchestrator.crud_confirmation import build_crud_confirmation_message
        from apps.core.ai_orchestrator.activity_reconciliation import (
            _parse_time, _times_match, _build_event_mutate_params,
            ReconciliationDecision, ReconciliationResult,
        )

        # Load actual event to get current time
        existing_time = None
        event_obj = None
        try:
            from apps.calendar_engine.models import CalendarEvent
            event_obj = CalendarEvent.objects.get(id=selected['id'], user=user)
            if event_obj.start_dt:
                try:
                    from apps.core.utils import get_current_local_datetime
                    user_now = get_current_local_datetime(user)
                    existing_time = event_obj.start_dt.astimezone(user_now.tzinfo).time()
                except Exception:
                    existing_time = event_obj.start_dt.time()
        except Exception:
            pass

        new_time = _parse_time(create_params.get('start_time'))
        matched_obj = {
            'model': 'CalendarEvent', 'id': selected['id'],
            'title': selected['title'],
            'time': str(existing_time) if existing_time else None,
        }

        if _times_match(new_time, existing_time):
            # Same time → SKIP
            time_str = existing_time.strftime('%I:%M %p').lstrip('0') if existing_time else ''
            recon = ReconciliationResult(
                decision=ReconciliationDecision.SKIP,
                original_intent=original_intent,
                confidence=1.0,
                matched_object=matched_obj,
                skip_message=(
                    f'You already have "{selected["title"]}" on your calendar'
                    + (f' at {time_str}' if time_str else '')
                    + '. No changes needed.'
                ),
                reason='disambiguated_same_time',
            )
            enriched = EnrichedAction(
                intent_type=original_intent,
                parameters=create_params,
                original_input=pending.get('original_input'),
            )
        else:
            # Different time → RESCHEDULE
            if event_obj:
                mutate_params = _build_event_mutate_params(event_obj, create_params, user)
            else:
                mutate_params = {
                    'action': 'update',
                    'event_id': selected['id'],
                }
                if create_params.get('start_time'):
                    mutate_params['start_time'] = create_params['start_time']

            recon = ReconciliationResult(
                decision=ReconciliationDecision.RESCHEDULE,
                original_intent=original_intent,
                confidence=1.0,
                matched_object=matched_obj,
                redirected_intent='mutate_calendar_event',
                redirected_params=mutate_params,
                reason='disambiguated_different_time',
            )
            enriched = EnrichedAction(
                intent_type='mutate_calendar_event',
                parameters=mutate_params,
                original_input=pending.get('original_input'),
            )

        msg = build_crud_confirmation_message(enriched, recon)
        self.store_pending_crud_action(user, {
            'intent_type': enriched.intent_type,
            'parameters': enriched.parameters,
            'original_intent': original_intent,
            'original_input': pending.get('original_input'),
            'recon_decision': recon.decision.value,
            'recon_context': recon.matched_object,
            'confirmation_message': msg,
        })

        logger.info(
            "[DISAMBIGUATE] Selected event #%s '%s' -> %s, user=%s",
            selected['id'], selected['title'], recon.decision.value, user.id,
        )

        return ActionResult(
            success=False,
            message=msg,
            error='crud_confirmation_required',
            action_type=enriched.intent_type,
        )

    def handle_crud_confirmation(self, user, response: str) -> Optional[ActionResult]:
        """
        Handle user's response to a CRUD confirmation request.

        Uses deterministic command parsing — supports both legacy
        CONFIRM/CANCEL/EDIT text AND structured A/B/C option keys.
        Includes idempotency protection, expiry handling, decision memory
        recording, and PendingAction DB status updates.

        Args:
            user: The User model instance
            response: User's response text

        Returns:
            ActionResult if handled, None if response unrecognized
        """
        pending = self.get_pending_crud_action(user)
        if not pending:
            # Expired — explicit message
            return ActionResult(
                success=False,
                message=(
                    "That pending action has expired. "
                    "Please tell me what you'd like to do again."
                ),
                action_type='expired',
            )

        if pending.get('executed'):
            # Already executed — idempotent no-op
            self.clear_pending_crud_action(user)
            return ActionResult(
                success=True,
                message="That action was already completed.",
                action_type='idempotent_skip',
            )

        from apps.core.ai_orchestrator.crud_confirmation import (
            parse_confirmation_response,
        )

        # Pass stored options so A/B/C letter keys are recognized
        options = pending.get('options', [])
        decision = parse_confirmation_response(response, options=options or None)

        # Helper to record decision in decision_memory and update DB
        def _record_and_resolve(action_str, db_status):
            try:
                from apps.core.ai_orchestrator.decision_memory import (
                    record_decision, compute_context_key,
                )
                ctx_key = compute_context_key(
                    pending.get('intent_type', ''),
                    pending.get('parameters', {}),
                )
                record_decision(user, pending.get('intent_type', ''), ctx_key, action_str)
            except Exception as e:
                logger.error("[DECISION_MEMORY] Record failed: %s", e, exc_info=True)
            try:
                from apps.core.ai_governance.models import PendingAction as PA
                pa = PA.objects.filter(id=pending.get('action_id')).first()
                if pa:
                    pa.resolve(action=action_str, status=db_status)
            except Exception as e:
                logger.error("[PENDING_ACTION] DB resolve failed: %s", e, exc_info=True)

        if decision == 'confirm':
            # Mark executed BEFORE execution (prevents double-fire)
            pending['executed'] = True
            cache.set(f"pending_crud_{user.id}", pending, 300)

            # Execute through full pipeline (safety → handler → intelligence)
            try:
                from apps.core.ai_orchestrator.action_router import EnrichedAction
                from apps.core.ai_orchestrator.execution_engine import execute_action

                enriched = EnrichedAction(
                    intent_type=pending['intent_type'],
                    parameters=pending['parameters'],
                    original_input=pending.get('original_input'),
                )
                self.clear_pending_crud_action(user)
                result = execute_action(user, enriched)
                _record_and_resolve('confirm', 'confirmed')
                logger.info(
                    "[CRUD_GATE] Confirmed: %s action_id=%s user=%s",
                    pending.get('intent_type', 'unknown'),
                    pending.get('action_id', 'unknown'), user.id,
                )
                return result
            except Exception as e:
                logger.error(
                    "[CRUD_GATE] Execution after confirm failed: %s", e,
                    exc_info=True,
                )
                self.clear_pending_crud_action(user)
                return ActionResult(
                    success=False,
                    message="Something went wrong executing that action. Please try again.",
                    error='execution_error',
                    action_type=pending.get('intent_type', 'unknown'),
                )

        elif decision == 'cancel':
            self.clear_pending_crud_action(user)
            _record_and_resolve('cancel', 'cancelled')
            logger.info(
                "[CRUD_GATE] Cancelled: %s action_id=%s user=%s",
                pending.get('intent_type', 'unknown'),
                pending.get('action_id', 'unknown'), user.id,
            )
            return ActionResult(
                success=True,
                message="Action cancelled.",
                action_type='cancelled',
            )

        elif decision == 'edit':
            self.clear_pending_crud_action(user)
            _record_and_resolve('edit', 'edited')
            logger.info(
                "[CRUD_GATE] Edit requested: %s action_id=%s user=%s",
                pending.get('intent_type', 'unknown'),
                pending.get('action_id', 'unknown'), user.id,
            )
            return ActionResult(
                success=True,
                message="No problem. Tell me what you'd like to do instead.",
                action_type='cancelled',
            )

        # Unrecognized response — escape confirmation loop.
        # Cancel the pending action and let the message route back through
        # normal AI interpretation so the user isn't trapped.
        self.clear_pending_crud_action(user)
        logger.info(
            "[CRUD_GATE] Escape: unrecognized response '%s' for %s user=%s — "
            "cancelling pending action and routing to AI",
            response[:50], pending.get('intent_type', 'unknown'), user.id,
        )
        return ActionResult(
            success=False,
            message=None,  # Caller should route to normal AI pipeline
            error='confirmation_escaped',
            action_type='confirmation_escaped',
        )

    # ── Pending Clarification (entity disambiguation) ──────────────

    def store_pending_clarification(
        self, user, intent_type: str, parameters: dict,
        candidates: list, ttl: int = 300,
    ):
        """
        Store a pending clarification (multiple-matches disambiguation).

        Args:
            user: The User model instance
            intent_type: e.g., 'mutate_task', 'complete_task'
            parameters: Original intent parameters (action, task_query, etc.)
            candidates: List of dicts [{'id': int, 'title': str}, ...]
            ttl: Time to live in seconds (default 5 minutes)
        """
        cache_key = f"pending_clarification_{user.id}"
        cache.set(cache_key, {
            'intent_type': intent_type,
            'parameters': parameters,
            'candidates': candidates,
            'timestamp': timezone.now().isoformat(),
        }, ttl)

    def get_pending_clarification(self, user) -> Optional[Dict]:
        """Retrieve a pending clarification from cache, or None."""
        cache_key = f"pending_clarification_{user.id}"
        return cache.get(cache_key)

    def clear_pending_clarification(self, user):
        """Clear any pending clarification for a user."""
        cache_key = f"pending_clarification_{user.id}"
        cache.delete(cache_key)

    def resolve_clarification(self, user, response: str) -> Optional[ActionResult]:
        """
        Try to resolve a pending clarification from the user's response.

        Matching strategy (against stored candidate titles):
        1. Number selection: "1", "#1", "the first one", "first"
        2. Exact case-insensitive match
        3. Prefix match
        4. Substring match

        Returns:
            ActionResult if resolved and executed, or None if no match.
        """
        pending = self.get_pending_clarification(user)
        if not pending:
            return None

        candidates = pending['candidates']
        response_lower = response.strip().lower()

        # ── Number selection ──
        ordinals = {
            'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
            'the first one': 1, 'the second one': 2, 'the third one': 3,
            'the fourth one': 4, 'the fifth one': 5,
        }
        number = ordinals.get(response_lower)
        if number is None:
            # Try numeric: "1", "#1", "#2"
            cleaned = response_lower.lstrip('#').strip()
            if cleaned.isdigit():
                number = int(cleaned)

        if number and 1 <= number <= len(candidates):
            matched = candidates[number - 1]
        else:
            matched = None

            # ── Exact match ──
            for c in candidates:
                if c['title'].lower() == response_lower:
                    matched = c
                    break

            # ── Prefix match ──
            if not matched:
                for c in candidates:
                    if c['title'].lower().startswith(response_lower):
                        matched = c
                        break

            # ── Substring match ──
            if not matched:
                for c in candidates:
                    if response_lower in c['title'].lower():
                        matched = c
                        break

        if matched:
            self.clear_pending_clarification(user)
            params = dict(pending['parameters'])
            params['_resolved_id'] = matched['id']
            intent_result = IntentResult(
                intent_type=pending['intent_type'],
                parameters=params,
            )
            logger.info(
                "[CLARIFICATION] Resolved '%s' → task %s (%s) for user %s",
                response, matched['id'], matched['title'], user.id,
            )
            return self.execute_intent(intent_result, user)

        # No match found
        return None

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
