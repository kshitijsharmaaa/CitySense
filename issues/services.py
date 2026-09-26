from django.db import transaction

from incidents.models import Incident, IncidentStatus, IncidentStatusHistory

from .models import Department


@transaction.atomic
def create_issue_with_incident(*, issue, reported_by):
    """Create a report and its temporary one-report incident atomically.

    This is the Phase 3 seam for the later triage and duplicate-association
    pipeline. Until that work exists, each report gets its own incident.
    """
    issue.reported_by = reported_by
    issue.save()

    department, _ = Department.objects.get_or_create(name="General")
    incident = Incident.objects.create(
        title=issue.title,
        category="Other",
        priority="MEDIUM",
        status=IncidentStatus.REPORTED,
        department=department,
        latitude=issue.latitude,
        longitude=issue.longitude,
        report_count=1,
    )
    issue.incident = incident
    issue.save(update_fields=("incident", "updated_at"))

    IncidentStatusHistory.objects.create(
        incident=incident,
        old_status="",
        new_status=IncidentStatus.REPORTED,
        comment="Incident created from a citizen report.",
        changed_by=reported_by,
    )
    return issue
