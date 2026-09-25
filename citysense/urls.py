"""
CitySense root URL configuration.

URL namespacing keeps each app's URLs isolated and avoids naming collisions.
The /health/ endpoint is unauthenticated and used by monitoring and CI.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from .views import health_check

urlpatterns = [
    # Health check — no auth required
    path("health/", health_check, name="health-check"),

    # Django admin (backend only)
    path("admin/", admin.site.urls),

    # CitySense apps (URLs wired up incrementally per milestone)
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path("issues/", include("issues.urls", namespace="issues")),
    path("incidents/", include("incidents.urls", namespace="incidents")),
    path("dashboard/", include("dashboard.urls", namespace="dashboard")),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
