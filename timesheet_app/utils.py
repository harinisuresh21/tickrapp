from datetime import timedelta
from django.utils import timezone

def get_current_week_bounds(today=None):
    """Return (monday, sunday) for current week."""
    if today is None:
        today = timezone.localdate()
    monday = today - timedelta(days=today.weekday())   # 0 = Monday
    sunday = monday + timedelta(days=6)
    return monday, sunday
