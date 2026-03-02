from django.urls import path

from . import views

app_name = "meals"

urlpatterns = [
    # Dashboard — Command Center
    path("", views.MealsDashboardView.as_view(), name="dashboard"),
    # Guided Setup Wizard
    path("setup/", views.MealsSetupView.as_view(), name="setup"),
    # Dinner Suggestions
    path("suggestions/", views.DinnerSuggestionsView.as_view(), name="suggestions"),
    # Pantry Intelligence
    path("pantry/", views.PantryView.as_view(), name="pantry"),
    path(
        "pantry/<int:pk>/confirm/",
        views.PantryConfirmView.as_view(),
        name="pantry_confirm",
    ),
    path(
        "pantry/<int:pk>/used/",
        views.PantryMarkUsedView.as_view(),
        name="pantry_mark_used",
    ),
    path(
        "pantry/<int:pk>/update/",
        views.PantryUpdateView.as_view(),
        name="pantry_update",
    ),
    # Meal Plan
    path("plan/", views.MealPlanView.as_view(), name="plan"),
    path("plan/generate/", views.GeneratePlanView.as_view(), name="plan_generate"),
    # Receipts
    path("receipts/", views.ReceiptUploadView.as_view(), name="receipts"),
    path(
        "receipts/<int:pk>/",
        views.ReceiptDetailView.as_view(),
        name="receipt_detail",
    ),
    # Recipe Intelligence Detail
    path(
        "recipe/<int:pk>/",
        views.RecipeIntelligenceDetailView.as_view(),
        name="recipe_detail",
    ),
]
