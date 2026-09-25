# CitySense Technical Notes

## Backend Architecture Decisions

### Django App Structure

| App | Owner | Purpose |
|---|---|---|
| `accounts` | Backend | User model, auth, roles (Citizen / Admin) |
| `issues` | Backend | Citizen issue reports |
| `incidents` | Backend | Aggregated civic incidents |
| `ai_engine` | Backend | AI triage, duplicate detection |
| `dashboard` | Backend (logic) + Frontend (UI) | Analytics and admin workflows |

### Database

- **Production / CI**: PostgreSQL via `DATABASE_URL` env var (parsed by `dj-database-url`)
- **Local dev**: SQLite fallback when `DATABASE_URL` is empty — allows either developer to run without a local Postgres instance
- Do NOT use SQLite for any demo or deployment; switch to PostgreSQL

### Settings Strategy

All secrets and environment-specific values come from environment variables.  
`python-decouple` loads from `.env` when present.  
`.env` is gitignored — never committed.

### URL Namespace Conventions

```
/health/           → citysense.views.health_check   (no auth)
/admin/            → Django admin
/accounts/…        → accounts app (Phase 2)
/issues/…          → issues app (Phase 2)
/incidents/…       → incidents app (Phase 2)
/dashboard/…       → dashboard app (Phase 3)
```

### Static / Media Files

```
static/            → Source static files (Palak's CSS/JS)
staticfiles/       → collectstatic output (gitignored)
media/             → User-uploaded images (gitignored)
```

### AI Integration

- AI calls live exclusively in the `ai_engine` app
- All AI output must be validated before use
- AI failure must NOT block issue creation (deterministic fallback required)
- API key read from `AI_API_KEY` env var — never hardcoded

### Naming Conventions

- Models: PascalCase — `CivicIssue`, `Incident`
- URL names: kebab-case — `issues:create`, `accounts:login`
- Template dirs: `<app>/templates/<app>/` — avoids name collisions

## Phase Log

| Phase | Description | Status |
|---|---|---|
| 1 | Django foundation scaffold | ✅ Complete |
| 2 | Models, auth, issue reporting | ⏳ Next |
| 3 | AI triage, duplicate detection | 🔜 |
| 4 | Incident aggregation, severity | 🔜 |
| 5 | Admin dashboard | 🔜 |
| 6 | Testing, deployment | 🔜 |
