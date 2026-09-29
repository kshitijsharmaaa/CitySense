# CitySense

> See the problem. Understand the issue. Drive the action.

CitySense is an AI-assisted civic issue intelligence and resolution platform.

## Problem

Civic issues are often reported as fragmented and unstructured complaints.
Multiple reports may also represent the same underlying problem.

## Solution

CitySense transforms citizen descriptions, images, and locations into
structured civic incidents using AI and deterministic location/text
intelligence.

## Core workflow

Citizen report → AI triage recommendation → duplicate detection → incident
aggregation → prioritization → department assignment → resolution → citizen
tracking.

## Features

- Citizen registration, login, and private report lists
- Issue reporting with image upload and location capture
- AI Smart Triage with output validation and deterministic fallback
- Deterministic duplicate detection and incident aggregation
- Incident severity calculation
- Admin incident review, department/operator assignment, status history,
  resolution, and reopen workflow
- Configurable incident SLAs with automatic, audited L1/L2 escalation
- Citizen progress tracking and map views
- Responsive Django Templates, Bootstrap 5, and vanilla JavaScript UI

## Tech stack

- Python and Django
- PostgreSQL in production; SQLite development fallback
- Django Templates, Bootstrap 5, and vanilla JavaScript
- Leaflet maps
- Gemini multimodal API integration

## Project status

AI category, priority, department, summary, and confidence are stored as
recommendations on each Issue. Validated recommendations seed only newly
created Incidents; administrators control canonical Incident values, and
duplicate reports do not overwrite existing Incident fields. If the provider
is unavailable or returns invalid output, deterministic keyword fallback
keeps report submission working. Gemini configuration is server-side through
`AI_API_KEY`, `AI_MODEL`, and `AI_TIMEOUT_SECONDS`.

### Incident SLAs and escalation

New Incidents start their SLA clock when created. Priority defaults are seeded
as Critical: 1 day, High: 3 days, Medium: 7 days, and Low: 14 days. Admins can
change these values and the L1-to-L2 wait period in Django admin under
**Incident SLA configurations**; a category-specific row overrides its
priority-wide default. L1-to-L2 defaults are 1, 2, 3, and 5 days respectively.
Designate active ADMIN accounts as L1 or L2 officers in the user admin. On
admin dashboard or incident review access, CitySense checks unresolved cases,
marks overdue SLAs, routes them to the designated officer, and records each
escalation in the incident history. This access-triggered check avoids a
separate worker service; an overdue case is evaluated the next time an admin
opens the operations dashboard or review page.

## Deploy to Render

CitySense runs as a Python Web Service backed by Render PostgreSQL. WhiteNoise
serves collected Django static files when `DEBUG=False`.

### Render setup

1. Create a Render PostgreSQL database in the same region as the web service
   (choose the Free plan for a short demo).
2. Create a public Python Web Service from the integrated CitySense branch in
   this repository (choose the Free plan for a short demo).
3. Set the build command to `bash build.sh` and the start command to:

   ```sh
   gunicorn citysense.wsgi:application --bind 0.0.0.0:$PORT
   ```

4. Set the health check path to `/health/`.
5. Add the environment variables below before the first deploy. Set
   `DATABASE_URL` to the database's **internal** connection URL. Set
   `ALLOWED_HOSTS` to the exact generated service host (for example,
   `citysense-example.onrender.com`) and `CSRF_TRUSTED_ORIGINS` to its HTTPS
   origin (for example, `https://citysense-example.onrender.com`).
6. Deploy. `build.sh` installs dependencies, collects static files, applies
   migrations, then runs `ensure_demo_admin` to create or update the configured
   demo administrator.
7. Verify the public service URL and `https://<service-host>/health/`.
   Citizens can register normally through the deployed application.

### Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | Yes in production | Generate a unique secret in Render; Django rejects an empty production value. |
| `DEBUG` | Yes | Set to `False`. |
| `ALLOWED_HOSTS` | Yes | Comma-separated exact Render hostnames. |
| `DATABASE_URL` | Yes | Render PostgreSQL internal connection URL. |
| `CSRF_TRUSTED_ORIGINS` | Yes | Comma-separated HTTPS origins, including scheme. |
| `AI_API_KEY` | Optional | Gemini credential; empty/missing uses deterministic fallback. |
| `AI_MODEL` | Optional | Gemini model; defaults to the project's configured default. |
| `AI_TIMEOUT_SECONDS` | Optional | Provider timeout; defaults to the project's configured default. |
| `DEMO_ADMIN_EMAIL` | Yes | Email of the one account managed as demo admin. |
| `DEMO_ADMIN_NAME` | Yes | Display name for the demo admin. |
| `DEMO_ADMIN_PASSWORD` | Yes | Strong admin password; never committed or printed by the command. |

Keep secret values in Render's Environment settings, not in source control.
`.env.example` lists the variables for local reference. Local development
continues to use the existing SQLite fallback when `DATABASE_URL` is empty.

### Render commands and free-tier notes

- Build command: `bash build.sh`
- Start command: `gunicorn citysense.wsgi:application --bind 0.0.0.0:$PORT`
- Health check: `/health/`
- Render Free web services use an ephemeral filesystem, so uploaded media is
  lost on restart, redeploy, or spin-down. Free web services also spin down
  after inactivity. Free Render PostgreSQL currently expires after 30 days;
  use persistent storage for data that must outlive a demo. See Render's
  [Free instance limitations](https://render.com/docs/free).
