from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from accounts.decorators import citizen_required

from .models import Incident


@citizen_required
@require_GET
def detail(request, pk):
    incident = get_object_or_404(
        Incident.objects.select_related("department").prefetch_related("status_history").distinct(),
        pk=pk,
        issues__reported_by=request.user,
    )
    return render(request, "incidents/detail.html", {"incident": incident})
