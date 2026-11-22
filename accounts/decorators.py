from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    def decorator(view):
        @login_required
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if user.is_superuser or user.role in roles:
                return view(request, *args, **kwargs)
            raise PermissionDenied
        return _wrapped

    return decorator


employee_required = role_required("admin", "manager", "agent")
overseer_required = role_required("admin", "manager")
admin_required = role_required("admin")
