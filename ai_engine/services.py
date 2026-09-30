"""Public service boundary for assistive AI triage."""

import logging

from django.conf import settings

from .fallback import classify_fallback
from .providers import generate_with_gemini
from .validators import validate_report_draft, validate_triage_result


logger = logging.getLogger(__name__)


def triage_issue(*, title, description, image=None, images=None, generate_report=False):
    """Return validated AI recommendations, or deterministic fallback values.

    Provider calls happen before issue creation starts its database transaction.
    Missing credentials, provider errors/timeouts, malformed JSON, and invalid
    model output all degrade to the local classifier.
    """
    fallback = classify_fallback(title=title, description=description)
    if not settings.AI_API_KEY:
        if generate_report:
            logger.warning("Image-assisted report drafting skipped: AI_API_KEY is not configured.")
            fallback["_draft_error"] = "missing_api_key"
        return fallback

    try:
        raw_response = generate_with_gemini(
            title=title,
            description=description,
            image=image,
            images=images,
            generate_report=generate_report,
        )
        return validate_report_draft(raw_response) if generate_report else validate_triage_result(raw_response)
    except Exception as exc:  # Provider and validation failures must not block reports.
        # Keep diagnostics useful without ever logging report text, image bytes,
        # credentials, or provider request payloads.
        safe_detail = str(exc).replace(settings.AI_API_KEY, "[redacted]")
        for report_text in (title, description):
            if report_text:
                safe_detail = safe_detail.replace(report_text, "[report text redacted]")
        safe_detail = safe_detail[:400]
        provider_status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        logger.warning(
            "Gemini request failed; using deterministic fallback "
            "(provider=Gemini, model=%s, http_status=%s, exception=%s, detail=%s).",
            settings.AI_MODEL, provider_status, type(exc).__name__, safe_detail,
        )
        if generate_report:
            if getattr(exc, "code", None) == 429:
                error_detail = safe_detail.lower()
                if "free_tier" in error_detail:
                    fallback["_draft_error"] = "free_tier_quota_exhausted"
                elif "quota exceeded" in error_detail:
                    fallback["_draft_error"] = "quota_exhausted"
                else:
                    fallback["_draft_error"] = "rate_limited"
            else:
                fallback["_draft_error"] = "provider_unavailable"
        return fallback
