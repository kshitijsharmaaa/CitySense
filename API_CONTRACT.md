# CitySense API / Data Contract

This document defines the data expected between the backend
and frontend.

## Issue

Expected fields:

- issue_code
- title
- description
- image
- category
- priority
- status
- department
- latitude
- longitude
- created_at
- updated_at

## AI Analysis

```json
{
  "category": "Pothole",
  "priority": "HIGH",
  "department": "Road Maintenance",
  "summary": "Large pothole near the main entrance.",
  "confidence": 0.92
}