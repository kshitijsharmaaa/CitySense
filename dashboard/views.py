from django.shortcuts import render
from django.views.decorators.http import require_GET

from accounts.decorators import citizen_or_admin_required
from issues.models import Issue


@citizen_or_admin_required
@require_GET
def index(request):
    issues = Issue.objects.select_related("incident__department")
    if request.user.is_citizen:
        issues = issues.filter(reported_by=request.user)
    return render(request, "dashboard/index.html", {"issues": issues})
