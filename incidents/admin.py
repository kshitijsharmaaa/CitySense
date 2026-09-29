"""
incidents/admin.py

Django admin for Incident and IncidentStatusHistory models.
"""

from django.contrib import admin

from .models import Incident, IncidentSLAConfiguration, IncidentStatusHistory


class IncidentStatusHistoryInline(admin.TabularInline):
    """Show status history inline on the Incident detail page."""
    model = IncidentStatusHistory
    extra = 0
    readonly_fields = (
        "event_type", "old_status", "new_status", "previous_escalation_level", "new_escalation_level",
        "reason", "assigned_from", "assigned_to", "department_from", "department_to",
        "comment", "changed_by", "created_at",
    )
    can_delete = False


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = (
        "incident_code",
        "title",
        "category",
        "priority",
        "status",
        "department",
        "report_count",
        "sla_started_at",
        "resolution_deadline",
        "sla_overdue",
        "escalation_level",
        "l1_escalated_at",
        "l2_escalated_at",
        "created_at",
    )
    list_filter = ("status", "priority", "category", "department")
    search_fields = ("incident_code", "title")
    readonly_fields = (
        "incident_code", "created_at", "updated_at", "report_count", "sla_started_at",
        "resolution_deadline", "sla_overdue", "escalation_level", "l1_escalated_at", "l2_escalated_at",
    )
    ordering = ("-created_at",)
    inlines = [IncidentStatusHistoryInline]

    fieldsets = (
        ("Identity", {"fields": ("incident_code", "title")}),
        ("Classification", {"fields": ("category", "priority", "status")}),
        ("Assignment", {"fields": ("department", "assigned_to")}),
        ("SLA and escalation", {"fields": (
            "sla_started_at", "resolution_deadline", "sla_overdue", "escalation_level",
            "l1_escalated_at", "l2_escalated_at",
        )}),
        ("Location", {"fields": ("latitude", "longitude")}),
        ("Intelligence", {"fields": ("severity_score", "report_count")}),
        ("Resolution", {"fields": ("resolution_notes", "resolved_at")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(IncidentStatusHistory)
class IncidentStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("incident", "event_type", "old_status", "new_status", "new_escalation_level", "changed_by", "created_at")
    list_filter = ("event_type", "new_status", "new_escalation_level")
    search_fields = ("incident__incident_code", "reason", "comment")
    readonly_fields = (
        "incident", "event_type", "old_status", "new_status", "previous_escalation_level",
        "new_escalation_level", "reason", "assigned_from", "assigned_to", "department_from",
        "department_to", "changed_by", "created_at",
    )
    ordering = ("-created_at",)


@admin.register(IncidentSLAConfiguration)
class IncidentSLAConfigurationAdmin(admin.ModelAdmin):
    list_display = ("priority", "category", "resolution_days", "l2_after_days")
    list_filter = ("priority", "category")
    ordering = ("priority", "category")
