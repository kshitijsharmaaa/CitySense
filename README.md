# CitySense

> See the problem. Understand the issue. Drive the action.

CitySense is an AI-assisted civic issue intelligence and resolution
platform.

## Problem

Civic issues are often reported as fragmented and unstructured
complaints. Multiple reports may also represent the same underlying
problem.

## Solution

CitySense transforms citizen descriptions, images and locations into
structured civic incidents using AI and location-based intelligence.

## Core Workflow

Citizen Report
→ AI Triage Recommendation
→ Duplicate Detection
→ Incident Aggregation
→ Prioritization
→ Department Assignment
→ Resolution
→ Citizen Tracking

## Planned Features

- Citizen issue reporting
- AI-assisted triage
- Duplicate detection
- Incident aggregation
- Priority assessment
- Department routing
- Map visualization
- Transparent status tracking
- Admin dashboard

## Tech Stack

- Python
- Django
- PostgreSQL
- Django Templates
- Bootstrap 5
- Vanilla JavaScript
- Leaflet
- Chart.js
- Multimodal AI API

## Project Status

Phases 1–3 are complete. Phase 4 implements AI Smart Triage: category,
priority, department, summary, and confidence are stored as recommendations
on each Issue. Administrators retain final authority over Incident
classification and department. If the provider is unavailable or returns
invalid output, a deterministic keyword fallback keeps report submission
working.

Duplicate detection, incident aggregation, severity scoring, admin workflow,
maps, analytics, and deployment are not implemented yet.

The Gemini provider uses the server-side `AI_API_KEY`, `AI_MODEL`, and
`AI_TIMEOUT_SECONDS` settings. Provider integration is isolated in
`ai_engine`; credentials are never sent to browser code.

## Team

Two-person team.
