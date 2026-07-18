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
    path(
        "pantry/<int:pk>/container/",
        views.PantrySetContainerView.as_view(),
        name="pantry_set_container",
    ),
    path(
        "pantry/barcode/",
        views.PantryBarcodeLookupView.as_view(),
        name="pantry_barcode",
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
    path(
        "receipts/<int:pk>/confirm/",
        views.ReceiptConfirmView.as_view(),
        name="receipt_confirm",
    ),
    path(
        "receipts/<int:pk>/status/",
        views.ReceiptProcessingStatusView.as_view(),
        name="receipt_processing_status",
    ),
    path(
        "receipts/<int:pk>/delete/",
        views.ReceiptDeleteView.as_view(),
        name="receipt_delete",
    ),
    # Recipe Intelligence Detail
    path(
        "recipe/<int:pk>/",
        views.RecipeIntelligenceDetailView.as_view(),
        name="recipe_detail",
    ),
    # Foundation 2 — record a preparation (deduct pantry + leftovers)
    path(
        "recipe/<int:pk>/prepare/",
        views.PrepareRecipeView.as_view(),
        name="prepare_recipe",
    ),
    # Foundation 2 — record consumption of a prepared meal (FoodEntry + reduce leftovers)
    path(
        "preparation/<int:prep_pk>/consume/",
        views.ConsumeMealView.as_view(),
        name="consume_meal",
    ),
    # Foundation 2 — leftovers inventory (list / detail / consume-later / discard)
    path("leftovers/", views.LeftoverListView.as_view(), name="leftovers"),
    path("leftovers/<int:pk>/", views.LeftoverDetailView.as_view(), name="leftover_detail"),
    path("leftovers/<int:pk>/consume/", views.ConsumeLeftoverView.as_view(),
         name="consume_leftover"),
    path("leftovers/<int:pk>/discard/", views.DiscardLeftoverView.as_view(),
         name="discard_leftover"),
    # Phase 12: Pantry Photo Scan
    path("pantry/scan/", views.PantryScanStartView.as_view(), name="pantry_scan"),
    path(
        "pantry/scan/<int:session_id>/confirm/",
        views.PantryScanConfirmView.as_view(),
        name="pantry_scan_confirm",
    ),
    path(
        "pantry/scan/<int:session_id>/status/",
        views.PantryScanStatusView.as_view(),
        name="pantry_scan_status",
    ),
    path(
        "pantry/sessions/",
        views.PantryScanSessionsView.as_view(),
        name="pantry_scan_sessions",
    ),
]
