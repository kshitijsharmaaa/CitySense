from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from accounts.decorators import admin_required, citizen_or_admin_required

from issues.models import Issue

from .forms import IncidentFilterForm, IncidentReviewForm
from .models import Incident, IncidentStatusHistory
from .presentation import complaint_age, complaint_progress
from .workflow import update_incident_review


@citizen_or_admin_required
@require_GET
def detail(request, pk):
    incidents = Incident.objects.select_related("department").prefetch_related(
        "status_history", "issues"
    )
    if request.user.is_citizen:
        incidents = incidents.filter(issues__reported_by=request.user)
    incident = get_object_or_404(incidents.distinct(), pk=pk)
    history = list(incident.status_history.all())
    age = complaint_age(incident.created_at, incident.priority, status=incident.status)
    if request.user.is_citizen and age and age["state"] != "overdue":
        age = None
    progress = complaint_progress(incident.status, history)
    return render(request, "incidents/detail.html", {
        "incident": incident,
        "case_progress": progress,
        "case_age": age,
        "latest_update": history[0] if history else None,
        "case_next_action": progress["next_action"],
    })


@admin_required
@require_GET
def admin_dashboard(request):
    """List incidents with validated, server-side filters for ADMIN users."""
    filters = IncidentFilterForm(request.GET or None)
    incidents = Incident.objects.select_related('department', 'assigned_to').all()
    if filters.is_bound and filters.is_valid():
        values = filters.cleaned_data
        if values['status']:
            incidents = incidents.filter(status=values['status'])
        if values['priority']:
            incidents = incidents.filter(priority=values['priority'])
        if values['category']:
            incidents = incidents.filter(category=values['category'])
        if values['department']:
            incidents = incidents.filter(department=values['department'])

    page_obj = Paginator(incidents.order_by('-updated_at', '-pk'), 25).get_page(
        request.GET.get('page')
    )
    return render(request, 'incidents/admin_dashboard.html', {
        'incidents': page_obj.object_list,
        'page_obj': page_obj,
        'filters': filters,
    })


@admin_required
@require_http_methods(['GET', 'POST'])
def admin_detail(request, pk):
    """Review linked citizen reports and update administrator-owned fields."""
    incident = get_object_or_404(
        Incident.objects.select_related('department', 'assigned_to').prefetch_related(
            Prefetch(
                'issues',
                queryset=Issue.objects.select_related('reported_by', 'ai_department').order_by('-created_at'),
            ),
            Prefetch(
                'status_history',
                queryset=IncidentStatusHistory.objects.select_related('changed_by'),
            ),
        ),
        pk=pk,
    )

    form = IncidentReviewForm(request.POST or None, request.FILES or None, instance=incident)
    if request.method == 'POST' and form.is_valid():
        update_incident_review(
            incident_id=incident.pk,
            cleaned_data=form.cleaned_data,
            changed_by=request.user,
        )
        messages.success(request, 'Incident updated.')
        return redirect('incidents:admin_detail', pk=incident.pk)

    return render(request, 'incidents/admin_detail.html', {
        'incident': incident,
        'issues': incident.issues.all(),
        'status_history': incident.status_history.all(),
        'case_progress': complaint_progress(incident.status, list(incident.status_history.all())),
        'case_age': complaint_age(incident.created_at, incident.priority, status=incident.status),
        'case_next_action': complaint_progress(incident.status, list(incident.status_history.all()))['next_action'],
        'form': form,
    })
