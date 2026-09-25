"""
issues/models.py

Department and Issue models.

ARCHITECTURAL NOTE:
- Issue = one citizen's raw report.
- Department is referenced by both Issue (AI suggestion) and Incident (final assignment).
- Department lives in this module because it is first referenced by the Issue model,
  but it is a shared lookup table used across the system.

AI fields on Issue represent SUGGESTIONS only.
Final incident classification is controlled by administrators on the Incident model.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# SHARED CHOICES
# (imported by incidents/models.py to keep choices canonical and DRY)
# ---------------------------------------------------------------------------

class Category(models.TextChoices):
    POTHOLE = "Pothole", "Pothole"
    GARBAGE = "Garbage", "Garbage"
    STREETLIGHT = "Streetlight", "Streetlight"
    WATER_LEAKAGE = "Water Leakage", "Water Leakage"
    DRAINAGE = "Drainage", "Drainage"
    ROAD_DAMAGE = "Road Damage", "Road Damage"
    OTHER = "Other", "Other"


class Priority(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"
    CRITICAL = "CRITICAL", "Critical"


# ---------------------------------------------------------------------------
# DEPARTMENT
# ---------------------------------------------------------------------------

class Department(models.Model):
    """
    A civic department responsible for resolving incidents.

    Instances are seeded via a data migration or management command.
    Administrators assign departments to Incidents; AI suggests them for Issues.
    """

    name = models.CharField(max_length=100, unique=True, verbose_name="Department name")
    description = models.TextField(blank=True, default="", verbose_name="Description")

    class Meta:
        verbose_name = "Department"
        verbose_name_plural = "Departments"
        ordering = ["name"]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# ISSUE
# ---------------------------------------------------------------------------

class Issue(models.Model):
    """
    An Issue represents one citizen's raw report of a civic problem.

    Key points:
    - Each report stands alone even if it describes the same underlying problem
      as other reports (duplicate detection happens later in the AI pipeline).
    - The `incident` FK is null until the backend associates this issue with
      an existing or newly created Incident.
    - AI fields store suggestions — they do NOT control the final Incident state.
    - Resolution information (status, department, assigned_to) belongs on Incident,
      NOT on Issue.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    issue_code = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        verbose_name="Issue code",
        help_text="Human-readable code e.g. CIV-1001. Auto-generated on save.",
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reported_issues",
        verbose_name="Reported by",
    )

    # ------------------------------------------------------------------
    # Raw citizen input
    # ------------------------------------------------------------------
    title = models.CharField(max_length=255, verbose_name="Title")
    description = models.TextField(verbose_name="Description")
    image = models.ImageField(
        upload_to="issues/images/%Y/%m/",
        null=True,
        blank=True,
        verbose_name="Photo",
    )
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
    # AI suggestions (NEVER automatically treated as final)
    # ------------------------------------------------------------------
    ai_category = models.CharField(
        max_length=50,
        choices=Category.choices,
        blank=True,
        default="",
        verbose_name="AI suggested category",
    )
    ai_priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        blank=True,
        default="",
        verbose_name="AI suggested priority",
    )
    ai_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_suggested_issues",
        verbose_name="AI suggested department",
    )
    ai_summary = models.TextField(blank=True, default="", verbose_name="AI summary")
    ai_confidence = models.FloatField(
        null=True,
        blank=True,
        verbose_name="AI confidence",
        help_text="0.0–1.0 confidence score returned by the AI model.",
    )

    # ------------------------------------------------------------------
    # Incident association (set by duplicate-detection / AI pipeline)
    # ------------------------------------------------------------------
    incident = models.ForeignKey(
        "incidents.Incident",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issues",
        verbose_name="Associated incident",
    )

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Reported at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Last updated")

    class Meta:
        verbose_name = "Issue"
        verbose_name_plural = "Issues"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.issue_code} — {self.title}"

    def save(self, *args, **kwargs):
        """Auto-generate issue_code on first save: CIV-1001, CIV-1002 …"""
        if not self.issue_code:
            super().save(*args, **kwargs)          # get pk first
            self.issue_code = f"CIV-{1000 + self.pk}"
            # Update only the code field to avoid a full resave loop
            Issue.objects.filter(pk=self.pk).update(issue_code=self.issue_code)
        else:
            super().save(*args, **kwargs)
