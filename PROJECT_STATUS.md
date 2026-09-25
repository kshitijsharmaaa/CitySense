# CitySense Development Status

## Current Phase

PHASE 3 IMPLEMENTED — Citizen Reporting Workflow (verification pending)

## Completed

- [x] GitHub repository created
- [x] Repository cloned locally
- [x] Initial project documentation planned
- [x] **Phase 1**: Django project `citysense` scaffolded
- [x] **Phase 1**: Apps created: `accounts`, `issues`, `incidents`, `ai_engine`, `dashboard`
- [x] **Phase 1**: `settings.py` — env vars, all apps, static/media, DB config
- [x] **Phase 1**: PostgreSQL via `DATABASE_URL` with SQLite dev fallback
- [x] **Phase 1**: Root URL routing with namespaced app includes
- [x] **Phase 1**: `/health/` endpoint — verified HTTP 200
- [x] **Phase 1**: `requirements.txt` created
- [x] **Phase 1**: `.env.example` updated with all variables
- [x] **Phase 1**: `manage.py check` — 0 issues
- [x] **Phase 1**: Committed: `chore: scaffold CitySense Django backend`
- [x] **Phase 2**: Custom user model (`CitySenseUser`) — email auth, CITIZEN/ADMIN roles
- [x] **Phase 2**: `AUTH_USER_MODEL = 'accounts.CitySenseUser'` set before migrations
- [x] **Phase 2**: `Department` model — shared lookup, 6 seeded departments (via tests/admin)
- [x] **Phase 2**: `Issue` model — citizen report with AI suggestion fields, CIV-NNNN codes
- [x] **Phase 2**: `Incident` model — civic problem, administrator-controlled, INC-NNNN codes
- [x] **Phase 2**: `IncidentStatusHistory` model — full audit trail of status transitions
- [x] **Phase 2**: Django admin configured for all models
- [x] **Phase 2**: Migrations created and applied successfully
- [x] **Phase 2**: 28 backend tests — all pass (0 failures)
- [x] **Phase 2**: `API_CONTRACT.md` updated with full field documentation
- [x] **Phase 2**: `TECHNICAL_NOTES.md` updated with architectural notes
- [x] **Phase 2**: Committed: `feat: implement CitySense core data model`
- [x] **Phase 3**: Citizen registration, email login and POST logout
- [x] **Phase 3**: Authenticated citizen dashboard and private issue list/detail
- [x] **Phase 3**: Validated issue submission with optional bounded location and image
- [x] **Phase 3**: Every new Issue gets its own `Other` / `MEDIUM` / `General` / `REPORTED` Incident
- [x] **Phase 3**: Issue and Incident creation plus initial status history are transactional
- [x] **Phase 3**: Citizen-scoped incident details and read-only status history
- [x] **Phase 3**: Minimal functional templates for the citizen workflow
- [x] **Phase 3**: Phase 3 test coverage added; execution pending a working local Pillow install

## Verification

The current MSYS Python 3.14 environment could not build Pillow, which is required by Django `ImageField`. As a result, `manage.py check` and `manage.py test` stop during app loading. Re-run both commands in an environment with the declared dependencies installed before treating Phase 3 as verified.

## Not Started

- [ ] AI triage integration
- [ ] Duplicate detection
- [ ] Incident aggregation
- [ ] Severity scoring
- [ ] Admin workflow views
- [ ] Map visualization
- [ ] Analytics / charts
- [ ] Deployment

## Next Milestone

Phase 4 — AI triage and duplicate detection. These are not part of the current implementation.

Phase 3 intentionally creates a new Incident for each submitted Issue because AI classification and duplicate/incident aggregation are Phase 4/5 features.
