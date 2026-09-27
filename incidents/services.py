"""Transactional helpers for attaching citizen reports to incidents."""

from decimal import Decimal

from issues.models import Issue

from .intelligence import calculate_incident_severity


def update_incident_intelligence(incident, *, update_severity=True):
    """Recalculate report count and location, optionally refreshing severity."""
    reports = list(Issue.objects.filter(incident=incident).only(
        "id", "incident_id", "ai_priority", "latitude", "longitude", "created_at",
    ))
    incident.report_count = len(reports)

    located_reports = [
        report for report in reports
        if report.latitude is not None and report.longitude is not None
    ]
    if located_reports:
        divisor = Decimal(len(located_reports))
        incident.latitude = sum((report.latitude for report in located_reports), Decimal("0")) / divisor
        incident.longitude = sum((report.longitude for report in located_reports), Decimal("0")) / divisor
    else:
        incident.latitude = None
        incident.longitude = None

    update_fields = ["report_count", "latitude", "longitude", "updated_at"]
    if update_severity:
        incident.severity_score = calculate_incident_severity(incident, reports).score
        update_fields.append("severity_score")
    incident.save(update_fields=update_fields)
    return incident
