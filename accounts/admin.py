"""
accounts/admin.py

Django admin configuration for the custom CitySenseUser model.

Follows Django's recommended pattern for custom user admin:
- Extends UserAdmin
- Overrides fieldsets to show email/name/role instead of username
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CitySenseUser


@admin.register(CitySenseUser)
class CitySenseUserAdmin(UserAdmin):
    model = CitySenseUser

    # Columns shown in the list view
    list_display = ("email", "name", "role", "is_staff", "is_active", "created_at")
    list_filter = ("role", "is_staff", "is_active")
    search_fields = ("email", "name")
    ordering = ("-created_at",)

    # Fields shown on the edit page
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("name",)}),
        ("Role", {"fields": ("role",)}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "created_at")}),
    )

    # Fields shown on the "add user" page
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "name", "role", "password1", "password2"),
            },
        ),
    )

    # created_at is auto-set — make it read-only in admin
    readonly_fields = ("created_at", "last_login")
