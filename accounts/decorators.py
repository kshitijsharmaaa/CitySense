from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def citizen_required(view):
    """Require a signed-in CITIZEN account for citizen workflow views."""
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_citizen:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def admin_required(view):
    """Require a signed-in CitySense ADMIN role for incident management."""
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_admin_user:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def citizen_or_admin_required(view):
    """Require an authenticated CitySense CITIZEN or ADMIN account."""
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not (request.user.is_citizen or request.user.is_admin_user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped
