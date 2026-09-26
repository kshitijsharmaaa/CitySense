# CitySense API / Data Contract

This document defines the data expected between the backend
and frontend.

---

## Core Architectural Distinction

### Issue

An **Issue** is one citizen's raw report of a civic problem.

- Owned by the citizen who submitted it
- Contains raw input: description, image, location
- Contains AI *suggestions*: category, priority, department, summary
- AI fields are SUGGESTIONS only — they are never the final authority
- An Issue may be linked to an Incident (nullable)

### Incident

An **Incident** is the underlying civic problem that administrators manage and resolve.

- May aggregate many Issues describing the same problem
- Holds administrator-controlled final classification: status, category, priority, department
- Resolution information (status, notes, resolved_at) belongs to Incident — NOT to Issue
- Administrators are responsible for transitioning Incident status

### Phase 3 behavior

- `accounts:register` creates a CITIZEN account only; self-selected roles are ignored.
- `issues:create` is available to authenticated users and takes `title`, `description`, optional `image`, `latitude`, and `longitude`. The reporter is always the session user.
- Each submitted Issue creates a new Incident with category `Other`, priority `MEDIUM`, status `REPORTED`, department `General`, and `report_count = 1`.
- The Issue is linked to that Incident and an initial `REPORTED` status history record is created in the same database transaction.
- **Phase 3 creates a new Incident for each submitted Issue because AI classification and duplicate/incident aggregation are Phase 4/5 features.**
- Citizens can access their own reports and an Incident only when it is associated with one of their reports. Incident status and classification are read-only in citizen routes.
- Issue images are limited to JPEG, PNG, GIF, or WebP and 5 MB.

---

## Issue Fields

| Field | Type | Notes |
|---|---|---|
| `issue_code` | string | Auto-generated. Format: `CIV-1001` |
| `reported_by` | FK → User | Nullable |
| `title` | string | Citizen-supplied title |
| `description` | text | Citizen description |
| `image` | image | Optional upload |
| `latitude` | decimal | Optional |
| `longitude` | decimal | Optional |
| `ai_category` | choice | AI suggestion only |
| `ai_priority` | choice | AI suggestion only |
| `ai_department` | FK → Department | AI suggestion only |
| `ai_summary` | text | AI-generated summary |
| `ai_confidence` | float | 0.0–1.0 |
| `incident` | FK → Incident | Nullable in the model; Phase 3 submission links a newly created Incident |
| `created_at` | datetime | |
| `updated_at` | datetime | |

---

## Incident Fields

| Field | Type | Notes |
|---|---|---|
| `incident_code` | string | Auto-generated. Format: `INC-1001` |
| `title` | string | |
| `category` | choice | Final admin-controlled value |
| `priority` | choice | Final admin-controlled value |
| `status` | choice | See status values below |
| `department` | FK → Department | Final assignment |
| `assigned_to` | FK → User | Admin user |
| `latitude` | decimal | Representative location |
| `longitude` | decimal | Representative location |
| `severity_score` | float | Reserved for future severity logic; not populated in Phase 3 |
| `report_count` | int | Count of linked Issues |
| `resolution_notes` | text | |
| `resolved_at` | datetime | Set when status = RESOLVED |
| `created_at` | datetime | |
| `updated_at` | datetime | |

---

## Category Choices

```
Pothole
Garbage
Streetlight
Water Leakage
Drainage
Road Damage
Other
```

## Priority Choices

```
LOW
MEDIUM
HIGH
CRITICAL
```

## Incident Status Choices

```
REPORTED
VERIFIED
ASSIGNED
IN_PROGRESS
RESOLVED
REJECTED
```

Status belongs to **Incident** only. Issues do not have a status field.

---

## IncidentStatusHistory

Every Incident status transition creates a history record.

| Field | Type |
|---|---|
| `incident` | FK → Incident |
| `old_status` | choice |
| `new_status` | choice |
| `comment` | text |
| `changed_by` | FK → User |
| `created_at` | datetime |

---

## User Fields

| Field | Type | Notes |
|---|---|---|
| `email` | email | Unique. Login identifier |
| `name` | string | Full name |
| `role` | choice | `CITIZEN` or `ADMIN` |
| `created_at` | datetime | |

---

## Department Fields

| Field | Type |
|---|---|
| `name` | string (unique) |
| `description` | text |

Seeded departments: Road Maintenance, Sanitation, Electrical, Water Supply, Drainage, General

---

## Future AI Analysis Response Shape

This describes a future AI pipeline contract. Phase 3 does not call an AI service or write AI suggestions.

The AI pipeline returns (or falls back to deterministic defaults):

```json
{
  "category": "Pothole",
  "priority": "HIGH",
  "department": "Road Maintenance",
  "summary": "Large pothole near the main entrance.",
  "confidence": 0.92
}
```

AI output is validated before being stored on the Issue.
AI failure must NOT prevent issue creation — fallback values are used instead.
