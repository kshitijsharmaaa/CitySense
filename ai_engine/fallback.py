"""Small, deterministic and explainable fallback triage classifier."""

import re


_CATEGORY_RULES = (
    (re.compile(r"\b(?:potholes?|road holes?)\b"), "Pothole", "Road Maintenance"),
    (re.compile(r"\b(?:garbage|trash|waste)\b"), "Garbage", "Sanitation"),
    (
        re.compile(r"\b(?:streetlights?|street lamps?|light not working)\b"),
        "Streetlight",
        "Electrical",
    ),
    (
        re.compile(r"\b(?:water leak(?:age|ing)?|leaking pipe)\b"),
        "Water Leakage",
        "Water Supply",
    ),
    (re.compile(r"\b(?:drain|drainage)\b"), "Drainage", "Drainage"),
    (re.compile(r"\b(?:road damage|road damaged|damaged road)\b"), "Road Damage", "Road Maintenance"),
)
_CRITICAL_PRIORITY = re.compile(r"\b(?:electrocution|explosion|fire|life threatening|collapse|collapsed)\b")
_HIGH_PRIORITY = re.compile(
    r"\b(?:urgent|severe|dangerous|flood|accident|injur(?:y|ies)|exposed wire)\b"
)


def classify_fallback(*, title, description):
    """Return deterministic recommendation values when AI is unavailable/invalid."""
    text = f"{title} {description}".lower()
    category, department = "Other", "General"
    for pattern, matched_category, matched_department in _CATEGORY_RULES:
        if pattern.search(text):
            category, department = matched_category, matched_department
            break

    if _CRITICAL_PRIORITY.search(text):
        priority = "CRITICAL"
    elif _HIGH_PRIORITY.search(text):
        priority = "HIGH"
    else:
        priority = "MEDIUM"

    summary = " ".join(description.split())[:1000]
    if len(summary) == 1000:
        summary = summary[:997].rstrip() + "..."

    return {
        "category": category,
        "priority": priority,
        "department": department,
        "summary": summary or "No description provided.",
        "confidence": 0.55 if category != "Other" else 0.2,
    }
