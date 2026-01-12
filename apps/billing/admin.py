"""
Billing admin interface.

Provides admin views for managing subscriptions, referrals, and payouts.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    BillingProfile,
    CreditTransaction,
    FeatureSuggestion,
    FoundingMemberPayout,
    PaymentAuditLog,
    PromoCodeUsage,
    ReferralQualification,
    ReferralReward,
)


@admin.register(BillingProfile)
class BillingProfileAdmin(admin.ModelAdmin):
    list_display = [
        'user_email',
        'pricing_tier',
        'subscription_status',
        'billing_cycle',
        'account_credit',
        'referral_code',
        'created_at',
    ]
    list_filter = ['pricing_tier', 'subscription_status', 'billing_cycle']
    search_fields = ['user__email', 'user__first_name', 'stripe_customer_id', 'referral_code']
    readonly_fields = [
        'stripe_customer_id',
        'stripe_subscription_id',
        'referral_code',
        'created_at',
        'updated_at',
    ]
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Pricing', {
            'fields': ('pricing_tier', 'tier_locked_until', 'graduation_date')
        }),
        ('Subscription', {
            'fields': (
                'subscription_status',
                'billing_cycle',
                'current_period_start',
                'current_period_end',
                'cancel_at_period_end',
            )
        }),
        ('Stripe', {
            'fields': ('stripe_customer_id', 'stripe_subscription_id'),
            'classes': ('collapse',),
        }),
        ('Referral', {
            'fields': ('referral_code', 'referred_by', 'account_credit')
        }),
        ('Payout Settings (Founding Members)', {
            'fields': ('payout_method', 'payout_email', 'payout_phone', 'payout_bank_info'),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Email'
    user_email.admin_order_field = 'user__email'


@admin.register(ReferralReward)
class ReferralRewardAdmin(admin.ModelAdmin):
    list_display = [
        'referrer_email',
        'referred_email',
        'signup_date',
        'first_payment_date',
        'referrer_reward_given',
        'referred_reward_given',
    ]
    list_filter = ['referrer_reward_given', 'referred_reward_given', 'signup_date']
    search_fields = ['referrer__email', 'referred_user__email']
    date_hierarchy = 'signup_date'

    def referrer_email(self, obj):
        return obj.referrer.email
    referrer_email.short_description = 'Referrer'

    def referred_email(self, obj):
        return obj.referred_user.email
    referred_email.short_description = 'Referred'


@admin.register(ReferralQualification)
class ReferralQualificationAdmin(admin.ModelAdmin):
    list_display = [
        'referrer_email',
        'referred_email',
        'signup_date',
        'qualified_date',
        'bonus_eligible',
        'bonus_paid',
        'quarter_applied',
    ]
    list_filter = ['bonus_eligible', 'bonus_paid', 'quarter_applied']
    search_fields = ['referrer__email', 'referred_user__email']
    date_hierarchy = 'qualified_date'

    def referrer_email(self, obj):
        return obj.referrer.email
    referrer_email.short_description = 'Founding Member'

    def referred_email(self, obj):
        return obj.referred_user.email
    referred_email.short_description = 'Referred User'


@admin.register(FoundingMemberPayout)
class FoundingMemberPayoutAdmin(admin.ModelAdmin):
    list_display = [
        'founding_member_email',
        'quarter',
        'qualifying_referrals',
        'payout_amount',
        'payout_method',
        'status',
        'paid_date',
    ]
    list_filter = ['status', 'quarter', 'payout_method']
    search_fields = ['founding_member__email']
    actions = ['mark_as_paid']

    def founding_member_email(self, obj):
        return obj.founding_member.email
    founding_member_email.short_description = 'Founding Member'

    @admin.action(description='Mark selected payouts as paid')
    def mark_as_paid(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status='pending').update(
            status='paid',
            paid_date=timezone.now().date()
        )
        self.message_user(request, f'{updated} payout(s) marked as paid.')


@admin.register(FeatureSuggestion)
class FeatureSuggestionAdmin(admin.ModelAdmin):
    list_display = [
        'user_email',
        'short_suggestion',
        'status',
        'submitted_date',
        'implemented_date',
        'reward_given',
    ]
    list_filter = ['status', 'reward_given', 'public_credit_consent']
    search_fields = ['user__email', 'suggestion_text']
    date_hierarchy = 'submitted_date'
    readonly_fields = ['submitted_date', 'reward_given']
    actions = ['mark_implemented', 'mark_declined']

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def short_suggestion(self, obj):
        return obj.suggestion_text[:80] + '...' if len(obj.suggestion_text) > 80 else obj.suggestion_text
    short_suggestion.short_description = 'Suggestion'

    @admin.action(description='Mark as implemented (give reward)')
    def mark_implemented(self, request, queryset):
        for suggestion in queryset.filter(status__in=['submitted', 'reviewing', 'planned']):
            suggestion.mark_implemented()
        self.message_user(request, f'Marked as implemented and rewards given.')

    @admin.action(description='Mark as declined')
    def mark_declined(self, request, queryset):
        queryset.update(status='declined')
        self.message_user(request, f'Marked as declined.')


@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'user_email',
        'amount_display',
        'transaction_type',
        'description_short',
        'created_at',
    ]
    list_filter = ['transaction_type', 'created_at']
    search_fields = ['user__email', 'description']
    date_hierarchy = 'created_at'
    readonly_fields = ['user', 'amount', 'transaction_type', 'description', 'related_invoice', 'created_at']

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def amount_display(self, obj):
        if obj.amount >= 0:
            return format_html('<span style="color: green;">+${}</span>', obj.amount)
        return format_html('<span style="color: red;">${}</span>', obj.amount)
    amount_display.short_description = 'Amount'

    def description_short(self, obj):
        return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
    description_short.short_description = 'Description'

    def has_add_permission(self, request):
        return False  # Transactions are created programmatically

    def has_change_permission(self, request, obj=None):
        return False  # Transactions are immutable


@admin.register(PromoCodeUsage)
class PromoCodeUsageAdmin(admin.ModelAdmin):
    list_display = ['user_email', 'code', 'applied_date', 'discount_display']
    list_filter = ['code', 'applied_date']
    search_fields = ['user__email', 'code']
    date_hierarchy = 'applied_date'

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def discount_display(self, obj):
        if obj.discount_amount:
            return f'${obj.discount_amount}'
        if obj.discount_percent:
            return f'{obj.discount_percent}%'
        return '-'
    discount_display.short_description = 'Discount'


@admin.register(PaymentAuditLog)
class PaymentAuditLogAdmin(admin.ModelAdmin):
    list_display = [
        'created_at',
        'user_email',
        'action',
        'success_icon',
        'stripe_event_id_short',
    ]
    list_filter = ['action', 'success', 'created_at']
    search_fields = ['user__email', 'stripe_event_id', 'stripe_object_id']
    date_hierarchy = 'created_at'
    readonly_fields = [
        'user', 'action', 'stripe_event_id', 'stripe_object_id',
        'success', 'details', 'ip_address', 'user_agent', 'created_at'
    ]

    def user_email(self, obj):
        return obj.user.email if obj.user else '-'
    user_email.short_description = 'User'

    def success_icon(self, obj):
        if obj.success:
            return format_html('<span style="color: green;">&#10004;</span>')
        return format_html('<span style="color: red;">&#10008;</span>')
    success_icon.short_description = 'OK'

    def stripe_event_id_short(self, obj):
        if obj.stripe_event_id:
            return obj.stripe_event_id[:20] + '...'
        return '-'
    stripe_event_id_short.short_description = 'Event ID'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False  # Audit logs are immutable
