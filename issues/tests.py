"""
issues/tests.py

Backend tests for Department and Issue models.

Tests cover:
- Department creation and uniqueness
- Issue creation and auto-code generation
- AI fields storage
- Issue → Incident relationship
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from .models import Category, Department, Issue, Priority

User = get_user_model()


class DepartmentTests(TestCase):

    def test_department_creation(self):
        """Department can be created with name and description."""
        dept = Department.objects.create(
            name="Road Maintenance",
            description="Manages road repairs and potholes.",
        )
        self.assertEqual(str(dept), "Road Maintenance")
        self.assertEqual(dept.description, "Manages road repairs and potholes.")

    def test_department_name_unique(self):
        """Department name must be unique."""
        Department.objects.create(name="Sanitation")
        with self.assertRaises(IntegrityError):
            Department.objects.create(name="Sanitation")

    def test_all_seed_department_names(self):
        """All six expected departments can be created without conflict."""
        names = ["Road Maintenance", "Sanitation", "Electrical", "Water Supply", "Drainage", "General"]
        for name in names:
            Department.objects.create(name=name)
        self.assertEqual(Department.objects.count(), 6)


class IssueTests(TestCase):

    def setUp(self):
        self.citizen = User.objects.create_user(
            email="citizen@test.com",
            name="Test Citizen",
            password="pass",
        )
        self.dept = Department.objects.create(name="Road Maintenance")

    def test_issue_creation_generates_code(self):
        """Issue auto-generates a CIV-NNNN issue_code on save."""
        issue = Issue.objects.create(
            reported_by=self.citizen,
            title="Pothole on Main Street",
            description="Large pothole causing traffic disruption.",
        )
        self.assertTrue(issue.issue_code.startswith("CIV-"))
        self.assertGreater(len(issue.issue_code), 4)

    def test_issue_codes_are_unique(self):
        """Two issues must have different issue_codes."""
        i1 = Issue.objects.create(
            reported_by=self.citizen,
            title="Issue One",
            description="First issue.",
        )
        i2 = Issue.objects.create(
            reported_by=self.citizen,
            title="Issue Two",
            description="Second issue.",
        )
        self.assertNotEqual(i1.issue_code, i2.issue_code)

    def test_issue_ai_fields_stored(self):
        """AI suggestion fields are stored correctly."""
        issue = Issue.objects.create(
            reported_by=self.citizen,
            title="Broken light",
            description="Streetlight is out.",
            ai_category=Category.STREETLIGHT,
            ai_priority=Priority.HIGH,
            ai_department=self.dept,
            ai_summary="Streetlight malfunction on Main Avenue.",
            ai_confidence=0.91,
        )
        issue.refresh_from_db()
        self.assertEqual(issue.ai_category, Category.STREETLIGHT)
        self.assertEqual(issue.ai_priority, Priority.HIGH)
        self.assertEqual(issue.ai_department, self.dept)
        self.assertAlmostEqual(issue.ai_confidence, 0.91, places=2)

    def test_issue_without_incident_is_valid(self):
        """An issue can exist without being linked to an incident."""
        issue = Issue.objects.create(
            reported_by=self.citizen,
            title="Unlinked issue",
            description="Not yet associated with an incident.",
        )
        self.assertIsNone(issue.incident)

    def test_issue_str(self):
        """Issue __str__ contains the code and title."""
        issue = Issue.objects.create(
            reported_by=self.citizen,
            title="Broken Pipe",
            description="Water leaking from main pipe.",
        )
        self.assertIn(issue.issue_code, str(issue))
        self.assertIn("Broken Pipe", str(issue))
