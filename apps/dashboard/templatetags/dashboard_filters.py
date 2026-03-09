from django import template

register = template.Library()


@register.filter(name='minutes_to_hm')
def minutes_to_hm(value):
    """Convert minutes to 'Xh Ym' format. E.g. 332 -> '5h 32m'."""
    try:
        total = int(float(value))
    except (TypeError, ValueError):
        return value
    hours = total // 60
    mins = total % 60
    if hours and mins:
        return f"{hours}h {mins}m"
    elif hours:
        return f"{hours}h 0m"
    else:
        return f"{mins}m"
