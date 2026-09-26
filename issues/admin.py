"""
issues/admin.py

Django admin for Department and Issue models.
"""

from django.contrib import admin

from .models import Department, Issue


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = (
        "issue_code",
        "title",
        "reported_by",
        "ai_category",
        "ai_priority",
        "incident",
        "created_at",
    )
    list_filter = ("ai_category", "ai_priority")
    search_fields = ("issue_code", "title", "description", "reported_by__email")
    readonly_fields = ("issue_code", "created_at", "updated_at")
    ordering = ("-created_at",)

    fieldsets = (
        ("Identity", {"fields": ("issue_code", "reported_by")}),
        ("Citizen report", {"fields": ("title", "description", "image", "latitude", "longitude")}),
        (
            "AI suggestions",
            {
                "fields": ("ai_category", "ai_priority", "ai_department", "ai_summary", "ai_confidence"),
                "description": "These are AI suggestions only — not the final incident classification.",
            },
        ),
        ("Incident association", {"fields": ("incident",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
