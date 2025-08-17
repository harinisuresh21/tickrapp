from functools import wraps
from django.shortcuts import redirect
from django.http import HttpResponseForbidden

def role_required(*allowed):
    def wrap(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            if request.user.role not in allowed:
                return HttpResponseForbidden("You don't have permission to view this page.")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return wrap
