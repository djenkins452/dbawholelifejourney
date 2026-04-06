from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability

registry.register(DomainCapability(
    name='medical',
    display_name='Medical & Labs',
    description='Medical records, lab results, providers, and medications',
    intent_types=['take_medication', 'take_intake_by_time', 'email_intake_list'],
    primary_models=['Medication', 'MedicationLog', 'LabResult', 'Provider'],
    context_builders=['_build_health_and_vitals', '_build_medical_context'],
    proactive_signals=['medication_gap', 'medication_overdue', 'lab_result_due'],
    related_domains=['health'],
    url_namespace='medical',
))
