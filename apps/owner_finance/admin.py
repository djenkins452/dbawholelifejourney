from django.contrib import admin

from .models import (
    ThirdPartyVendor,
    VendorBillingRecord,
    LLMPriceBook,
    LLMUsageEvent,
    UserSubscriptionSnapshot,
    DailyCostRollup,
    BudgetGuardrail,
)


@admin.register(ThirdPartyVendor)
class ThirdPartyVendorAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'created_at')
    list_filter = ('category',)
    search_fields = ('name',)


@admin.register(VendorBillingRecord)
class VendorBillingRecordAdmin(admin.ModelAdmin):
    list_display = ('vendor', 'period_start', 'period_end', 'cost_usd', 'cost_type')
    list_filter = ('vendor', 'cost_type')
    date_hierarchy = 'period_start'


@admin.register(LLMPriceBook)
class LLMPriceBookAdmin(admin.ModelAdmin):
    list_display = (
        'model_name', 'vendor', 'effective_start', 'effective_end',
        'input_cost_per_1m_tokens_usd', 'output_cost_per_1m_tokens_usd', 'is_active',
    )
    list_filter = ('vendor', 'is_active')
    search_fields = ('model_name',)


@admin.register(LLMUsageEvent)
class LLMUsageEventAdmin(admin.ModelAdmin):
    list_display = (
        'created_at', 'user', 'feature', 'model_name',
        'input_tokens', 'output_tokens', 'cost_usd', 'escalated',
    )
    list_filter = ('feature', 'model_name', 'escalated')
    date_hierarchy = 'created_at'
    search_fields = ('user__email',)
    readonly_fields = ('request_id', 'created_at')
    raw_id_fields = ('user',)


@admin.register(UserSubscriptionSnapshot)
class UserSubscriptionSnapshotAdmin(admin.ModelAdmin):
    list_display = ('user', 'tier', 'monthly_price_usd', 'effective_start', 'effective_end')
    list_filter = ('tier',)
    search_fields = ('user__email',)
    raw_id_fields = ('user',)


@admin.register(DailyCostRollup)
class DailyCostRollupAdmin(admin.ModelAdmin):
    list_display = ('date', 'user', 'feature', 'total_cost_usd', 'total_calls')
    list_filter = ('feature',)
    date_hierarchy = 'date'
    raw_id_fields = ('user',)


@admin.register(BudgetGuardrail)
class BudgetGuardrailAdmin(admin.ModelAdmin):
    list_display = ('name', 'scope', 'scope_value', 'budget_usd', 'period', 'alert_threshold_pct', 'is_active')
    list_filter = ('scope', 'period', 'is_active')
