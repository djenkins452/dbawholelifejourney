"""
Help Chat Service - Handles searching articles and generating responses.

The WLJ Assistant searches internal help documentation to answer user questions,
adapting its tone based on the user's selected coaching style.
"""
import re
from django.db.models import Q
from django.core.cache import cache

from apps.ai.models import CoachingStyle
from .models import HelpArticle, HelpCategory


class HelpChatService:
    """
    Service for the WLJ Assistant chat bot.

    Searches help articles and generates responses that match
    the user's preferred coaching style tone.
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

        Args:
            query: The user's question
            context_module: The module the user is currently viewing

        Returns:
            dict with 'message' (str) and 'articles' (list of HelpArticle)
        """
        # Search for relevant articles
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
