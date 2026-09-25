# CitySense Technical Notes

## Backend Architecture Decisions

### Django App Structure

| App | Owner | Purpose |
|---|---|---|
| `accounts` | Backend | Custom user model, email auth, CITIZEN/ADMIN roles |
| `issues` | Backend | Department lookup, citizen Issue reports |
| `incidents` | Backend | Incident aggregation, status lifecycle, history |
| `ai_engine` | Backend | AI triage, duplicate detection (Phase 3) |
| `dashboard` | Backend (logic) + Frontend (UI) | Admin analytics and workflows |

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
/accounts/…        → accounts app (Phase 3)
/issues/…          → issues app (Phase 3)
/incidents/…       → incidents app (Phase 3+)
/dashboard/…       → dashboard app (Phase 4)
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

- AI calls live exclusively in the `ai_engine` app
- All AI output must be validated before use
- AI failure must NOT block issue creation (deterministic fallback required)
- API key read from `AI_API_KEY` env var — never hardcoded
- AI suggestions stored on `Issue` — final values live on `Incident`

---

## Phase Log

| Phase | Description | Status |
|---|---|---|
| 1 | Django foundation scaffold | ✅ Complete |
| 2 | Core data model + auth foundation | ✅ Complete |
| 3 | Issue reporting + auth views | ⏳ Next |
| 4 | AI triage + duplicate detection | 🔜 |
| 5 | Incident aggregation + severity | 🔜 |
| 6 | Admin dashboard views | 🔜 |
| 7 | Testing, deployment | 🔜 |

## Migration History

| Migration | Description |
|---|---|
| `accounts/0001_initial` | CitySenseUser model |
| `issues/0001_initial` | Department + Issue models |
| `incidents/0001_initial` | Incident + IncidentStatusHistory (core tables) |
| `incidents/0002_initial` | Foreign key additions (department, changed_by, incident) |
