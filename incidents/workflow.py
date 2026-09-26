"""Transactional persistence for administrator incident reviews."""

from django.db import transaction
from django.utils import timezone

from .models import Incident, IncidentStatus, IncidentStatusHistory


@transaction.atomic
def update_incident_review(*, incident_id, cleaned_data, changed_by):
    """Apply editable admin fields and record a status transition atomically."""
    incident = Incident.objects.select_for_update().get(pk=incident_id)
    old_status = incident.status
    new_status = cleaned_data['status']

    incident.department = cleaned_data['department']
    incident.assigned_to = cleaned_data['assigned_to']
    incident.status = new_status
    incident.resolution_notes = cleaned_data['resolution_notes']

    if new_status == IncidentStatus.RESOLVED:
        if old_status != IncidentStatus.RESOLVED or incident.resolved_at is None:
            incident.resolved_at = timezone.now()
    elif old_status == IncidentStatus.RESOLVED:
        # If an incident is reopened, retain the notes but clear the timestamp
        # indicating its current unresolved state.
        incident.resolved_at = None

    incident.save(update_fields=(
        'department', 'assigned_to', 'status', 'resolution_notes',
        'resolved_at', 'updated_at',
    ))

    if old_status != new_status:
        IncidentStatusHistory.objects.create(
            incident=incident,
            old_status=old_status,
            new_status=new_status,
            comment=cleaned_data.get('status_comment', '').strip(),
            changed_by=changed_by,
        )
    return incident
