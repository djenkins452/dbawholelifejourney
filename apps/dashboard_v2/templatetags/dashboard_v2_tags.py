"""Template tags for dashboard_v2."""

from django import template

register = template.Library()

# Map behavior domain keys to compliance scoring bucket slugs
DOMAIN_TO_BUCKET = {
    "medication": "medication_doses",
    "workout": "workouts",
    "routine": "routine_items",
    "task": "tasks",
    "journal": "journal",
    "faith": "faith",
}


@register.filter
def compliance_bucket(domain_key):
    """Convert a behavior domain key to a compliance scoring bucket slug."""
    return DOMAIN_TO_BUCKET.get(domain_key, domain_key)
