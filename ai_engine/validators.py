"""Validation for untrusted AI triage output."""

import json
import math
from collections.abc import Mapping

from .prompts import ALLOWED_CATEGORIES, ALLOWED_DEPARTMENTS, ALLOWED_PRIORITIES


class TriageValidationError(ValueError):
    """Raised when a provider response is not a valid triage recommendation."""


EXPECTED_KEYS = {"category", "priority", "department", "summary", "confidence"}


def validate_triage_result(candidate):
    """Parse JSON if needed and return a strict, normalized triage structure."""
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except (json.JSONDecodeError, TypeError) as exc:
            raise TriageValidationError("AI response is not valid JSON.") from exc

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
