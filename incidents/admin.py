"""
incidents/admin.py

Django admin for Incident and IncidentStatusHistory models.
"""

from django.contrib import admin

from .models import Incident, IncidentStatusHistory


class IncidentStatusHistoryInline(admin.TabularInline):
    """Show status history inline on the Incident detail page."""
    model = IncidentStatusHistory
    extra = 0
    readonly_fields = ("old_status", "new_status", "comment", "changed_by", "created_at")
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
        "created_at",
    )
    list_filter = ("status", "priority", "category", "department")
    search_fields = ("incident_code", "title")
    readonly_fields = ("incident_code", "created_at", "updated_at", "report_count")
    ordering = ("-created_at",)
    inlines = [IncidentStatusHistoryInline]

    fieldsets = (
        ("Identity", {"fields": ("incident_code", "title")}),
        ("Classification", {"fields": ("category", "priority", "status")}),
        ("Assignment", {"fields": ("department", "assigned_to")}),
        ("Location", {"fields": ("latitude", "longitude")}),
        ("Intelligence", {"fields": ("severity_score", "report_count")}),
        ("Resolution", {"fields": ("resolution_notes", "resolved_at")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(IncidentStatusHistory)
class IncidentStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("incident", "old_status", "new_status", "changed_by", "created_at")
    list_filter = ("new_status",)
    search_fields = ("incident__incident_code",)
    readonly_fields = ("incident", "old_status", "new_status", "changed_by", "created_at")
    ordering = ("-created_at",)
