"""
incidents/tests.py

Backend tests for Incident and IncidentStatusHistory models.

Tests cover:
- Incident creation and auto-code generation
- Issue → Incident relationship and report_count
- Status choices validation
- IncidentStatusHistory creation
- Incident __str__ representation
"""

from django.test import TestCase
from django.contrib.auth import get_user_model

from issues.models import Category, Department, Issue, Priority
from .models import Incident, IncidentStatus, IncidentStatusHistory

User = get_user_model()


class IncidentTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@test.com",
            name="Admin User",
            password="pass",
            role=User.Role.ADMIN,
        )
        self.citizen = User.objects.create_user(
            email="citizen@test.com",
            name="Citizen User",
            password="pass",
        )
        self.dept = Department.objects.create(name="Road Maintenance")

    def test_incident_creation_generates_code(self):
        """Incident auto-generates an INC-NNNN incident_code on save."""
        incident = Incident.objects.create(
            title="Pothole cluster near Main Gate",
            category=Category.POTHOLE,
            priority=Priority.HIGH,
            department=self.dept,
        )
        self.assertTrue(incident.incident_code.startswith("INC-"))
        self.assertGreater(len(incident.incident_code), 4)

    def test_incident_codes_are_unique(self):
        """Two incidents have different codes."""
        i1 = Incident.objects.create(title="Incident One", category=Category.POTHOLE)
        i2 = Incident.objects.create(title="Incident Two", category=Category.GARBAGE)
        self.assertNotEqual(i1.incident_code, i2.incident_code)

    def test_incident_default_status(self):
        """A newly created incident has REPORTED status."""
        incident = Incident.objects.create(title="New Incident")
        self.assertEqual(incident.status, IncidentStatus.REPORTED)

    def test_incident_default_priority(self):
        """A newly created incident has MEDIUM priority."""
        incident = Incident.objects.create(title="Medium Prio Test")
        self.assertEqual(incident.priority, Priority.MEDIUM)

    def test_issue_linked_to_incident(self):
        """An Issue can be linked to an Incident via the incident FK."""
        incident = Incident.objects.create(
            title="Linked Incident",
            category=Category.POTHOLE,
        )
        issue = Issue.objects.create(
            reported_by=self.citizen,
            title="Citizen pothole report",
            description="There is a big pothole.",
            incident=incident,
        )
        self.assertEqual(issue.incident, incident)
        self.assertIn(issue, incident.issues.all())

    def test_multiple_issues_linked_to_same_incident(self):
        """Multiple issues can be linked to the same incident."""
        incident = Incident.objects.create(title="Multi-issue Incident")
        for i in range(4):
            Issue.objects.create(
                reported_by=self.citizen,
                title=f"Report {i}",
                description="Duplicate pothole report.",
                incident=incident,
            )
        self.assertEqual(incident.issues.count(), 4)

    def test_update_report_count(self):
        """update_report_count correctly reflects associated issue count."""
        incident = Incident.objects.create(title="Report Count Test")
        for i in range(3):
            Issue.objects.create(
                reported_by=self.citizen,
                title=f"Report {i}",
                description="Test report.",
                incident=incident,
            )
        incident.update_report_count()
        incident.refresh_from_db()
        self.assertEqual(incident.report_count, 3)

    def test_incident_str(self):
        """__str__ contains code, title, and status."""
        incident = Incident.objects.create(
            title="Garbage on Park Road",
            category=Category.GARBAGE,
        )
        s = str(incident)
        self.assertIn(incident.incident_code, s)
        self.assertIn("Garbage on Park Road", s)
        self.assertIn(IncidentStatus.REPORTED, s)


class IncidentStatusHistoryTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@test.com",
            name="Admin",
            password="pass",
            role=User.Role.ADMIN,
        )
        self.incident = Incident.objects.create(title="Status History Test Incident")

    def test_status_history_creation(self):
        """IncidentStatusHistory records a status transition."""
        history = IncidentStatusHistory.objects.create(
            incident=self.incident,
            old_status=IncidentStatus.REPORTED,
            new_status=IncidentStatus.VERIFIED,
            comment="Verified by field team.",
            changed_by=self.admin,
        )
        self.assertEqual(history.incident, self.incident)
        self.assertEqual(history.old_status, IncidentStatus.REPORTED)
        self.assertEqual(history.new_status, IncidentStatus.VERIFIED)
        self.assertEqual(history.changed_by, self.admin)

    def test_status_history_linked_to_incident(self):
        """History entries are accessible via incident.status_history."""
        IncidentStatusHistory.objects.create(
            incident=self.incident,
            old_status="",
            new_status=IncidentStatus.REPORTED,
            changed_by=self.admin,
        )
        IncidentStatusHistory.objects.create(
            incident=self.incident,
            old_status=IncidentStatus.REPORTED,
            new_status=IncidentStatus.VERIFIED,
            changed_by=self.admin,
        )
        self.assertEqual(self.incident.status_history.count(), 2)

    def test_status_history_str(self):
        """__str__ contains incident code and status transition."""
        history = IncidentStatusHistory.objects.create(
            incident=self.incident,
            old_status=IncidentStatus.REPORTED,
            new_status=IncidentStatus.ASSIGNED,
            changed_by=self.admin,
        )
        s = str(history)
        self.assertIn(self.incident.incident_code, s)
        self.assertIn(IncidentStatus.ASSIGNED, s)

    def test_multiple_history_entries_ordered(self):
        """Status history is returned in reverse chronological order."""
        h1 = IncidentStatusHistory.objects.create(
            incident=self.incident,
            old_status="",
            new_status=IncidentStatus.REPORTED,
            changed_by=self.admin,
        )
        h2 = IncidentStatusHistory.objects.create(
            incident=self.incident,
            old_status=IncidentStatus.REPORTED,
            new_status=IncidentStatus.VERIFIED,
            changed_by=self.admin,
        )
        history = list(self.incident.status_history.all())
        # Newest first
        self.assertEqual(history[0].pk, h2.pk)
        self.assertEqual(history[1].pk, h1.pk)
