"""
Users URLs - Profile, preferences, and terms acceptance.
"""

from django.urls import path

from . import views

app_name = "users"

urlpatterns = [
    # Profile
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("profile/edit/", views.ProfileEditView.as_view(), name="profile_edit"),
    
    # Preferences
    path("preferences/", views.PreferencesView.as_view(), name="preferences"),
    path("preferences/theme/", views.ThemeSelectionView.as_view(), name="theme_selection"),
    
    # Terms acceptance
    path("accept-terms/", views.AcceptTermsView.as_view(), name="accept_terms"),
    
    # Onboarding
    path("onboarding/", views.OnboardingView.as_view(), name="onboarding"),
    path("onboarding/complete/", views.CompleteOnboardingView.as_view(), name="complete_onboarding"),
]
