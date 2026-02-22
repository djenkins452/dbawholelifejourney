import uuid

from django.conf import settings
from django.db import models


class ThirdPartyVendor(models.Model):
    """External service vendor (OpenAI, Twilio, Railway, etc.)."""

    CATEGORY_CHOICES = [
        ('LLM', 'LLM / AI'),
        ('TTS', 'Text-to-Speech'),
        ('SMS', 'SMS'),
        ('EMAIL', 'Email'),
        ('NUTRITION_API', 'Nutrition API'),
        ('HOSTING', 'Hosting'),
        ('ANALYTICS', 'Analytics'),
        ('FINANCE_API', 'Finance API'),
        ('HEALTH_API', 'Health API'),
        ('OTHER', 'Other'),
    ]

    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Third-Party Vendor'
        verbose_name_plural = 'Third-Party Vendors'

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class VendorBillingRecord(models.Model):
    """Monthly/periodic billing from a vendor (Railway, Twilio, etc.)."""

    COST_TYPE_CHOICES = [
        ('FIXED', 'Fixed'),
        ('VARIABLE', 'Variable'),
    ]

    vendor = models.ForeignKey(
        ThirdPartyVendor, on_delete=models.CASCADE,
        related_name='billing_records',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    cost_usd = models.DecimalField(max_digits=10, decimal_places=4)
    cost_type = models.CharField(max_length=10, choices=COST_TYPE_CHOICES)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_start']
        verbose_name = 'Vendor Billing Record'
        verbose_name_plural = 'Vendor Billing Records'

    def __str__(self):
        return f"{self.vendor.name} {self.period_start}–{self.period_end}: ${self.cost_usd}"


class LLMPriceBook(models.Model):
    """Per-model pricing by effective date. Never hardcode costs in code."""

    vendor = models.ForeignKey(
        ThirdPartyVendor, on_delete=models.CASCADE,
        related_name='price_book_entries',
    )
    model_name = models.CharField(max_length=100, db_index=True)
    effective_start = models.DateField()
    effective_end = models.DateField(null=True, blank=True)
    input_cost_per_1m_tokens_usd = models.DecimalField(max_digits=10, decimal_places=4)
    output_cost_per_1m_tokens_usd = models.DecimalField(max_digits=10, decimal_places=4)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-effective_start']
        unique_together = [('vendor', 'model_name', 'effective_start')]
        verbose_name = 'LLM Price Book Entry'
        verbose_name_plural = 'LLM Price Book Entries'

    def __str__(self):
        return (
            f"{self.model_name} (from {self.effective_start}): "
            f"${self.input_cost_per_1m_tokens_usd}/1M in, "
            f"${self.output_cost_per_1m_tokens_usd}/1M out"
        )


class LLMUsageEvent(models.Model):
    """Ledger row per LLM call. Core telemetry table."""

    FEATURE_CHOICES = [
        ('INTENT', 'Intent Recognition'),
        ('MAIN_RESPONSE', 'Main AI Response'),
        ('TRANSCRIPTION', 'Audio Transcription'),
        ('SUMMARIZATION', 'Transcript Summarization'),
        ('NUTRITION_AI', 'AI Nutrition Estimation'),
        ('VISION', 'Vision / Image Analysis'),
        ('SCAN', 'Scan (Barcode/Medicine/Product)'),
        ('HEALTHCARE_LOOKUP', 'Healthcare Provider Lookup'),
        ('JOURNAL_REFLECTION', 'Journal Reflection'),
        ('DAILY_INSIGHT', 'Daily Insight'),
        ('WEEKLY_SUMMARY', 'Weekly Summary'),
        ('COS_CHAT', 'CoS Chat'),
        ('EXEC_BRIEFING', 'Executive Briefing'),
        ('OTHER', 'Other'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='llm_usage_events',
    )
    conversation_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    request_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    feature = models.CharField(max_length=30, choices=FEATURE_CHOICES, db_index=True)
    engine = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    model_name = models.CharField(max_length=100, db_index=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    escalated = models.BooleanField(default=False, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['feature', 'created_at']),
            models.Index(fields=['model_name', 'created_at']),
            models.Index(fields=['created_at', 'cost_usd']),
        ]
        verbose_name = 'LLM Usage Event'
        verbose_name_plural = 'LLM Usage Events'

    def __str__(self):
        user_label = self.user.email if self.user else 'system'
        return f"{self.feature} by {user_label} @ {self.created_at:%Y-%m-%d %H:%M}"


class UserSubscriptionSnapshot(models.Model):
    """Snapshot of user tier for margin calculations."""

    TIER_CHOICES = [
        ('FREE', 'Free'),
        ('FAITH_ONLY', 'Faith Only'),
        ('STUDENT', 'Student'),
        ('ADULT', 'Adult'),
        ('FOUNDING', 'Founding Member'),
        ('OWNER', 'Owner'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='subscription_snapshots',
    )
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, db_index=True)
    monthly_price_usd = models.DecimalField(max_digits=8, decimal_places=2)
    effective_start = models.DateField()
    effective_end = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_start']
        verbose_name = 'User Subscription Snapshot'
        verbose_name_plural = 'User Subscription Snapshots'

    def __str__(self):
        return f"{self.user.email} — {self.tier} (${self.monthly_price_usd}/mo)"


class DailyCostRollup(models.Model):
    """Pre-aggregated daily cost summary for fast dashboard queries."""

    date = models.DateField(db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True, related_name='daily_cost_rollups',
    )
    feature = models.CharField(max_length=30, null=True, blank=True, db_index=True)
    total_cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    total_calls = models.PositiveIntegerField(default=0)
    total_input_tokens = models.PositiveIntegerField(default=0)
    total_output_tokens = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [('date', 'user', 'feature')]
        ordering = ['-date']
        verbose_name = 'Daily Cost Rollup'
        verbose_name_plural = 'Daily Cost Rollups'

    def __str__(self):
        user_label = self.user.email if self.user else 'all'
        return f"{self.date} | {user_label} | {self.feature or 'total'}: ${self.total_cost_usd}"


class BudgetGuardrail(models.Model):
    """Budget thresholds with alert triggers."""

    SCOPE_CHOICES = [
        ('TOTAL', 'Monthly Total'),
        ('PER_USER', 'Per User'),
        ('PER_FEATURE', 'Per Feature'),
    ]
    PERIOD_CHOICES = [
        ('DAILY', 'Daily'),
        ('MONTHLY', 'Monthly'),
    ]

    name = models.CharField(max_length=100)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    scope_value = models.CharField(
        max_length=50, null=True, blank=True,
        help_text='Feature name if scope is PER_FEATURE',
    )
    budget_usd = models.DecimalField(max_digits=10, decimal_places=2)
    period = models.CharField(max_length=10, choices=PERIOD_CHOICES, default='MONTHLY')
    alert_threshold_pct = models.IntegerField(
        default=80, help_text='Alert when spend reaches this % of budget',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scope', 'name']
        verbose_name = 'Budget Guardrail'
        verbose_name_plural = 'Budget Guardrails'

    def __str__(self):
        return f"{self.name} ({self.get_scope_display()}): ${self.budget_usd}/{self.get_period_display()}"
