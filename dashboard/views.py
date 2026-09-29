from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.decorators import citizen_or_admin_required
from incidents.models import IncidentStatus
from issues.models import Issue


def _personal_issue_queryset(user):
    return Issue.objects.filter(reported_by=user).select_related(
        "incident__department", "incident__assigned_to", "ai_department"
    ).prefetch_related("images")


def _personal_stats(issues):
    return {
        "total": issues.count(),
        "active": issues.filter(
            Q(incident__isnull=True)
            | Q(incident__status__in=(
                IncidentStatus.REPORTED,
                IncidentStatus.VERIFIED,
                IncidentStatus.ASSIGNED,
                IncidentStatus.IN_PROGRESS,
            ))
        ).count(),
        "in_progress": issues.filter(incident__status=IncidentStatus.IN_PROGRESS).count(),
        "resolved": issues.filter(incident__status=IncidentStatus.RESOLVED).count(),
        "linked": issues.filter(incident__isnull=False).count(),
        "incident_count": issues.exclude(incident__isnull=True).values("incident_id").distinct().count(),
    }


def _admin_stats(issues):
    linked = issues.exclude(incident__isnull=True)
    return {
        "total": issues.count(),
        "active": linked.exclude(
            incident__status__in=(IncidentStatus.RESOLVED, IncidentStatus.REJECTED)
        ).values("incident_id").distinct().count(),
        "resolved": linked.filter(
            incident__status=IncidentStatus.RESOLVED
        ).values("incident_id").distinct().count(),
        "in_progress": linked.filter(
            incident__status=IncidentStatus.IN_PROGRESS
        ).values("incident_id").distinct().count(),
        "linked": linked.count(),
    }


def _living_city_report_points(issues):
    located = list(issues.exclude(latitude__isnull=True).exclude(longitude__isnull=True))
    if not located:
        return []
    latitudes = [float(issue.latitude) for issue in located]
    longitudes = [float(issue.longitude) for issue in located]
    min_lat, max_lat = min(latitudes), max(latitudes)
    min_lng, max_lng = min(longitudes), max(longitudes)
    lat_span = max_lat - min_lat or 1
    lng_span = max_lng - min_lng or 1
    points = []
    for issue in located:
        x = 600 if max_lng == min_lng else 45 + ((float(issue.longitude) - min_lng) / lng_span) * 1110
        y = 400 if max_lat == min_lat else 70 + ((max_lat - float(issue.latitude)) / lat_span) * 660
        points.append({
            "x": round(x, 1),
            "y": round(y, 1),
            "resolved": bool(issue.incident and issue.incident.status == IncidentStatus.RESOLVED),
        })
    return points


@citizen_or_admin_required
@require_GET
def index(request):
    issues = _personal_issue_queryset(request.user) if request.user.is_citizen else Issue.objects.select_related(
        "incident__department", "incident__assigned_to", "ai_department"
    ).prefetch_related("images")
    stats = _personal_stats(issues) if request.user.is_citizen else _admin_stats(issues)
    if request.user.is_citizen:
        incident_ids = issues.exclude(incident__isnull=True).values("incident_id").distinct()
        other_report_count = Issue.objects.filter(
            incident_id__in=incident_ids, reported_by__role="CITIZEN"
        ).exclude(reported_by=request.user).count()
        city_report_points = _living_city_report_points(issues)
    else:
        other_report_count = 0
        city_report_points = []
    hour = timezone.localtime().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    context = {
        "issues": issues,
        "stats": stats,
        "other_report_count": other_report_count,
        "greeting": greeting,
        "first_name": request.user.name.strip().split()[0] if request.user.name.strip() else request.user.name,
        "city_report_points": city_report_points,
    }
    return render(request, "dashboard/index.html", context)


@citizen_or_admin_required
@require_GET
def profile(request):
    issues = _personal_issue_queryset(request.user)
    context = {"stats": _personal_stats(issues)}
    return render(request, "dashboard/profile.html", context)
