from django.shortcuts import render
from django.views.decorators.http import require_GET

from accounts.decorators import citizen_required

@citizen_required
@require_GET
def index(request):
    issues = (
        request.user.reported_issues
        .select_related("incident__department")
        .all()
    )
    return render(request, "dashboard/index.html", {"issues": issues})
