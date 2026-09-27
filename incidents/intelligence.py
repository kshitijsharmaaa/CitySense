"""Deterministic incident matching and explainable severity scoring."""

import math
import re
from dataclasses import dataclass
from datetime import timedelta
from difflib import SequenceMatcher

from django.db.models import Prefetch
from django.utils import timezone

from issues.models import Issue, Priority

from .models import Incident, IncidentStatus


# Matching policy is centralized here so it can be tuned without changing the
# scoring algorithm or allowing an AI response to decide incident association.
MATCH_WINDOW_DAYS = 30
MATCH_RADIUS_KM = 0.5
DUPLICATE_THRESHOLD = 0.60
CATEGORY_WEIGHT = 0.35
LOCATION_WEIGHT = 0.35
TEXT_WEIGHT = 0.25
RECENCY_WEIGHT = 0.05

_STOP_WORDS = {
    "a", "an", "and", "at", "by", "for", "from", "in", "is", "it",
    "near", "of", "on", "or", "the", "to", "with",
}
_PRIORITY_POINTS = {
    Priority.LOW: 5,
    Priority.MEDIUM: 12,
    Priority.HIGH: 22,
    Priority.CRITICAL: 30,
}


@dataclass(frozen=True)
class IncidentMatch:
    incident: Incident
    score: float
    reasons: dict


@dataclass(frozen=True)
class SeverityAssessment:
    score: float
    factors: dict


def _tokens(value):
    return {
        token for token in re.findall(r"[a-z0-9]+", (value or "").casefold())
        if len(token) > 1 and token not in _STOP_WORDS
    }


def _text_similarity(left, right):
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    sequence = SequenceMatcher(None, " ".join(sorted(left_tokens)), " ".join(sorted(right_tokens))).ratio()
    return max(jaccard, sequence)


def _coordinates(latitude, longitude):
    if latitude is None or longitude is None:
        return None
    return float(latitude), float(longitude)


def _distance_km(first, second):
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    lat_delta, lon_delta = lat2 - lat1, lon2 - lon1
    haversine = (
        math.sin(lat_delta / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(lon_delta / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(haversine)))


def score_incident_match(issue, incident, *, now=None):
    """Return a weighted score and the concrete signals behind it.

    A concrete category match is required. Coordinates contribute only when
    both reports have valid coordinate pairs; absent coordinates do not count
    as evidence of proximity.
    """
    now = now or timezone.now()
    related_issues = list(incident.issues.all())
    categories = {incident.category}
    categories.update(item.ai_category for item in related_issues if item.ai_category)
    categories.discard("Other")
    current_category_match = bool(
        issue.ai_category
        and issue.ai_category != "Other"
        and issue.ai_category in categories
    )
    identical_report_category_match = any(
        item.title == issue.title
        and item.description == issue.description
        and item.ai_category in categories
        for item in related_issues
    )
    category_match = current_category_match or identical_report_category_match
    category_match_source = (
        "current_issue" if current_category_match
        else "identical_prior_report" if identical_report_category_match
        else None
    )

    new_location = _coordinates(issue.latitude, issue.longitude)
    incident_locations = [
        location for location in (
            _coordinates(item.latitude, item.longitude) for item in related_issues
        ) if location
    ]
    incident_location = _coordinates(incident.latitude, incident.longitude)
    if incident_location:
        incident_locations.append(incident_location)
    distances = [_distance_km(new_location, location) for location in incident_locations] if new_location else []
    distance_km = min(distances) if distances else None
    nearby = distance_km is not None and distance_km <= MATCH_RADIUS_KM
    location_similarity = (
        max(0.0, 1.0 - (distance_km / MATCH_RADIUS_KM) * 0.5) if nearby else 0.0
    )

    new_text = f"{issue.title} {issue.description}"
    existing_texts = [incident.title]
    existing_texts.extend(f"{item.title} {item.description}" for item in related_issues)
    text_similarity = max((_text_similarity(new_text, text) for text in existing_texts), default=0.0)

    age_days = max(0.0, (now - incident.created_at).total_seconds() / 86400)
    recency = max(0.0, 1.0 - age_days / MATCH_WINDOW_DAYS)
    score = (
        (CATEGORY_WEIGHT if category_match else 0.0)
        + LOCATION_WEIGHT * location_similarity
        + TEXT_WEIGHT * text_similarity
        + RECENCY_WEIGHT * recency
    )
    return IncidentMatch(
        incident=incident,
        score=round(score, 4),
        reasons={
            "category_match": category_match,
            "category_match_source": category_match_source,
            "distance_km": round(distance_km, 3) if distance_km is not None else None,
            "within_location_radius": nearby,
            "text_similarity": round(text_similarity, 4),
            "incident_age_days": round(age_days, 2),
            "score_threshold": DUPLICATE_THRESHOLD,
            "threshold_met": category_match and score >= DUPLICATE_THRESHOLD,
        },
    )


def find_related_incident(issue, *, now=None):
    """Return the best explainable match among active, recent incidents."""
    now = now or timezone.now()
    candidates = (
        Incident.objects.select_for_update()
        .filter(created_at__gte=now - timedelta(days=MATCH_WINDOW_DAYS))
        .exclude(status__in=(IncidentStatus.RESOLVED, IncidentStatus.REJECTED))
        .prefetch_related(Prefetch("issues", queryset=Issue.objects.only(
            "id", "incident_id", "title", "description", "ai_category", "latitude", "longitude",
        )))
        .order_by("-created_at", "-pk")
    )
    assessments = [score_incident_match(issue, candidate, now=now) for candidate in candidates]
    if not assessments:
        return None
    best = max(assessments, key=lambda item: (item.score, item.incident.created_at, item.incident.pk))
    if best.reasons["threshold_met"]:
        return best
    return None


def calculate_incident_severity(incident, issues=None, *, now=None):
    """Compute a transparent 0–100 urgency score without changing admin fields."""
    now = now or timezone.now()
    issues = list(issues if issues is not None else incident.issues.all())
    priorities = [incident.priority]
    priorities.extend(item.ai_priority for item in issues if item.ai_priority)
    priority = max(priorities, key=lambda value: _PRIORITY_POINTS.get(value, 0))

    report_points = min(max(len(issues) - 1, 0) * 5, 25)
    priority_points = _PRIORITY_POINTS.get(priority, 0)
    first_report = min((item.created_at for item in issues), default=incident.created_at)
    age_days = max(0.0, (now - first_report).total_seconds() / 86400)
    persistence_points = min(age_days / 7, 1.0) * 10
    has_location = any(item.latitude is not None and item.longitude is not None for item in issues)
    if not has_location:
        has_location = incident.latitude is not None and incident.longitude is not None
    location_points = 5 if has_location else 0

    factors = {
        "base_points": 20,
        "additional_report_points": report_points,
        "highest_priority": priority,
        "priority_points": priority_points,
        "persistence_days": round(age_days, 2),
        "persistence_points": round(persistence_points, 2),
        "location_present": has_location,
        "location_points": location_points,
    }
    score = min(100.0, 20 + report_points + priority_points + persistence_points + location_points)
    return SeverityAssessment(score=round(score, 2), factors=factors)
