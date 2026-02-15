"""
Learning Pipeline — Store knowledge from interactions for future use.

After each successful action, records what was learned so the AI
can resolve similar inputs automatically next time.
"""

import logging

from apps.core.ai_memory.learning_engine import log_clarification, store_learned_mapping

logger = logging.getLogger(__name__)


def learn_from_interaction(user, user_input, action_result, enriched_action=None,
                            clarification_data=None):
    """
    Store learned knowledge from a completed interaction.

    Called after successful action execution.

    Args:
        user: Django user instance.
        user_input: Original user message.
        action_result: ActionResult from execution.
        enriched_action: Optional EnrichedAction with resolution details.
        clarification_data: Optional dict if a clarification exchange occurred:
            {
                "question": "Which scripture?",
                "response": "John 3:16",
                "phrase": "the scripture",
                "meaning_type": "scripture",
                "meaning_identifier": "John 3:16"
            }
    """
    try:
        # If a clarification was resolved, store the mapping
        if clarification_data:
            mapping = store_learned_mapping(
                user=user,
                phrase=clarification_data["phrase"],
                meaning_type=clarification_data["meaning_type"],
                meaning_identifier=clarification_data["meaning_identifier"],
            )

            log_clarification(
                user=user,
                original_input=user_input,
                question=clarification_data.get("question", ""),
                response=clarification_data.get("response", ""),
                resolved=clarification_data["meaning_identifier"],
                mapping=mapping,
            )

            logger.info(
                f"Learned mapping for user {user.id}: "
                f"'{clarification_data['phrase']}' → "
                f"{clarification_data['meaning_type']}:{clarification_data['meaning_identifier']}"
            )

    except Exception as e:
        # Learning failures must never break the main flow
        logger.error(f"Learning pipeline error: {e}", exc_info=True)
