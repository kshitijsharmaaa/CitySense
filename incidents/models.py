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
from django.db import models
from django.utils import timezone

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
