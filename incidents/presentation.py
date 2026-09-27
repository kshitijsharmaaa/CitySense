"""Presentation helpers derived from existing incident status and timestamps."""
from datetime import timedelta

from django.utils import timezone

from issues.models import Priority

from .models import IncidentStatus


PROGRESS_STAGES = (
    (IncidentStatus.REPORTED, "Report received"),
    (IncidentStatus.VERIFIED, "Verified"),
    (IncidentStatus.ASSIGNED, "Assigned"),
    (IncidentStatus.IN_PROGRESS, "Work in progress"),
    (IncidentStatus.RESOLVED, "Resolved"),
)

# Lightweight operational targets only; these are not policy or SLA guarantees.
PRIORITY_AGE_LIMITS = {
    Priority.CRITICAL: timedelta(hours=24),
    Priority.HIGH: timedelta(hours=48),
    Priority.MEDIUM: timedelta(days=3),
    Priority.LOW: timedelta(days=7),
}
DUE_SOON_FRACTION = 0.75

NEXT_ACTIONS = {
    IncidentStatus.REPORTED: "Verify this case",
    IncidentStatus.VERIFIED: "Assign a response team",
    IncidentStatus.ASSIGNED: "Begin work",
    IncidentStatus.IN_PROGRESS: "Record the resolution",
    IncidentStatus.RESOLVED: "Reopen if the problem returns",
    IncidentStatus.REJECTED: "No further action",
}


def _duration_label(duration):
    seconds = max(0, int(duration.total_seconds()))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f"{days} day" + ("" if days == 1 else "s")
    if hours:
        return f"{hours} hour" + ("" if hours == 1 else "s")
    return f"{max(1, minutes)} minute" + ("" if minutes == 1 else "s")


def complaint_age(started_at, priority, *, status, now=None):
    """Return an age and priority-based operational indicator for an open case."""
    if not started_at or status in (IncidentStatus.RESOLVED, IncidentStatus.REJECTED):
        return None
    now = now or timezone.now()
    elapsed = max(now - started_at, timedelta(0))
    limit = PRIORITY_AGE_LIMITS.get(priority, PRIORITY_AGE_LIMITS[Priority.MEDIUM])
    remaining = limit - elapsed
    if remaining <= timedelta(0):
        state = "overdue"
        attention_text = "Overdue by " + _duration_label(-remaining)
    elif elapsed >= limit * DUE_SOON_FRACTION:
        state = "due_soon"
        attention_text = "Due soon"
    else:
        state = "on_track"
        attention_text = "On track"
    return {
        "age_text": "Open for " + _duration_label(elapsed),
        "state": state,
        "attention_text": attention_text,
        "citizen_text": "Taking longer than expected" if state == "overdue" else "",
    }


def complaint_progress(status, history):
    """Build progress from recorded transitions; never synthesize status events."""
    entries = sorted(list(history), key=lambda entry: entry.created_at)
    if status == IncidentStatus.REJECTED:
        latest = entries[-1] if entries else None
        return {
            "is_closed": True,
            "closed_note": (
                latest.comment if latest and latest.new_status == IncidentStatus.REJECTED
                and latest.comment else ""
            ),
            "steps": [],
            "next_action": "",
            "latest_update": entries[-1] if entries else None,
        }

    status_index = {value: index for index, (value, _label) in enumerate(PROGRESS_STAGES)}
    current_event_index = max(
        (index for index, entry in enumerate(entries) if entry.new_status == status),
        default=None,
    )
    evidence = set()
    event_time = {}
    if current_event_index is not None:
        for entry in entries[:current_event_index + 1]:
            if entry.old_status:
                evidence.add(entry.old_status)
            evidence.add(entry.new_status)
            event_time[entry.new_status] = entry.created_at

    steps = []
    for value, label in PROGRESS_STAGES:
        is_current = value == status
        before_current = (
            value in evidence
            and value in status_index
            and status in status_index
            and status_index[value] < status_index[status]
        )
        steps.append({
            "status": value,
            "label": label,
            "is_current": is_current,
            "is_complete": bool(before_current),
            "occurred_at": event_time.get(value) if before_current or is_current else None,
        })

    return {
        "is_closed": False,
        "closed_note": "",
        "steps": steps,
        "next_action": NEXT_ACTIONS.get(status, ""),
        "latest_update": entries[-1] if entries else None,
    }
