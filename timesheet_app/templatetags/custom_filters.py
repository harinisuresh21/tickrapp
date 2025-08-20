from django import template

register = template.Library()

@register.filter
def color_from_hours(hours):
    """
    Returns a color hex code based on hours worked (GitHub contribution-style heatmap).
    Handles int, float, or string inputs.
    """
    try:
        hours = float(hours)
    except (ValueError, TypeError):
        return '#ebedf0'  # default (light grey)

    if hours <= 0:
        return '#ebedf0'  # light grey
    elif hours < 2:
        return '#9be9a8'  # light green
    elif hours < 4:
        return '#40c463'  # medium green
    else:
        return '#30a14e'  # dark green


@register.filter
def multiply(value, arg):
    """
    Multiplies the value by the argument.
    Handles int, float, and string safely.
    Returns 0 if invalid.
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0
