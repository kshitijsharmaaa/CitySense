"""Transactional helpers for attaching citizen reports to incidents."""

from decimal import Decimal

from issues.models import Issue

from .intelligence import calculate_incident_severity


def update_incident_intelligence(incident):
    """Recalculate report count, representative location and severity."""
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

    incident.severity_score = calculate_incident_severity(incident, reports).score
    incident.save(update_fields=("report_count", "latitude", "longitude", "severity_score", "updated_at"))
    return incident
