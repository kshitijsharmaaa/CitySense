"""
CitySense project-level views.
"""

from django.http import JsonResponse
from django.db.models import Count, Prefetch, Q
from django.shortcuts import render
from django.views.decorators.http import require_GET

from incidents.models import Incident, IncidentStatus
from incidents.presentation import complaint_age
from issues.models import Department, Issue, Priority


@require_GET
def health_check(request):
    """
    GET /health/
    Returns HTTP 200 with a JSON payload for monitoring.
    """
    return JsonResponse(
        {
            "status": "ok",
            "service": "CitySense",
        }
    )


def home(request):
    """Render public guidance or the administrator's live operations overview."""
    context = {"admin_home": False}

    if request.user.is_authenticated and request.user.is_admin_user:
        incidents = Incident.objects.all()
        closed_statuses = (IncidentStatus.RESOLVED, IncidentStatus.REJECTED)
        active_incidents = incidents.exclude(status__in=closed_statuses)
        reports = Issue.objects.all()
        report_counts = {
            "total": reports.count(),
            "open": reports.filter(
                Q(incident__isnull=True) | ~Q(incident__status__in=closed_statuses)
            ).count(),
            "assigned": reports.filter(incident__status=IncidentStatus.ASSIGNED).count(),
            "in_progress": reports.filter(incident__status=IncidentStatus.IN_PROGRESS).count(),
            "resolved": reports.filter(incident__status=IncidentStatus.RESOLVED).count(),
            "closed": reports.filter(incident__status=IncidentStatus.REJECTED).count(),
        }

        candidate_incidents = active_incidents.select_related(
            "department", "assigned_to"
        ).prefetch_related(Prefetch(
            "issues",
            queryset=Issue.objects.select_related("incident").order_by("-created_at"),
        ))
        attention_items = []
        priority_rank = {
            Priority.CRITICAL: 0,
            Priority.HIGH: 1,
            Priority.MEDIUM: 2,
            Priority.LOW: 3,
        }
        for incident in candidate_incidents:
            age = complaint_age(
                incident.created_at, incident.priority, status=incident.status
            )
            unassigned = not incident.department or not incident.assigned_to
            high_priority = incident.priority in (Priority.CRITICAL, Priority.HIGH)
            old_case = age and age["state"] != "on_track"
            if not (high_priority or unassigned or old_case):
                continue
            reasons = []
            if high_priority:
                reasons.append("High priority")
            if unassigned:
                reasons.append("Needs assignment")
            if old_case:
                reasons.append(age["attention_text"])
            linked_reports = list(incident.issues.all())
            attention_items.append({
                "incident": incident,
                "issue": linked_reports[0] if linked_reports else None,
                "age": age,
                "reason": " ? ".join(reasons),
                "sort_key": (
                    priority_rank.get(incident.priority, 4),
                    0 if unassigned else 1,
                    0 if age and age["state"] == "overdue" else 1,
                    incident.created_at,
                ),
            })
        attention_items.sort(key=lambda item: item["sort_key"])

        department_workload = Department.objects.annotate(
            active_incident_count=Count(
                "incidents",
                filter=~Q(incidents__status__in=closed_statuses),
            )
        ).filter(active_incident_count__gt=0).order_by(
            "-active_incident_count", "name"
        )

        context.update({
            "admin_home": True,
            "report_count": report_counts["total"],
            "open_report_count": report_counts["open"],
            "assigned_report_count": report_counts["assigned"],
            "in_progress_report_count": report_counts["in_progress"],
            "resolved_report_count": report_counts["resolved"],
            "closed_report_count": report_counts["closed"],
            "active_incident_count": active_incidents.count(),
            "in_progress_count": incidents.filter(status=IncidentStatus.IN_PROGRESS).count(),
            "resolved_count": incidents.filter(status=IncidentStatus.RESOLVED).count(),
            "recent_reports": Issue.objects.select_related(
                "incident__department", "ai_department"
            ).order_by("-created_at")[:6],
            "recent_incidents": active_incidents.select_related(
                "department", "assigned_to"
            ).order_by("-updated_at")[:6],
            "attention_items": attention_items[:8],
            "department_workload": department_workload,
        })

    return render(request, "landing/home.html", context)
