from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability

registry.register(DomainCapability(
    name='finance',
    display_name='Finance',
    description='Transaction logging, budget tracking, and financial insights',
    intent_types=['log_transaction', 'check_budget'],
    primary_models=['Transaction', 'Budget', 'BudgetCategory'],
    context_builders=['_build_finance_context'],
    proactive_signals=['budget_threshold', 'savings_milestone', 'spending_pattern'],
    related_domains=['goals'],
    feature_flag='features.finance.enabled',
    url_namespace='finance',
))
