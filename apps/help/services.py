"""
Help Chat Service - Handles searching articles and generating responses.

The WLJ Assistant searches internal help documentation to answer user questions,
adapting its tone based on the user's selected coaching style.

Also handles personal data queries by integrating with the assistant module
to provide context-aware responses about user's wellness data.
"""
import logging
import re
from django.db.models import Q
from django.core.cache import cache

from apps.ai.models import CoachingStyle
from assistant import process_assistant_message
from .models import HelpArticle, HelpCategory

logger = logging.getLogger(__name__)


# Base system prompt for personal data query responses
PERSONAL_DATA_SYSTEM_PROMPT = """You are the WLJ Assistant, a helpful assistant integrated into Whole Life Journey,
a personal wellness and journaling application. Your role is to help users understand
and reflect on their personal wellness data.

When responding to questions about personal data:
- Be specific to their actual data - never make up numbers or be generic
- Help users see patterns and insights in their data
- Be supportive and encouraging while being honest
- Keep responses concise but helpful (2-4 sentences)
- Never provide medical advice - only observations about their data

IMPORTANT: You are NOT a medical professional. For health data, provide observations
and encourage the user to discuss concerns with their healthcare provider."""


class HelpChatService:
    """
    Service for the WLJ Assistant chat bot.

    Searches help articles and generates responses that match
    the user's preferred coaching style tone.

    Also handles personal data queries by integrating with the
    assistant module to provide AI-generated responses with
    personal context.
    """

    # Tone templates for different coaching styles
    TONE_TEMPLATES = {
        'supportive': {
            'greeting': "I am your WLJ assistant, what can I help you with today?",
            'found_single': "Great question! Here's what I found that should help:",
            'found_multiple': "I found some helpful information for you:",
            'not_found': "I couldn't find a specific answer to that, but don't worry - here are some related topics that might help:",
            'no_results': "I'm sorry, I couldn't find any information on that topic. Would you like to try asking in a different way, or would you prefer to contact support?",
            'follow_up': "Is there anything else I can help you with?",
            'closing': "I hope this helps! Feel free to ask if you have any more questions.",
        },
        'direct_coach': {
            'greeting': "I am your WLJ assistant, what can I help you with today?",
            'found_single': "Here's what you need to know:",
            'found_multiple': "Found it. Here's the information:",
            'not_found': "No exact match. Check these related topics:",
            'no_results': "No information found on that. Rephrase your question or contact support.",
            'follow_up': "What else do you need?",
            'closing': "Done. Next question?",
        },
        'gentle_guide': {
            'greeting': "I am your WLJ assistant, what can I help you with today?",
            'found_single': "Let me share what I found for you:",
            'found_multiple': "I've gathered some information that might be helpful:",
            'not_found': "I wasn't able to find exactly what you're looking for, but perhaps one of these might help:",
            'no_results': "I'm having trouble finding that information. Maybe we could try approaching this from a different angle?",
            'follow_up': "Would you like to explore anything else?",
            'closing': "Take your time with this information. I'm here if you need more help.",
        },
        'wise_mentor': {
            'greeting': "I am your WLJ assistant, what can I help you with today?",
            'found_single': "Here's some wisdom on that topic:",
            'found_multiple': "Let me share what I've gathered on this:",
            'not_found': "That's not something I have specific guidance on, but consider exploring these related areas:",
            'no_results': "Sometimes the best answers come from asking different questions. Could you tell me more about what you're trying to accomplish?",
            'follow_up': "What other questions are on your mind?",
            'closing': "Reflect on this and come back whenever you need guidance.",
        },
        'cheerful_friend': {
            'greeting': "I am your WLJ assistant, what can I help you with today?",
            'found_single': "Awesome question! Here's what I found:",
            'found_multiple': "Oh, I know just what you need! Check this out:",
            'not_found': "Hmm, couldn't find an exact match, but how about these?",
            'no_results': "Oops! I'm coming up empty on that one. Want to try asking differently?",
            'follow_up': "Anything else you'd like to know?",
            'closing': "Happy to help anytime!",
        },
        'calm_companion': {
            'greeting': "I am your WLJ assistant, what can I help you with today?",
            'found_single': "Here's some helpful information:",
            'found_multiple': "I've found some relevant information for you:",
            'not_found': "I don't have an exact answer, but these topics may be useful:",
            'no_results': "I wasn't able to find that. Let's try a different approach when you're ready.",
            'follow_up': "Feel free to ask anything else.",
            'closing': "I'm here whenever you need assistance.",
        },
        'accountability_partner': {
            'greeting': "I am your WLJ assistant, what can I help you with today?",
            'found_single': "Let's get you sorted. Here's what you need:",
            'found_multiple': "Got the info you need right here:",
            'not_found': "Couldn't find that specific info, but these might move you forward:",
            'no_results': "Nothing on that yet. Let's reframe and try again - what's the core issue?",
            'follow_up': "What's the next thing you need to tackle?",
            'closing': "Now go put this into action!",
        },
    }

    # Default tone if coaching style not found
    DEFAULT_STYLE = 'supportive'

    def __init__(self, user):
        """
        Initialize the service for a specific user.

        Args:
            user: The User instance
        """
        self.user = user
        self.coaching_style_key = self._get_user_coaching_style()
        self.tone = self._get_tone_template()

    def _get_user_coaching_style(self):
        """Get the user's coaching style preference."""
        try:
            prefs = self.user.preferences
            return prefs.ai_coaching_style or self.DEFAULT_STYLE
        except Exception:
            return self.DEFAULT_STYLE

    def _get_tone_template(self):
        """Get the tone template for the user's coaching style."""
        return self.TONE_TEMPLATES.get(
            self.coaching_style_key,
            self.TONE_TEMPLATES[self.DEFAULT_STYLE]
        )

    def get_welcome_message(self):
        """Get the welcome message for the chat."""
        return self.tone['greeting']

    # Synonym mapping for common search terms
    SEARCH_SYNONYMS = {
        'account': ['settings', 'preferences', 'profile'],
        'update': ['change', 'edit', 'modify'],
        'my': ['profile', 'settings', 'preferences'],
        'password': ['login', 'security', 'credentials'],
        'log': ['journal', 'entry', 'record'],
        'track': ['log', 'record', 'monitor'],
        'workout': ['exercise', 'fitness', 'training'],
        'food': ['nutrition', 'meal', 'diet', 'calories'],
        'weight': ['body', 'mass', 'scale'],
        'prayer': ['faith', 'spiritual'],
        'bible': ['scripture', 'faith', 'verse'],
    }

    def _expand_query_with_synonyms(self, words):
        """Expand search words with synonyms for better matching."""
        expanded = set(words)
        for word in words:
            if word in self.SEARCH_SYNONYMS:
                expanded.update(self.SEARCH_SYNONYMS[word])
        return list(expanded)

    def search_articles(self, query, module=None, limit=5):
        """
        Search help articles for relevant content.

        Args:
            query: The user's search query
            module: Optional module to prioritize (e.g., 'journal', 'health')
            limit: Maximum number of results

        Returns:
            List of matching HelpArticle instances
        """
        if not query or len(query.strip()) < 2:
            return []

        query = query.strip().lower()
        words = query.split()

        # Expand with synonyms for better matching
        words = self._expand_query_with_synonyms(words)

        # Build search query
        q_filter = Q()

        # Search in title
        for word in words:
            q_filter |= Q(title__icontains=word)

        # Search in summary
        for word in words:
            q_filter |= Q(summary__icontains=word)

        # Search in content
        for word in words:
            q_filter |= Q(content__icontains=word)

        # Search in keywords
        for word in words:
            q_filter |= Q(keywords__icontains=word)

        # Get matching articles
        articles = HelpArticle.objects.filter(
            is_active=True
        ).filter(q_filter).select_related('category')

        # Score and sort results
        scored_articles = []
        for article in articles:
            score = self._score_article(article, words, module)
            scored_articles.append((score, article))

        # Sort by score (highest first)
        scored_articles.sort(key=lambda x: x[0], reverse=True)

        # Return top results
        return [article for score, article in scored_articles[:limit]]

    def _score_article(self, article, query_words, priority_module=None):
        """
        Score an article based on relevance to query.

        Args:
            article: HelpArticle instance
            query_words: List of search words
            priority_module: Module to boost in results

        Returns:
            Integer score (higher = more relevant)
        """
        score = 0
        title_lower = article.title.lower()
        summary_lower = article.summary.lower()
        keywords = article.keywords_list

        for word in query_words:
            # Title matches are most valuable
            if word in title_lower:
                score += 10

            # Keyword matches are very valuable
            if word in keywords:
                score += 8

            # Summary matches
            if word in summary_lower:
                score += 5

            # Content matches (less weight)
            if word in article.content.lower():
                score += 2

        # Boost if module matches
        if priority_module and article.module == priority_module:
            score += 15
        elif article.module == 'general':
            score += 3  # Small boost for general articles

        return score

    def generate_response(self, query, context_module=None):
        """
        Generate a response to the user's query.

        Checks in order:
        1. Navigation queries ("where do I...", "how do I get to...")
        2. Personal data queries (weight, journal, medication, food, mood)
        3. Help article search

        Args:
            query: The user's question
            context_module: The module the user is currently viewing

        Returns:
            dict with 'message' (str) and 'articles' (list of HelpArticle)
        """
        # Step 1: Check if this is a navigation query
        navigation_response = self._try_navigation_response(query)
        if navigation_response:
            return navigation_response

        # Step 2: Check if this is a personal data query
        personal_data_response = self._try_personal_data_response(query)
        if personal_data_response:
            return personal_data_response

        # Step 3: Fall back to help article search
        articles = self.search_articles(query, module=context_module)

        if not articles:
            # No results found
            return {
                'message': self.tone['no_results'],
                'articles': []
            }

        if len(articles) == 1:
            # Single result - provide detailed response
            article = articles[0]
            message = self._format_single_response(article)
            return {
                'message': message,
                'articles': articles
            }

        # Multiple results - provide overview
        message = self._format_multiple_response(articles)
        return {
            'message': message,
            'articles': articles
        }

    def _try_navigation_response(self, query):
        """
        Try to answer a navigation query using TeachingToolService.

        Handles questions like "where do I log my weight?" or
        "how do I get to my goals?" with a direct link.

        Args:
            query: The user's question

        Returns:
            dict with 'message' and 'articles' if navigation query found,
            None if not a navigation query
        """
        # Check if query looks like a navigation question
        # Be specific - only catch "where" questions and explicit navigation requests
        # Don't catch "how do I use X" which should go to help articles
        query_lower = query.lower().strip()
        navigation_indicators = [
            'where do i', 'where can i', 'where is', 'where are',
            'how do i get to', 'how do i find', 'how do i access',
            'how do i go to', 'how do i navigate',
            'take me to', 'go to the', 'navigate to',
            'show me the', 'open the', 'where\'s the', 'where\'s my',
            'link to', 'path to', 'url for',
        ]

        is_navigation_query = any(
            query_lower.startswith(indicator) or f' {indicator}' in f' {query_lower}'
            for indicator in navigation_indicators
        )

        if not is_navigation_query:
            return None

        try:
            teaching_service = TeachingToolService()
            result = teaching_service.search(query)

            if result['found'] and result['destination']:
                dest = result['destination']
                # Format a friendly response with the link
                message = (
                    f"{result['message']}\n\n"
                    f"**[Go to {dest['name']}]({dest['url']})**"
                )

                # Add suggestions if any
                if result.get('suggestions'):
                    suggestions_text = "\n".join([
                        f"- [{s['name']}]({s['url']})"
                        for s in result['suggestions'][:3]
                    ])
                    if suggestions_text:
                        message += f"\n\nYou might also be looking for:\n{suggestions_text}"

                return {
                    'message': message,
                    'articles': [],
                    'navigation': dest,  # Include destination for potential UI use
                }

            # Weak match - return suggestions but don't block other handlers
            if result.get('suggestions'):
                suggestions_text = "\n".join([
                    f"- [{s['name']}]({s['url']})"
                    for s in result['suggestions'][:5]
                ])
                message = (
                    f"I'm not sure exactly where that is, but here are some pages that might help:\n\n"
                    f"{suggestions_text}"
                )
                return {
                    'message': message,
                    'articles': [],
                }

            return None

        except Exception as e:
            logger.error(f"Error in navigation response: {e}")
            return None

    def _try_personal_data_response(self, query):
        """
        Try to generate a response for a personal data query.

        Uses the assistant module to detect personal data queries and
        generate AI responses with the user's actual data context.

        Args:
            query: The user's question

        Returns:
            dict with 'message' and 'articles' if personal data query,
            None if not a personal data query or if generation fails
        """
        # Skip personal data check for "how to use" questions - these are help queries
        query_lower = query.lower().strip()
        help_question_indicators = [
            'how do i use', 'how to use', 'how does', 'what is',
            'explain', 'help me understand', 'tutorial', 'guide',
        ]
        if any(ind in query_lower for ind in help_question_indicators):
            return None

        try:
            # Process the message to detect personal data intent
            result = process_assistant_message(
                user=self.user,
                message=query,
                base_system_prompt=PERSONAL_DATA_SYSTEM_PROMPT,
            )

            # If not a personal query, return None to fall back to help search
            if not result['is_personal_query']:
                return None

            # If it's a personal query but no data found, provide a helpful message
            if not result['has_data']:
                data_types = ', '.join(result['data_types']) if result['data_types'] else 'data'
                message = (
                    f"I'd love to help you with your {data_types} question, but "
                    f"I don't have any {data_types} data recorded yet. "
                    f"Once you start logging, I'll be able to answer questions about your history!"
                )
                return {
                    'message': message,
                    'articles': []
                }

            # Generate AI response with personal context
            ai_response = self._generate_ai_response(query, result['system_prompt'])
            if ai_response:
                return {
                    'message': ai_response,
                    'articles': []
                }

            # AI generation failed, fall back to help search
            logger.warning("AI generation failed for personal data query, falling back to help search")
            return None

        except Exception as e:
            logger.error(f"Error processing personal data query: {e}")
            return None

    def _generate_ai_response(self, query, system_prompt):
        """
        Generate an AI response using OpenAI.

        Args:
            query: The user's question
            system_prompt: System prompt with personal data context

        Returns:
            str response or None if generation fails
        """
        try:
            from apps.ai.services import AIService

            # Check if AI service is available
            ai_service = AIService()
            if not ai_service.is_available:
                logger.warning("AI service not available for personal data response")
                return None

            # Add coaching style context to the system prompt
            coaching_style_prompt = self._get_coaching_style_instructions()
            full_system_prompt = system_prompt + "\n\n" + coaching_style_prompt

            # Generate response
            response = ai_service._call_api(
                system_prompt=full_system_prompt,
                user_prompt=query,
                max_tokens=200
            )

            return response

        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            return None

    def _get_coaching_style_instructions(self):
        """Get coaching style instructions for AI prompt."""
        style_instructions = {
            'supportive': "Be warm, encouraging, and balanced - like a trusted friend.",
            'direct_coach': "Be direct and to-the-point. Give clear, concise answers.",
            'gentle_guide': "Be gentle and patient. Guide the user thoughtfully.",
            'wise_mentor': "Share wisdom with perspective. Help them see the bigger picture.",
            'cheerful_friend': "Be upbeat and positive! Use friendly, enthusiastic language.",
            'calm_companion': "Be calm and steady. Provide a peaceful, reassuring presence.",
            'accountability_partner': "Be supportive but focused on action and progress.",
        }
        instruction = style_instructions.get(
            self.coaching_style_key,
            style_instructions['supportive']
        )
        return f"COACHING STYLE: {instruction}"

    def _format_single_response(self, article):
        """Format a response for a single matching article."""
        intro = self.tone['found_single']

        # Use the summary for a concise response
        response = f"{intro}\n\n**{article.title}**\n{article.summary}"

        # Add a snippet from the content if it's helpful
        # Extract first paragraph that isn't just a header
        content_lines = article.content.split('\n')
        for line in content_lines:
            line = line.strip()
            if line and not line.startswith('#') and len(line) > 50:
                response += f"\n\n{line[:300]}..."
                break

        # Add link to full article
        response += f"\n\n[Read more about {article.title}](/help/article/{article.slug}/)"

        # Check for related articles
        related = article.related_articles.filter(is_active=True)[:2]
        if related:
            response += "\n\n**Related:**"
            for rel in related:
                response += f"\n- [{rel.title}](/help/article/{rel.slug}/)"

        return response

    def _format_multiple_response(self, articles):
        """Format a response for multiple matching articles."""
        intro = self.tone['found_multiple']

        response = f"{intro}\n"

        for i, article in enumerate(articles[:3], 1):
            response += f"\n**{i}. {article.title}**\n{article.summary}\n"

        if len(articles) > 3:
            response += f"\n*...and {len(articles) - 3} more results.*"

        response += f"\n\n{self.tone['follow_up']}"

        return response

    def get_suggestions_for_module(self, module):
        """
        Get suggested help topics for a specific module.

        Args:
            module: The module name (e.g., 'journal', 'health')

        Returns:
            List of HelpArticle instances
        """
        articles = HelpArticle.objects.filter(
            is_active=True,
            module=module
        ).select_related('category').order_by('sort_order', 'title')[:5]

        # Also include some general articles
        general = HelpArticle.objects.filter(
            is_active=True,
            module='general'
        ).select_related('category').order_by('sort_order', 'title')[:2]

        return list(articles) + list(general)

    def get_all_categories(self):
        """Get all active help categories with their articles."""
        return HelpCategory.objects.filter(
            is_active=True
        ).prefetch_related(
            'articles'
        ).order_by('sort_order', 'name')

    def get_closing_message(self):
        """Get a closing message when user ends the chat."""
        return self.tone['closing']


# =============================================================================
# TEACHING TOOL SERVICE (Navigation Intent Matching)
# =============================================================================


class TeachingToolService:
    """
    Service for matching user questions to app destinations.

    Uses keyword/phrase matching to find the best destination for
    questions like "Where do I log my weight?" or "How do I talk to the AI coach?"
    """

    # Words to ignore when matching (common filler words)
    STOP_WORDS = {
        'a', 'an', 'the', 'to', 'do', 'i', 'my', 'me', 'is', 'are', 'can',
        'how', 'where', 'what', 'when', 'why', 'which', 'who',
        'in', 'on', 'at', 'for', 'of', 'with', 'about', 'into',
        'go', 'get', 'find', 'see', 'view', 'open', 'access', 'use',
    }

    # Response templates
    RESPONSE_FOUND = "You can {action} under **{path}**."
    RESPONSE_NOT_FOUND = "I'm not sure about that, but here are some things I can help you find:"
    RESPONSE_NO_DESTINATIONS = "I don't have any navigation suggestions yet. Please try the Help Center for more information."

    def __init__(self):
        """Initialize the service."""
        self.destinations = None

    def _load_destinations(self):
        """Load destinations from database (cached)."""
        if self.destinations is None:
            from .models import TeachingDestination
            self.destinations = TeachingDestination.get_all_active()
        return self.destinations

    def search(self, query, limit=5):
        """
        Search for destinations matching the user's query.

        Args:
            query: Natural language question from user
            limit: Maximum results to return

        Returns:
            dict with:
                - found: bool - whether a match was found
                - message: str - response text
                - destination: dict or None - best match
                - suggestions: list - alternative destinations
        """
        if not query or len(query.strip()) < 2:
            return self._no_match_response()

        destinations = self._load_destinations()
        if not destinations:
            return {
                'found': False,
                'message': self.RESPONSE_NO_DESTINATIONS,
                'destination': None,
                'suggestions': [],
            }

        # Normalize and tokenize query
        query_lower = query.strip().lower()
        query_words = self._extract_words(query_lower)

        # Score all destinations
        scored = []
        for dest in destinations:
            score = self._score_destination(dest, query_lower, query_words)
            if score > 0:
                scored.append((score, dest))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        if not scored:
            return self._no_match_response(destinations[:limit])

        # Best match
        best_score, best_dest = scored[0]

        # Build response
        if best_score >= 10:
            # Strong match - confident response
            action = best_dest.explanation or f"access {best_dest.name}"
            # Make action lowercase and remove trailing period
            action = action.rstrip('.').lower()
            if action.startswith('you can '):
                action = action[8:]

            message = self.RESPONSE_FOUND.format(
                action=action,
                path=best_dest.path_description
            )

            # Get suggestions excluding the best match
            suggestions = [
                self._destination_to_dict(dest)
                for score, dest in scored[1:limit]
                if score >= 5
            ]

            return {
                'found': True,
                'message': message,
                'destination': self._destination_to_dict(best_dest),
                'suggestions': suggestions,
            }
        else:
            # Weak match - show as suggestions
            return self._no_match_response([dest for score, dest in scored[:limit]])

    def _extract_words(self, text):
        """Extract meaningful words from text, excluding stop words."""
        # Remove punctuation and split
        words = re.sub(r'[^\w\s]', ' ', text).split()
        # Filter out stop words and short words
        return [w for w in words if w not in self.STOP_WORDS and len(w) > 1]

    def _score_destination(self, destination, query_lower, query_words):
        """
        Score how well a destination matches the query.

        Args:
            destination: TeachingDestination instance
            query_lower: Lowercase query string
            query_words: List of extracted query words

        Returns:
            Integer score (higher = better match)
        """
        score = 0
        keywords = destination.keywords_list

        # Check for exact phrase matches in keywords (highest value)
        for keyword in keywords:
            if keyword in query_lower:
                # Longer phrase matches score higher
                score += 10 + len(keyword.split())

        # Check for word matches
        for word in query_words:
            # Word in any keyword
            for keyword in keywords:
                if word in keyword or keyword in word:
                    score += 3

            # Word in name
            if word in destination.name.lower():
                score += 5

            # Word in path description
            if word in destination.path_description.lower():
                score += 2

            # Word in explanation
            if destination.explanation and word in destination.explanation.lower():
                score += 1

        return score

    def _destination_to_dict(self, dest):
        """Convert destination model to dict for JSON response."""
        return {
            'id': dest.destination_id,
            'name': dest.name,
            'path': dest.path_description,
            'url': dest.url,
            'explanation': dest.explanation,
        }

    def _no_match_response(self, suggestions=None):
        """Build a response when no strong match is found."""
        destinations = self._load_destinations()

        if suggestions is None:
            # Return top destinations by sort order
            suggestions = destinations[:5]

        return {
            'found': False,
            'message': self.RESPONSE_NOT_FOUND,
            'destination': None,
            'suggestions': [self._destination_to_dict(d) for d in suggestions],
        }

    def get_popular_destinations(self, limit=5):
        """Get popular destinations for the fallback display."""
        destinations = self._load_destinations()
        return [self._destination_to_dict(d) for d in destinations[:limit]]
