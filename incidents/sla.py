"""Transactional SLA deadlines and idempotent officer escalations."""

import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import CitySenseUser

from .models import (
    EscalationLevel,
    HistoryEventType,
    Incident,
    IncidentSLAConfiguration,
    IncidentStatus,
    IncidentStatusHistory,
)

logger = logging.getLogger(__name__)

DEFAULT_SLA_DAYS = {
    "CRITICAL": (1, 1),
    "HIGH": (3, 2),
    "MEDIUM": (7, 3),
    "LOW": (14, 5),
}


def get_sla_configuration(*, priority, category):
    """Resolve an exact category override, then a priority-wide default."""
    configuration = IncidentSLAConfiguration.objects.filter(
        priority=priority, category=category,
    ).first()
    if configuration:
        return configuration
    configuration = IncidentSLAConfiguration.objects.filter(
        priority=priority, category="",
    ).first()
    if configuration:
        return configuration

    resolution_days, l2_after_days = DEFAULT_SLA_DAYS.get(priority, (7, 3))
    return IncidentSLAConfiguration(
        priority=priority,
        category="",
        resolution_days=resolution_days,
        l2_after_days=l2_after_days,
    )


def set_sla_schedule(incident, *, started_at=None):
    """Set a new SLA clock, used on creation and when an admin reopens a case."""
    started_at = started_at or timezone.now()
    configuration = get_sla_configuration(priority=incident.priority, category=incident.category)
    incident.sla_started_at = started_at
    incident.resolution_deadline = started_at + timedelta(days=configuration.resolution_days)
    incident.sla_overdue = False
    incident.escalation_level = EscalationLevel.NORMAL
    incident.l1_escalated_at = None
    incident.l2_escalated_at = None
    return incident


def _officer_for(level):
    return CitySenseUser.objects.filter(
        role=CitySenseUser.Role.ADMIN,
        officer_level=level,
        is_active=True,
    ).order_by("created_at", "pk").first()


def _write_escalation(incident, *, new_level, officer, now, reason):
    previous_level = incident.escalation_level
    previous_officer = incident.assigned_to
    department = incident.department

    incident.escalation_level = new_level
    incident.assigned_to = officer
    if new_level == EscalationLevel.L1:
        incident.l1_escalated_at = now
    else:
        incident.l2_escalated_at = now

    fields = ["escalation_level", "assigned_to", "updated_at"]
    if new_level == EscalationLevel.L1:
        fields.append("l1_escalated_at")
    else:
        fields.append("l2_escalated_at")
    incident.save(update_fields=fields)

    IncidentStatusHistory.objects.create(
        incident=incident,
        old_status=incident.status,
        new_status=incident.status,
        event_type=HistoryEventType.ESCALATION,
        previous_escalation_level=previous_level,
        new_escalation_level=new_level,
        reason=reason,
        comment=reason,
        changed_by=None,  # A null user on an escalation event means CitySense system.
        assigned_from=previous_officer,
        assigned_to=officer,
        department_from=department,
        department_to=department,
        created_at=now,
    )


@transaction.atomic
def evaluate_due_escalations(*, now=None):
    """Mark overdue cases and route each overdue level once to its designated officer.

    The admin dashboard/detail views call this on access as the monolith's
    deterministic periodic mechanism. Row locks and level transitions make
    concurrent/repeated checks safe and prevent duplicate audit entries.
    """
    now = now or timezone.now()
    incidents = Incident.objects.select_for_update().select_related(
        "assigned_to", "department",
    ).filter(
        ~Q(status__in=(IncidentStatus.RESOLVED, IncidentStatus.REJECTED)),
    ).filter(
        Q(resolution_deadline__lt=now) | Q(escalation_level=EscalationLevel.L1),
    ).order_by("pk")

    escalated = 0
    for incident in incidents:
        if not incident.resolution_deadline:
            continue
        if incident.resolution_deadline < now and not incident.sla_overdue:
            incident.sla_overdue = True
            incident.save(update_fields=("sla_overdue", "updated_at"))

        if incident.escalation_level == EscalationLevel.NORMAL:
            if incident.resolution_deadline >= now:
                continue
            officer = _officer_for(CitySenseUser.OfficerLevel.L1)
            if not officer:
                logger.warning("Incident %s is overdue but no active L1 officer is configured.", incident.pk)
                continue
            reason = (
                f"Resolution SLA passed at {incident.resolution_deadline.isoformat()}; "
                "automatically routed to the designated L1 officer."
            )
            _write_escalation(
                incident, new_level=EscalationLevel.L1, officer=officer, now=now, reason=reason,
            )
            escalated += 1
            continue

        if incident.escalation_level == EscalationLevel.L1 and incident.l1_escalated_at:
            configuration = get_sla_configuration(priority=incident.priority, category=incident.category)
            l2_deadline = incident.l1_escalated_at + timedelta(days=configuration.l2_after_days)
            if now < l2_deadline:
                continue
            officer = _officer_for(CitySenseUser.OfficerLevel.L2)
            if not officer:
                logger.warning("Incident %s is due for L2 but no active L2 officer is configured.", incident.pk)
                continue
            reason = (
                f"The L1 escalation period passed at {l2_deadline.isoformat()} without resolution; "
                "automatically routed to the designated L2 officer."
            )
            _write_escalation(
                incident, new_level=EscalationLevel.L2, officer=officer, now=now, reason=reason,
            )
            escalated += 1

    return escalated
