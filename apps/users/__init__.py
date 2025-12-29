"""
Whole Life Journey - Users Application Package

Project: Whole Life Journey
Path: apps/users/__init__.py
Purpose: Custom user model, authentication, and user preference management

Description:
    The users app implements custom email-based authentication (no username),
    user preferences/settings, terms acceptance tracking, onboarding wizard,
    and WebAuthn biometric login support.

Key Responsibilities:
    - Custom User model with email as the unique identifier
    - UserPreferences: Theme, module toggles, AI settings, timezone
    - TermsAcceptance: Version-tracked terms of service acceptance
    - WebAuthnCredential: Biometric login (Face ID/Touch ID) support
    - Onboarding wizard for new user setup
    - Profile and preferences management views

Package Contents:
    - models.py: User, UserPreferences, TermsAcceptance, WebAuthnCredential
    - views.py: Profile, preferences, onboarding, biometric views
    - forms.py: ProfileForm, PreferencesForm
    - middleware.py: Terms acceptance and onboarding enforcement
    - signals.py: Auto-create UserPreferences on user creation
    - urls.py: URL routing for user-related pages

Dependencies:
    - django.contrib.auth for authentication base classes
    - django-allauth for authentication flow
    - apps.ai.models for CoachingStyle preferences

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

default_app_config = "apps.users.apps.UsersConfig"
