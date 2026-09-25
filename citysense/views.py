"""
CitySense project-level views.

Currently only the /health/ endpoint lives here.
All other business-logic views belong in their respective apps.
"""

import json

from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health_check(request):
    """
    GET /health/

    Returns HTTP 200 with a JSON payload.
    Used by CI, monitoring, and the team to confirm the server is up.
    No authentication required.
    """
    return JsonResponse(
        {
            "status": "ok",
            "service": "CitySense",
        }
    )
