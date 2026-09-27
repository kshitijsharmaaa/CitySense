import logging

from django.db import transaction

from ai_engine.validators import validate_triage_result
from incidents.models import Incident, IncidentStatus, IncidentStatusHistory
from incidents.intelligence import find_related_incident
from incidents.services import update_incident_intelligence

from .models import Department

logger = logging.getLogger(__name__)


@transaction.atomic
def create_issue_with_incident(*, issue, reported_by, triage_result=None):
    """Save a triaged report and associate it with a matching/new incident.

    The triage provider runs before this transaction. The Issue always stores
    its validated AI recommendation, which seeds classification only when a
    new Incident is created. Existing incidents keep their canonical values.
    Matching failures roll back to a savepoint and use a new standalone
    incident so an uncertain report is never silently merged.
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

    matched_incident = None
    try:
        # A savepoint makes unexpected query/scoring/update failures recoverable
        # without leaving a partial association or a broken outer transaction.
        with transaction.atomic():
            match = find_related_incident(issue)
            if match is not None:
                matched_incident = match.incident
                issue.incident = matched_incident
                issue.save(update_fields=("incident", "updated_at"))
                update_incident_intelligence(matched_incident, update_severity=False)
    except Exception:
        logger.exception("Incident matching failed; creating a separate incident for issue %s", issue.pk)
        matched_incident = None

    if matched_incident is None:
        if triage_result is None:
            category = "Other"
            priority = "MEDIUM"
            department, _ = Department.objects.get_or_create(name="General")
        else:
            category = triage_result["category"]
            priority = triage_result["priority"]
            department = ai_department
        matched_incident = Incident.objects.create(
            title=issue.title,
            category=category,
            priority=priority,
            status=IncidentStatus.REPORTED,
            department=department,
            latitude=issue.latitude,
            longitude=issue.longitude,
            report_count=1,
        )
        issue.incident = matched_incident
        issue.save(update_fields=("incident", "updated_at"))

        IncidentStatusHistory.objects.create(
            incident=matched_incident,
            old_status="",
            new_status=IncidentStatus.REPORTED,
            comment="Incident created from a citizen report.",
            changed_by=reported_by,
        )
        # Severity is useful intelligence, but a calculation failure must not
        # discard the citizen's otherwise-valid report.
        try:
            with transaction.atomic():
                update_incident_intelligence(matched_incident)
        except Exception:
            logger.exception("Severity update failed for new incident %s", matched_incident.pk)

    return issue
