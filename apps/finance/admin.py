# ==============================================================================
# File: apps/finance/admin.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Finance module Django admin configuration
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# ==============================================================================
from django.contrib import admin
from django.utils.html import format_html

from .models import (
    FinancialAccount,
    TransactionCategory,
    Transaction,
    Budget,
    FinancialGoal,
    FinancialMetricSnapshot,
    Payee,
)


@admin.register(FinancialAccount)
class FinancialAccountAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'user', 'account_type', 'formatted_balance',
        'institution', 'include_in_net_worth', 'status'
    ]
    list_filter = ['account_type', 'status', 'include_in_net_worth', 'currency']
    search_fields = ['name', 'institution', 'user__email']
    readonly_fields = ['created_at', 'updated_at', 'balance_updated_at']
    ordering = ['user', 'sort_order', 'name']

    fieldsets = (
        (None, {
            'fields': ('user', 'name', 'account_type', 'institution')
        }),
        ('Balance', {
            'fields': ('current_balance', 'currency', 'balance_updated_at')
        }),
        ('Display', {
            'fields': ('color', 'icon', 'sort_order', 'is_hidden')
        }),
        ('Settings', {
            'fields': ('include_in_net_worth', 'account_number_last4', 'notes')
        }),
        ('Status', {
            'fields': ('status', 'created_at', 'updated_at')
        }),
    )

    def formatted_balance(self, obj):
        color = 'green' if obj.current_balance >= 0 else 'red'
        return format_html(
            '<span style="color: {};">${:,.2f}</span>',
            color,
            obj.current_balance
        )
    formatted_balance.short_description = 'Balance'
    formatted_balance.admin_order_field = 'current_balance'


@admin.register(TransactionCategory)
class TransactionCategoryAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'category_type', 'parent', 'user_display',
        'color_preview', 'is_system', 'is_active'
    ]
    list_filter = ['category_type', 'is_system', 'is_active']
    search_fields = ['name', 'user__email']
    ordering = ['category_type', 'sort_order', 'name']

    def user_display(self, obj):
        return obj.user.email if obj.user else 'System'
    user_display.short_description = 'Owner'

    def color_preview(self, obj):
        return format_html(
            '<span style="background-color: {}; padding: 2px 10px; border-radius: 3px;">&nbsp;</span>',
            obj.color
        )
    color_preview.short_description = 'Color'


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'date', 'description', 'formatted_amount', 'account',
        'category', 'is_cleared', 'user'
    ]
    list_filter = ['account', 'category', 'is_cleared', 'is_recurring', 'status']
    search_fields = ['description', 'payee', 'notes', 'user__email']
    date_hierarchy = 'date'
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-date', '-created_at']

    fieldsets = (
        (None, {
            'fields': ('user', 'account', 'date', 'amount', 'description')
        }),
        ('Categorization', {
            'fields': ('category', 'payee', 'tags')
        }),
        ('Details', {
            'fields': ('notes', 'reference', 'is_cleared', 'is_recurring')
        }),
        ('Transfer', {
            'fields': ('transfer_pair',),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('status', 'created_at', 'updated_at')
        }),
    )

    def formatted_amount(self, obj):
        color = 'green' if obj.amount >= 0 else 'red'
        sign = '+' if obj.amount >= 0 else ''
        return format_html(
            '<span style="color: {};">{}{:,.2f}</span>',
            color,
            sign,
            obj.amount
        )
    formatted_amount.short_description = 'Amount'
    formatted_amount.admin_order_field = 'amount'


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = [
        'category', 'month', 'budgeted_amount', 'spent_display',
        'remaining_display', 'status_badge', 'user'
    ]
    list_filter = ['month', 'category__category_type', 'rollover_enabled']
    search_fields = ['category__name', 'user__email']
    ordering = ['-month', 'category__name']
    date_hierarchy = 'month'

    def spent_display(self, obj):
        return f'${obj.spent_amount:,.2f}'
    spent_display.short_description = 'Spent'

    def remaining_display(self, obj):
        remaining = obj.remaining_amount
        color = 'green' if remaining >= 0 else 'red'
        return format_html(
            '<span style="color: {};">${:,.2f}</span>',
            color,
            remaining
        )
    remaining_display.short_description = 'Remaining'

    def status_badge(self, obj):
        colors = {
            'on_track': '#10b981',
            'warning': '#f59e0b',
            'over': '#ef4444'
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.status.replace('_', ' ').title()
        )
    status_badge.short_description = 'Status'


@admin.register(FinancialGoal)
class FinancialGoalAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'goal_type', 'target_amount', 'current_amount',
        'progress_bar', 'goal_status', 'target_date', 'user'
    ]
    list_filter = ['goal_type', 'goal_status']
    search_fields = ['name', 'description', 'user__email']
    readonly_fields = ['created_at', 'updated_at', 'completed_at']
    ordering = ['-created_at']

    fieldsets = (
        (None, {
            'fields': ('user', 'name', 'goal_type', 'description')
        }),
        ('Target', {
            'fields': ('target_amount', 'current_amount', 'target_date')
        }),
        ('Linked Items', {
            'fields': ('linked_account', 'life_goal')
        }),
        ('Display', {
            'fields': ('color', 'icon')
        }),
        ('Status', {
            'fields': ('goal_status', 'started_at', 'completed_at', 'notes')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def progress_bar(self, obj):
        pct = obj.progress_percentage
        color = '#10b981' if pct < 100 else '#6366f1'
        return format_html(
            '<div style="width: 100px; background: #e5e7eb; border-radius: 4px;">'
            '<div style="width: {}%; background: {}; height: 12px; border-radius: 4px;"></div>'
            '</div>'
            '<small>{:.1f}%</small>',
            min(100, pct),
            color,
            pct
        )
    progress_bar.short_description = 'Progress'


@admin.register(FinancialMetricSnapshot)
class FinancialMetricSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        'snapshot_date', 'user', 'formatted_net_worth',
        'formatted_cash_flow', 'savings_rate_display'
    ]
    list_filter = ['snapshot_date']
    search_fields = ['user__email']
    date_hierarchy = 'snapshot_date'
    ordering = ['-snapshot_date']

    readonly_fields = [
        'snapshot_date', 'total_assets', 'total_liabilities', 'net_worth',
        'monthly_income', 'monthly_expenses', 'monthly_cash_flow',
        'savings_rate', 'liquid_assets', 'emergency_fund_months',
        'created_at', 'updated_at'
    ]

    def formatted_net_worth(self, obj):
        color = 'green' if obj.net_worth >= 0 else 'red'
        return format_html(
            '<span style="color: {};">${:,.2f}</span>',
            color,
            obj.net_worth
        )
    formatted_net_worth.short_description = 'Net Worth'

    def formatted_cash_flow(self, obj):
        color = 'green' if obj.monthly_cash_flow >= 0 else 'red'
        return format_html(
            '<span style="color: {};">${:,.2f}</span>',
            color,
            obj.monthly_cash_flow
        )
    formatted_cash_flow.short_description = 'Cash Flow'

    def savings_rate_display(self, obj):
        return f'{obj.savings_rate:.1f}%'
    savings_rate_display.short_description = 'Savings Rate'


@admin.register(Payee)
class PayeeAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'default_category', 'use_count', 'last_used_at']
    list_filter = ['default_category']
    search_fields = ['name', 'user__email']
    ordering = ['-use_count', 'name']
