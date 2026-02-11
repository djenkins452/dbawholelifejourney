"""
Whole Life Journey - User URL Configuration

Project: Whole Life Journey
Path: apps/users/urls.py
Purpose: URL routing for user profile, preferences, and authentication features

Description:
    Defines URL patterns for user-related views including profile editing,
    preferences management, terms acceptance, onboarding wizard, and
    WebAuthn biometric authentication endpoints.

URL Patterns:
    - /profile/            : View user profile
    - /profile/edit/       : Edit profile form
    - /preferences/        : User preferences page
    - /accept-terms/       : Terms of service acceptance
    - /onboarding/*        : Onboarding wizard steps
    - /biometric/*         : WebAuthn biometric login endpoints

Note:
    This app is mounted at /user/ (singular) in the main URL configuration.

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
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
    path("preferences/toggle/", views.PreferenceToggleView.as_view(), name="preference_toggle"),

    # Terms acceptance
    path("accept-terms/", views.AcceptTermsView.as_view(), name="accept_terms"),

    # Onboarding (legacy redirect)
    path("onboarding/", views.OnboardingView.as_view(), name="onboarding"),
    path("onboarding/complete/", views.CompleteOnboardingView.as_view(), name="complete_onboarding"),

    # Onboarding Wizard (new step-by-step flow)
    path("onboarding/start/", views.OnboardingWizardView.as_view(), name="onboarding_wizard"),
    path("onboarding/step/<str:step>/", views.OnboardingWizardView.as_view(), name="onboarding_wizard_step"),

    # API endpoints
    path("api/dismiss-intro-banner/", views.DismissIntroBannerView.as_view(), name="dismiss_intro_banner"),
    path("api/ai-profile-nudge/", views.AIProfileNudgeActionView.as_view(), name="ai_profile_nudge"),
    path("api/ai-profile-builder/", views.AIProfileBuilderView.as_view(), name="ai_profile_builder"),
    path("api/sub-feature-toggle/", views.SubFeatureToggleView.as_view(), name="sub_feature_toggle"),
    path("api/sub-features/", views.SubFeaturesBulkView.as_view(), name="sub_features"),
    path("api/module-order/", views.ModuleOrderView.as_view(), name="module_order"),

    # Biometric / WebAuthn Login
    path("biometric/check/", views.BiometricCheckView.as_view(), name="biometric_check"),
    path("biometric/credentials/", views.BiometricCredentialsView.as_view(), name="biometric_credentials"),
    path("biometric/register/begin/", views.BiometricRegisterBeginView.as_view(), name="biometric_register_begin"),
    path("biometric/register/complete/", views.BiometricRegisterCompleteView.as_view(), name="biometric_register_complete"),
    path("biometric/login/begin/", views.BiometricLoginBeginView.as_view(), name="biometric_login_begin"),
    path("biometric/login/complete/", views.BiometricLoginCompleteView.as_view(), name="biometric_login_complete"),
    path("biometric/delete/<int:credential_id>/", views.BiometricDeleteCredentialView.as_view(), name="biometric_delete"),

    # GDPR Data Export (CISO Review 2026-01-12)
    path("data-export/", views.DataExportView.as_view(), name="data_export"),
    path("data-export/download/", views.DataExportDownloadView.as_view(), name="data_export_download"),

    # Password confirmation for sensitive operations (CISO Review 2026-01-12)
    path("confirm-password/", views.ConfirmPasswordView.as_view(), name="confirm_password"),

    # MFA Enforcement
    path("mfa-required/", views.MFARequiredView.as_view(), name="mfa_required"),

    # MFA Email Code endpoints
    path("mfa/email/send/", views.MFAEmailCodeSendView.as_view(), name="mfa_email_send"),
    path("mfa/email/verify/", views.MFAEmailCodeVerifyView.as_view(), name="mfa_email_verify"),
    path("mfa/email/login-send/", views.MFAEmailCodeLoginSendView.as_view(), name="mfa_email_login_send"),
    path("mfa/email/login-verify/", views.MFAEmailCodeLoginVerifyView.as_view(), name="mfa_email_login_verify"),

    # Account deletion (GDPR/App Store compliance)
    path("delete-account/", views.DeleteAccountView.as_view(), name="delete_account"),
    path("export-data/", views.ExportAccountDataView.as_view(), name="export_data"),

    # Quick Links (external links)
    path("api/quick-links/", views.QuickLinkCreateView.as_view(), name="quick_link_create"),
    path("api/quick-links/<int:link_id>/delete/", views.QuickLinkDeleteView.as_view(), name="quick_link_delete"),
]
