"""
incidents/models.py

Incident and IncidentStatusHistory models.

ARCHITECTURAL NOTE:
- Incident = the underlying civic problem that administrators manage and resolve.
- An Incident may aggregate many citizen Issues that describe the same problem.
- Status, priority, category, and department on Incident are the FINAL,
  administrator-controlled values — not AI suggestions.
- IncidentStatusHistory records every status transition for auditability.
"""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from datetime import timedelta

# Import shared choices from issues to keep them canonical and DRY
from issues.models import Category, Department, Priority


# ---------------------------------------------------------------------------
# STATUS CHOICES (Incident-specific)
# ---------------------------------------------------------------------------

class IncidentStatus(models.TextChoices):
    REPORTED = "REPORTED", "Reported"
    VERIFIED = "VERIFIED", "Verified"
    ASSIGNED = "ASSIGNED", "Assigned"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    RESOLVED = "RESOLVED", "Resolved"
    REJECTED = "REJECTED", "Rejected"


class EscalationLevel(models.TextChoices):
    NORMAL = "NORMAL", "Normal"
    L1 = "L1", "Level 1"
    L2 = "L2", "Level 2"


class HistoryEventType(models.TextChoices):
    STATUS = "STATUS", "Status change"
    ESCALATION = "ESCALATION", "SLA escalation"


class IncidentSLAConfiguration(models.Model):
    """Priority defaults and optional category-specific SLA overrides."""

    priority = models.CharField(max_length=10, choices=Priority.choices)
    # Empty category means the priority-wide default.
    category = models.CharField(max_length=50, choices=Category.choices, blank=True, default="")
    resolution_days = models.PositiveSmallIntegerField(
        default=7, validators=[MinValueValidator(1)],
        help_text="Calendar days from SLA start until the first escalation.",
    )
    l2_after_days = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1)],
        help_text="Calendar days after L1 escalation before routing to L2.",
    )

    class Meta:
        ordering = ("priority", "category")
        constraints = [models.UniqueConstraint(
            fields=("priority", "category"), name="unique_incident_sla_priority_category",
        )]
        verbose_name = "Incident SLA configuration"
        verbose_name_plural = "Incident SLA configurations"

    def __str__(self):
        scope = self.category or "all categories"
        return f"{self.get_priority_display()} / {scope}: {self.resolution_days} days"


# ---------------------------------------------------------------------------
# INCIDENT
# ---------------------------------------------------------------------------

class Incident(models.Model):
    """
    An Incident represents the underlying civic problem.

    Key points:
    - One Incident can aggregate many Issues (citizen reports).
    - Status, category, priority, department and assignment belong here —
      these are the definitive resolution-facing values.
    - severity_score and report_count are computed/updated by the backend
      intelligence pipeline (Phase 3).
    - resolved_at is set when status transitions to RESOLVED.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    incident_code = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        verbose_name="Incident code",
        help_text="Human-readable code e.g. INC-1001. Auto-generated on save.",
    )
    title = models.CharField(max_length=255, verbose_name="Incident title")

    # ------------------------------------------------------------------
    # Classification (administrator-controlled)
    # ------------------------------------------------------------------
    category = models.CharField(
        max_length=50,
        choices=Category.choices,
        default=Category.OTHER,
        verbose_name="Category",
    )
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        verbose_name="Priority",
    )
    status = models.CharField(
        max_length=20,
        choices=IncidentStatus.choices,
        default=IncidentStatus.REPORTED,
        verbose_name="Status",
    )

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidents",
        verbose_name="Responsible department",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_incidents",
        verbose_name="Assigned to",
    )

    # ------------------------------------------------------------------
    # Service-level agreement and escalation
    # ------------------------------------------------------------------
    sla_started_at = models.DateTimeField(null=True, blank=True, verbose_name="SLA started at")
    resolution_deadline = models.DateTimeField(null=True, blank=True, verbose_name="Resolution deadline")
    sla_overdue = models.BooleanField(default=False, verbose_name="SLA overdue")
    escalation_level = models.CharField(
        max_length=10, choices=EscalationLevel.choices, default=EscalationLevel.NORMAL,
        verbose_name="Escalation level",
    )
    l1_escalated_at = models.DateTimeField(null=True, blank=True, verbose_name="L1 escalated at")
    l2_escalated_at = models.DateTimeField(null=True, blank=True, verbose_name="L2 escalated at")

    # ------------------------------------------------------------------
    # Location (representative location for the incident)
    # ------------------------------------------------------------------
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Latitude",
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Longitude",
    )

    # ------------------------------------------------------------------
    # Intelligence (populated by AI/severity pipeline in Phase 3)
    # ------------------------------------------------------------------
    severity_score = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Severity score",
        help_text="Computed by the severity pipeline. Higher = more urgent.",
    )
    report_count = models.PositiveIntegerField(
        default=1,
        verbose_name="Report count",
        help_text="Number of citizen issues associated with this incident.",
    )

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------
    resolution_notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Resolution notes",
    )
    resolution_image = models.ImageField(
        upload_to="incidents/resolutions/%Y/%m/",
        null=True,
        blank=True,
        verbose_name="Resolution photo",
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Resolved at",
    )

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Created at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Last updated")

    class Meta:
        verbose_name = "Incident"
        verbose_name_plural = "Incidents"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.incident_code} — {self.title} [{self.status}]"

    def save(self, *args, **kwargs):
        """Auto-generate incident_code on first save: INC-1001, INC-1002 …"""
        if not self.incident_code:
            if not self.sla_started_at:
                self.sla_started_at = self.created_at or timezone.now()
            if not self.resolution_deadline:
                configuration = IncidentSLAConfiguration.objects.filter(
                    priority=self.priority, category=self.category,
                ).first() or IncidentSLAConfiguration.objects.filter(
                    priority=self.priority, category="",
                ).first()
                default_days = {
                    Priority.CRITICAL: 1,
                    Priority.HIGH: 3,
                    Priority.MEDIUM: 7,
                    Priority.LOW: 14,
                }.get(self.priority, 7)
                self.resolution_deadline = self.sla_started_at + timedelta(
                    days=configuration.resolution_days if configuration else default_days
                )
            super().save(*args, **kwargs)          # get pk first
            self.incident_code = f"INC-{1000 + self.pk}"
            Incident.objects.filter(pk=self.pk).update(incident_code=self.incident_code)
        else:
            super().save(*args, **kwargs)

    def update_report_count(self):
        """
        Recalculate report_count from associated Issues.
        Called by the issue association logic in Phase 3.
        """
        count = self.issues.count()
        self.report_count = max(count, 1)
        Incident.objects.filter(pk=self.pk).update(report_count=self.report_count)


# ---------------------------------------------------------------------------
# INCIDENT STATUS HISTORY
# ---------------------------------------------------------------------------

class IncidentStatusHistory(models.Model):
    """
    Audit trail of every status transition on an Incident.

    Created automatically whenever an Incident's status changes.
    Provides administrators and citizens with a transparent timeline.
    """

    incident = models.ForeignKey(
        Incident,
        on_delete=models.CASCADE,
        related_name="status_history",
        verbose_name="Incident",
    )
    old_status = models.CharField(
        max_length=20,
        choices=IncidentStatus.choices,
        blank=True,
        default="",
        verbose_name="Previous status",
    )
    new_status = models.CharField(
        max_length=20,
        choices=IncidentStatus.choices,
        verbose_name="New status",
    )
    comment = models.TextField(blank=True, default="", verbose_name="Comment")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="status_changes",
        verbose_name="Changed by",
    )
    event_type = models.CharField(
        max_length=12, choices=HistoryEventType.choices, default=HistoryEventType.STATUS,
        verbose_name="Event type",
    )
    previous_escalation_level = models.CharField(
        max_length=10, choices=EscalationLevel.choices, blank=True, default="",
    )
    new_escalation_level = models.CharField(
        max_length=10, choices=EscalationLevel.choices, blank=True, default="",
    )
    reason = models.TextField(blank=True, default="", verbose_name="Audit reason")
    assigned_from = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="incident_escalations_from", verbose_name="Previously assigned officer",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="incident_escalations_to", verbose_name="Escalated to officer",
    )
    department_from = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="incident_escalations_from", verbose_name="Original department",
    )
    department_to = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="incident_escalations_to", verbose_name="Routed department",
    )
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Changed at")

    class Meta:
        verbose_name = "Incident status history"
        verbose_name_plural = "Incident status histories"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.incident.incident_code}: "
            f"{self.old_status or '—'} → {self.new_status} "
            f"at {self.created_at:%Y-%m-%d %H:%M}"
        )
