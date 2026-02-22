from django.urls import path

from . import views

app_name = 'owner_finance'

urlpatterns = [
    path('', views.OverviewView.as_view(), name='overview'),
    path('users/', views.UserCostsView.as_view(), name='users'),
    path('features/', views.FeatureBreakdownView.as_view(), name='features'),
    path('vendors/', views.VendorLedgerView.as_view(), name='vendors'),
]
