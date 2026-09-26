# CitySense Technical Notes

## Backend Architecture Decisions

### Django App Structure

| App | Owner | Purpose |
|---|---|---|
| `accounts` | Backend | Custom user model, email auth, CITIZEN/ADMIN roles |
| `issues` | Backend | Department lookup, citizen Issue reports |
| `incidents` | Backend | Incident aggregation, status lifecycle, history |
| `ai_engine` | Backend | AI triage and validated report suggestions |
| `dashboard` | Backend (logic) + Frontend (UI) | Phase 3 citizen report list; later admin analytics and workflows |

---

### Core Data Model: Issue vs Incident

This distinction is a **fundamental architectural decision** and must not be collapsed.

#### Issue
- One citizen's raw report
- Contains: description, image, location, AI suggestions
- AI fields (`ai_category`, `ai_priority`, `ai_department`, `ai_summary`, `ai_confidence`) are **suggestions only**
- An Issue may or may not be linked to an Incident
- Issues do NOT have a status field — they do not represent the resolution lifecycle

#### Incident
- The underlying civic problem (may aggregate many Issues)
- Contains: final category, priority, status, department assignment, resolution notes
- Status (`REPORTED → VERIFIED → ASSIGNED → IN_PROGRESS → RESOLVED`) belongs here
- `report_count` tracks how many Issues are linked
- `resolved_at` is set when status → RESOLVED

**Never put final resolution state on Issue. Never put status on Issue.**

---

### Custom User Model

```python
AUTH_USER_MODEL = "accounts.CitySenseUser"
```

- **Login identifier**: email (not username)
- **Roles**: `CITIZEN`, `ADMIN`
- **Password**: hashed by Django's `set_password()` — never stored plaintext
- **Admin support**: via `PermissionsMixin` and custom `UserAdmin`
- Must be set in `settings.py` **before** the first migration

---

### Shared Choices (canonical location)

`Category` and `Priority` choices are defined in `issues/models.py`.  
`incidents/models.py` imports them from there to avoid duplication.

```python
from issues.models import Category, Priority
```

`IncidentStatus` choices are defined in `incidents/models.py` (Incident-only concept).

---

### Auto-generated Codes

Both `Issue` and `Incident` use a two-step `save()` pattern:

1. Save to get `pk`
2. Compute code from `pk`: `CIV-{1000 + pk}` or `INC-{1000 + pk}`
3. `update()` only the code field (avoids recursion)

This guarantees human-readable codes without a separate sequence.

---

### Database

- **Production / CI**: PostgreSQL via `DATABASE_URL` env var
- **Local dev**: SQLite fallback when `DATABASE_URL` is empty
- Do NOT use SQLite for any demo or deployment

---

### Database Relationship Map

```
CitySenseUser
  ├── reported_issues → [Issue]
  ├── assigned_incidents → [Incident]
  └── status_changes → [IncidentStatusHistory]

Department
  ├── incidents → [Incident]       (final assignment)
  └── ai_suggested_issues → [Issue] (AI suggestion only)

Issue
  └── incident → Incident (nullable FK)

Incident
  ├── issues → [Issue]             (reverse FK)
  ├── department → Department
  ├── assigned_to → CitySenseUser
  └── status_history → [IncidentStatusHistory]

IncidentStatusHistory
  ├── incident → Incident
  └── changed_by → CitySenseUser
```

---

### Settings Strategy

All secrets and environment-specific values come from environment variables.  
`python-decouple` loads from `.env` when present.  
`.env` is gitignored — never committed.

---

### URL Namespace Conventions

```
/health/           → citysense.views.health_check   (no auth)
/admin/            → Django admin
/accounts/…        → register, email login, POST logout
/issues/…          → authenticated citizen issue list, create, detail
/incidents/…       → incident detail accessible through a citizen's own issue
/dashboard/…       → authenticated citizen report dashboard
```

---

### Static / Media Files

```
static/            → Source static files (Palak's CSS/JS)
staticfiles/       → collectstatic output (gitignored)
media/             → User-uploaded images (gitignored)
```

---

### AI Integration Rules

- AI orchestration lives in `ai_engine.services`; Google-specific calls live behind the `ai_engine.providers` adapter
- The current integration uses the Google Gen AI Python SDK (`google-genai`) and `AI_MODEL`
- `AI_API_KEY` is read server-side only; `AI_TIMEOUT_SECONDS` bounds each provider request (default 20 seconds, one attempt)
- All AI output must be validated before use
- AI failure must NOT block issue creation (deterministic fallback required)
- API key read from `AI_API_KEY` env var — never hardcoded
- AI suggestions stored on `Issue` — final values live on `Incident`
- The prompt restricts output to the allowed category, priority, and department enums and requests JSON only
- Provider output is strictly checked for structure, enum values, a non-empty summary, and finite confidence in `[0, 1]`
- Keyword fallback uses explicit civic terms and high-risk terms; unknown reports use `Other`, `General`, and `MEDIUM`
- Provider calls happen before the database transaction; validated AI or fallback values are written atomically with the Issue, Incident, link, and initial history

---

### Phase 3/4/5 report creation

`issues.views.create` validates the submission and calls `ai_engine.services.triage_issue` before beginning a database transaction. The provider receives the title, description, and optional image, with a bounded request timeout. Missing credentials, provider exceptions, timeouts, malformed JSON, and invalid output return deterministic fallback values.

`issues.services.create_issue_with_incident` owns the atomic database writes. It stores validated recommendations in the existing Issue AI fields, then asks `incidents.intelligence` for a deterministic match. A match links the Issue to an existing active Incident and recalculates its report count, representative location, and severity. No match creates a new Incident using the existing `Other`, `MEDIUM`, `REPORTED`, and `General` defaults and writes the initial `REPORTED` status history entry. The Incident's final category, priority, department, and status are not overwritten during aggregation.

AI suggestions are evidence, not authority: they can contribute to category matching and the severity calculation, but they never set final Incident classification. The detector compares reports from the last 30 days and excludes resolved/rejected Incidents. Its score weights category match (0.35), nearby location (0.35), text similarity (0.25), and recency (0.05); its configurable-in-code threshold is 0.60. A concrete non-`Other` category match is required. Geographic evidence applies only when both sides have coordinates and are within 0.5 km. The returned match assessment includes the score and signal details so association is explainable. If coordinates are absent, text and category evidence can still meet the threshold.

Candidate scores use the strongest token-set overlap / normalized-token sequence similarity against the Incident title and its linked report texts. Location uses haversine distance. These are deterministic heuristics, not model predictions. The constants are centralized in `incidents/intelligence.py` (`MATCH_WINDOW_DAYS`, `MATCH_RADIUS_KM`, `DUPLICATE_THRESHOLD`, and signal weights).

Severity is a 0–100 heuristic: 20 base points, up to 25 points for additional reports (5 each), 5/12/22/30 points for the highest final or suggested priority (LOW/MEDIUM/HIGH/CRITICAL), up to 10 points for persistence over seven days, and 5 points when a location is available. The result and factor breakdown are returned by `calculate_incident_severity` and the numeric score is stored in the existing `Incident.severity_score`. It never changes priority or any other admin-controlled field.

Matching and association run within the Issue creation transaction. Matching/update work has a nested savepoint; an unexpected intelligence exception rolls back a partial match and creates a separate Incident instead. This favors a possible duplicate Incident over a silent false merge and keeps a valid citizen submission from failing. AI provider calls still happen before database writes and continue to use the existing validated deterministic fallback. No REST endpoint or template redesign was added.

The citizen routes filter issue queries by `reported_by=request.user`. Incident detail is available only when the requested Incident is associated with one of that user's Issues. These views are read-only; classification and status changes remain outside the citizen workflow.

Images are validated as JPEG, PNG, GIF, or WebP and capped at 5 MB. Coordinates are optional and bounded to latitude `[-90, 90]` and longitude `[-180, 180]`.

---

## Phase Log

| Phase | Description | Status |
|---|---|---|
| 1 | Django foundation scaffold | ✅ Complete |
| 2 | Core data model + auth foundation | ✅ Complete |
| 3 | Citizen reporting + auth views | ✅ Complete |
| 4 | AI Smart Triage | ✅ Complete |
| 5 | Incident aggregation + severity | ✅ Complete |
| 6 | Admin dashboard views | 🔜 |
| 7 | Testing, deployment | 🔜 |

## Migration History

| Migration | Description |
|---|---|
| `accounts/0001_initial` | CitySenseUser model |
| `issues/0001_initial` | Department + Issue models |
| `incidents/0001_initial` | Incident + IncidentStatusHistory (core tables) |
| `incidents/0002_initial` | Foreign key additions (department, changed_by, incident) |
