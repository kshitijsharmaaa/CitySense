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
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from io import BytesIO
from PIL import Image

from incidents.models import IncidentStatus, IncidentStatusHistory
from .forms import MAX_IMAGE_SIZE
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


@override_settings(AI_API_KEY="")
class CitizenIssueWorkflowTests(TestCase):
    def setUp(self):
        self.citizen = User.objects.create_user(
            email="reporter@example.com", name="Reporter", password="CivicPass!2719"
        )
        self.other_citizen = User.objects.create_user(
            email="other@example.com", name="Other", password="CivicPass!2719"
        )

    @staticmethod
    def image_upload(name="report.png", image_format="PNG"):
        buffer = BytesIO()
        Image.new("RGB", (2, 2), color="red").save(buffer, format=image_format)
        content_type = "image/png" if image_format == "PNG" else "image/jpeg"
        return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)

    def submit_data(self, **overrides):
        data = {
            "title": "Pothole near the library",
            "description": "A deep pothole is blocking the cycle lane.",
            "latitude": "19.076000",
            "longitude": "72.877700",
        }
        data.update(overrides)
        return data

    def test_anonymous_cannot_access_dashboard_create_or_issue_detail(self):
        issue = Issue.objects.create(title="Private", description="Private report")
        for url in (
            reverse("dashboard:index"),
            reverse("issues:create"),
            reverse("issues:detail", args=(issue.pk,)),
        ):
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}")

    def test_valid_issue_creates_linked_default_incident_and_history(self):
        self.client.force_login(self.citizen)
        response = self.client.post(reverse("issues:create"), self.submit_data())
        issue = Issue.objects.get()
        incident = issue.incident
        self.assertRedirects(response, reverse("issues:detail", args=(issue.pk,)))
        self.assertEqual(issue.reported_by, self.citizen)
        self.assertTrue(issue.issue_code.startswith("CIV-"))
        self.assertIsNotNone(incident)
        self.assertEqual(incident.title, issue.title)
        self.assertEqual(incident.category, Category.OTHER)
        self.assertEqual(incident.priority, Priority.MEDIUM)
        self.assertEqual(incident.department.name, "General")
        self.assertEqual(incident.status, IncidentStatus.REPORTED)
        self.assertEqual(incident.report_count, 1)
        history = IncidentStatusHistory.objects.get(incident=incident)
        self.assertEqual(history.new_status, IncidentStatus.REPORTED)
        self.assertEqual(history.changed_by, self.citizen)

    def test_uploaded_valid_image_is_saved(self):
        self.client.force_login(self.citizen)
        response = self.client.post(
            reverse("issues:create"),
            {**self.submit_data(), "image": self.image_upload()},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Issue.objects.get().image)

    def test_invalid_latitude_is_rejected(self):
        self.client.force_login(self.citizen)
        response = self.client.post(reverse("issues:create"), self.submit_data(latitude="90.000001"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Issue.objects.exists())

    def test_invalid_longitude_is_rejected(self):
        self.client.force_login(self.citizen)
        response = self.client.post(reverse("issues:create"), self.submit_data(longitude="-180.000001"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Issue.objects.exists())

    def test_invalid_image_is_rejected(self):
        self.client.force_login(self.citizen)
        bad_image = SimpleUploadedFile("not-image.jpg", b"not a real image", content_type="image/jpeg")
        response = self.client.post(
            reverse("issues:create"), {**self.submit_data(), "image": bad_image}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Issue.objects.exists())

    def test_unsupported_image_format_is_rejected(self):
        self.client.force_login(self.citizen)
        response = self.client.post(
            reverse("issues:create"),
            {**self.submit_data(), "image": self.image_upload("report.bmp", "BMP")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Issue.objects.exists())

    def test_title_and_description_are_required(self):
        self.client.force_login(self.citizen)
        response = self.client.post(
            reverse("issues:create"), self.submit_data(title="", description="")
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Issue.objects.exists())

    def test_oversized_image_is_rejected(self):
        self.client.force_login(self.citizen)
        valid = self.image_upload().read()
        oversized = SimpleUploadedFile(
            "large.png", valid + (b"x" * (MAX_IMAGE_SIZE + 1)), content_type="image/png"
        )
        response = self.client.post(
            reverse("issues:create"), {**self.submit_data(), "image": oversized}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Issue.objects.exists())

    def test_citizen_can_access_own_issue_but_not_another_citizens_issue(self):
        own = Issue.objects.create(reported_by=self.citizen, title="Own", description="Own report")
        other = Issue.objects.create(reported_by=self.other_citizen, title="Other", description="Private")
        self.client.force_login(self.citizen)
        self.assertEqual(self.client.get(reverse("issues:detail", args=(own.pk,))).status_code, 200)
        self.assertEqual(self.client.get(reverse("issues:detail", args=(other.pk,))).status_code, 404)

    def test_citizen_cannot_post_changes_to_issue_detail(self):
        issue = Issue.objects.create(reported_by=self.citizen, title="Own", description="Own report")
        self.client.force_login(self.citizen)
        response = self.client.post(reverse("issues:detail", args=(issue.pk,)), {
            "status": IncidentStatus.RESOLVED,
            "priority": Priority.CRITICAL,
            "department": "other",
            "report_count": 999,
        })
        self.assertEqual(response.status_code, 405)

    def test_citizen_cannot_post_incident_classification_changes(self):
        from issues.services import create_issue_with_incident

        issue = create_issue_with_incident(
            issue=Issue(title="Own", description="Own report"), reported_by=self.citizen
        )
        incident = issue.incident
        self.client.force_login(self.citizen)
        response = self.client.post(reverse("incidents:detail", args=(incident.pk,)), {
            "status": IncidentStatus.RESOLVED,
            "priority": Priority.CRITICAL,
            "department": "other",
            "report_count": 999,
        })
        self.assertEqual(response.status_code, 405)
        incident.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.REPORTED)
        self.assertEqual(incident.priority, Priority.MEDIUM)
        self.assertEqual(incident.department.name, "General")
        self.assertEqual(incident.report_count, 1)

    def test_citizen_cannot_access_django_admin(self):
        self.client.force_login(self.citizen)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_admin_role_cannot_use_citizen_workflow(self):
        admin_user = User.objects.create_user(
            email="admin-role@example.com", name="Admin Role", password="CivicPass!2719",
            role=User.Role.ADMIN,
        )
        self.client.force_login(admin_user)
        self.assertEqual(self.client.get(reverse("dashboard:index")).status_code, 403)
        self.assertEqual(self.client.get(reverse("issues:create")).status_code, 403)

    def test_dashboard_only_shows_authenticated_citizens_issues(self):
        own = Issue.objects.create(reported_by=self.citizen, title="My issue", description="Mine")
        Issue.objects.create(reported_by=self.other_citizen, title="Private issue", description="Theirs")
        self.client.force_login(self.citizen)
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(list(response.context["issues"]), [own])
        self.assertContains(response, own.issue_code)
        self.assertNotContains(response, "Private issue")

    def test_citizen_can_access_associated_incident_but_other_citizen_cannot(self):
        from issues.services import create_issue_with_incident

        own = create_issue_with_incident(
            issue=Issue(title="Mine", description="Mine"), reported_by=self.citizen
        )
        incident = own.incident
        self.client.force_login(self.other_citizen)
        self.assertEqual(self.client.get(reverse("incidents:detail", args=(incident.pk,))).status_code, 404)
        self.client.force_login(self.citizen)
        response = self.client.get(reverse("incidents:detail", args=(incident.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reported")
