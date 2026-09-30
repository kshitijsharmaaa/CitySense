"""Validation for untrusted AI triage output."""

import json
import math
import re
from collections.abc import Mapping

from .prompts import ALLOWED_CATEGORIES, ALLOWED_DEPARTMENTS, ALLOWED_PRIORITIES


class TriageValidationError(ValueError):
    """Raised when a provider response is not a valid triage recommendation."""


EXPECTED_KEYS = {"category", "priority", "department", "summary", "confidence"}
REPORT_DRAFT_KEYS = {"generated_title", "generated_description"}


def _parse_candidate(candidate):
    if isinstance(candidate, str):
        candidate = candidate.strip()
        fenced_json = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.IGNORECASE | re.DOTALL)
        if fenced_json:
            candidate = fenced_json.group(1)
        try:
            candidate = json.loads(candidate)
        except (json.JSONDecodeError, TypeError) as exc:
            raise TriageValidationError("AI response is not valid JSON.") from exc
    if not isinstance(candidate, Mapping):
        raise TriageValidationError("AI response has an invalid structure.")
    return candidate


def validate_triage_result(candidate):
    """Parse JSON if needed and return a strict, normalized triage structure."""
    candidate = _parse_candidate(candidate)

    if not isinstance(candidate, Mapping) or set(candidate) != EXPECTED_KEYS:
        raise TriageValidationError("AI response has an invalid structure.")

    for field, allowed in (
        ("category", ALLOWED_CATEGORIES),
        ("priority", ALLOWED_PRIORITIES),
        ("department", ALLOWED_DEPARTMENTS),
    ):
        value = candidate[field]
        if not isinstance(value, str) or value not in allowed:
            raise TriageValidationError(f"AI response contains an invalid {field}.")

    summary = candidate["summary"]
    if not isinstance(summary, str) or not summary.strip() or len(summary.strip()) > 1000:
        raise TriageValidationError("AI response contains an invalid summary.")

    confidence = candidate["confidence"]
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        raise TriageValidationError("AI response contains invalid confidence.")

    return {
        "category": candidate["category"],
        "priority": candidate["priority"],
        "department": candidate["department"],
        "summary": summary.strip(),
        "confidence": float(confidence),
    }


def validate_report_draft(candidate):
    """Validate triage plus an editable, citizen-facing title and description."""
    candidate = _parse_candidate(candidate)
    if set(candidate) != EXPECTED_KEYS | REPORT_DRAFT_KEYS:
        raise TriageValidationError("AI report draft has an invalid structure.")

    validated = validate_triage_result({key: candidate[key] for key in EXPECTED_KEYS})
    title = candidate["generated_title"]
    description = candidate["generated_description"]
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 255:
        raise TriageValidationError("AI response contains an invalid generated title.")
    if not isinstance(description, str) or not description.strip() or len(description.strip()) > 2000:
        raise TriageValidationError("AI response contains an invalid generated description.")
    validated["generated_title"] = title.strip()
    validated["generated_description"] = description.strip()
    return validated
