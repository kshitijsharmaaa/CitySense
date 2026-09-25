# CitySense Project Specification

## Project

CitySense is an AI-assisted civic issue intelligence and resolution
platform built for a 36-hour hackathon.

## Problem

Civic problems such as potholes, garbage accumulation, broken
streetlights, water leakage and drainage issues are often reported
through fragmented channels.

Multiple citizens may report the same underlying problem independently.
Reports may also be unstructured and difficult to categorize,
prioritize and route.

## Solution

CitySense transforms citizen reports containing a description,
optional image and location into structured civic incidents.

The system can:

1. Understand the report using AI
2. Suggest a category
3. Suggest priority
4. Suggest the responsible department
5. Detect potential duplicate incidents
6. Aggregate related citizen reports
7. Help administrators review and route incidents
8. Allow citizens to track resolution

## Core Differentiator

CitySense is not simply a complaint CRUD application.

Its core value is:

Unstructured Reports
→ Intelligence
→ Civic Incidents
→ Action

## Core Workflow

Citizen
→ Report
→ AI Triage
→ Duplicate Detection
→ Incident Association
→ Prioritization
→ Department Assignment
→ Resolution
→ Citizen Tracking

## Target Users

### Citizen

Reports civic issues and tracks their progress.

### Administrator

Reviews, prioritizes, assigns and resolves civic incidents.

## Categories

- Pothole
- Garbage
- Streetlight
- Water Leakage
- Drainage
- Road Damage
- Other

## Priorities

- LOW
- MEDIUM
- HIGH
- CRITICAL

## Statuses

- REPORTED
- VERIFIED
- ASSIGNED
- IN_PROGRESS
- RESOLVED
- REJECTED

## AI

AI is used for:

- category suggestion
- priority suggestion
- department suggestion
- summary generation

AI is assistive and not the final authority.

## AI Failure Handling

If the AI service fails or returns invalid output,
CitySense must use deterministic fallback logic and
still allow issue creation.

## Hackathon Constraints

- 2 developers
- 36 hours
- first hackathon
- prioritize reliability and completion
- avoid unnecessary infrastructure