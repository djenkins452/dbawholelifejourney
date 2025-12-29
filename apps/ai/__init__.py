"""
Whole Life Journey - AI Application Package

Project: Whole Life Journey
Path: apps/ai/__init__.py
Purpose: AI coaching, insights, and OpenAI API integration

Description:
    The AI module provides personalized coaching and insights using OpenAI's
    GPT models. It powers dashboard insights, journal analysis, and the
    AI Camera feature for scanning documents, food, and medicines.

Key Responsibilities:
    - AIPromptConfig: Database-driven prompt management for AI interactions
    - CoachingStyle: Personality styles for AI responses
    - AIInsight: Cached AI-generated insights for performance
    - AIUsageLog: Track API usage for monitoring and billing
    - AIService: Main service class for generating AI content
    - DashboardAI: Dashboard-specific AI insight generation

Package Contents:
    - models.py: AIPromptConfig, CoachingStyle, AIInsight, AIUsageLog
    - services.py: AIService for OpenAI API interactions
    - dashboard_ai.py: Dashboard insight generation
    - admin.py: Django admin configuration
    - fixtures/: Default coaching styles and prompt configs

AI Features:
    - Daily dashboard insights based on user data
    - Journal reflection prompts and analysis
    - Celebrations and accountability nudges
    - AI Camera object recognition (via apps.scan)

Security Notes:
    - API key stored in environment variable
    - User must consent to AI data processing
    - All AI requests are logged for auditing

Dependencies:
    - openai: OpenAI Python SDK
    - apps.core.models for user data
    - User's ai_data_consent preference

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""
