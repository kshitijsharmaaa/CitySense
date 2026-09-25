# CitySense Agent Instructions

## Project

CitySense is an AI-assisted civic issue intelligence and resolution
platform for a 36-hour hackathon.

## Core Principle

Do NOT build a generic CRUD complaint system.

The core value is:

Unstructured Reports
→ AI Understanding
→ Duplicate Detection
→ Incident Aggregation
→ Prioritization
→ Action

## Team

### Backend + Intelligence Owner

Responsible for:

- Django backend
- PostgreSQL
- models
- authentication
- authorization
- business logic
- AI
- duplicate detection
- incident aggregation
- severity logic
- backend tests

### Frontend + UX Owner

Responsible for:

- Django templates
- Bootstrap
- CSS
- JavaScript
- UX
- Leaflet
- Chart.js
- visual integration

## Stack

- Python
- Django
- PostgreSQL
- Django Templates
- Bootstrap 5
- Vanilla JavaScript
- Leaflet
- Chart.js
- Multimodal AI API

## Architecture

Use a modular Django monolith.

## Do NOT introduce

- React
- Vite
- microservices
- Celery
- Redis
- WebSockets
- Kubernetes
- unnecessary infrastructure
- custom ML training

## AI Rules

- AI is assistive.
- Validate all AI output.
- Never expose API keys.
- Use environment variables.
- AI failure must not prevent issue creation.
- Always provide deterministic fallback logic.

## Security

- Use server-side authorization.
- Validate uploaded files.
- Protect authenticated routes.
- Never commit .env.
- Never hardcode secrets.

## Development Rules

1. Inspect the current project before changing files.
2. Work milestone by milestone.
3. Do not build the whole system in one operation.
4. Do not rewrite working code unnecessarily.
5. Do not modify another teammate's area without reason.
6. Run checks/tests after implementation.
7. Report files changed.
8. Do not claim a feature works unless tested.

## GitHub

GitHub is part of hackathon evaluation.

Create meaningful commits after milestones.

Examples:

- chore: initialize CitySense project
- feat: add issue reporting
- feat: add AI triage
- feat: add incident detection
- fix: handle AI fallback

Never commit secrets.

Never rewrite history.

## Timeline

Hour 0–2:
Architecture and foundation

Hour 2–12:
Core application

Hour 12–20:
AI and intelligence

Hour 20–28:
Integration and polish

Hour 28–34:
Testing and deployment

Hour 34–36:
Demo and submission