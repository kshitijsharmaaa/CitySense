"""Public service boundary for assistive AI triage."""

import logging

from django.conf import settings

from .fallback import classify_fallback
from .providers import generate_with_gemini
from .validators import validate_triage_result


logger = logging.getLogger(__name__)


def triage_issue(*, title, description, image=None):
    """Return validated AI recommendations, or deterministic fallback values.

    Provider calls happen before issue creation starts its database transaction.
    Missing credentials, provider errors/timeouts, malformed JSON, and invalid
    model output all degrade to the local classifier.
    """
    fallback = classify_fallback(title=title, description=description)
    if not settings.AI_API_KEY:
        return fallback

    try:
        raw_response = generate_with_gemini(
            title=title,
            description=description,
            image=image,
        )
        return validate_triage_result(raw_response)
    except Exception as exc:  # Provider and validation failures must not block reports.
        logger.warning("AI triage failed; using deterministic fallback (%s).", type(exc).__name__)
        return fallback
