from django.db import transaction

from ai_engine.validators import validate_triage_result
from incidents.models import Incident, IncidentStatus, IncidentStatusHistory

from .models import Department


@transaction.atomic
def create_issue_with_incident(*, issue, reported_by, triage_result=None):
    """Save a triaged report and its current one-report incident atomically.

    The triage provider runs before this transaction. The Issue stores its AI
    recommendation, while the Incident retains the Phase 3 administrator-facing
    defaults until a later phase implements review and association workflows.
    """
    if triage_result is not None:
        triage_result = validate_triage_result(triage_result)
        ai_department, _ = Department.objects.get_or_create(name=triage_result["department"])
        issue.ai_category = triage_result["category"]
        issue.ai_priority = triage_result["priority"]
        issue.ai_department = ai_department
        issue.ai_summary = triage_result["summary"]
        issue.ai_confidence = triage_result["confidence"]

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
