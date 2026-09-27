"""
issues/tests.py

Backend tests for Department and Issue models.

Tests cover:
- Department creation and uniqueness
- Issue creation and auto-code generation
- AI fields storage
- Issue → Incident relationship
"""

from django.test import Client, TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from django.urls import reverse
from unittest.mock import patch
from io import BytesIO
from PIL import Image

from incidents.intelligence import (
    DUPLICATE_THRESHOLD,
    calculate_incident_severity,
    find_related_incident,
    score_incident_match,
)
from incidents.models import Incident, IncidentStatus, IncidentStatusHistory
from .forms import MAX_IMAGE_SIZE
from .models import Category, Department, Issue, Priority
from .services import create_issue_with_incident

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
        incident = Incident.objects.create(title="Private incident")
        Issue.objects.create(
            title="Incident report", description="Private linked report", incident=incident
        )
        for url in (
            reverse("dashboard:index"),
            reverse("issues:list"),
            reverse("issues:create"),
            reverse("issues:detail", args=(issue.pk,)),
            reverse("incidents:detail", args=(incident.pk,)),
        ):
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}")

    def test_home_omits_buttons_typography_showcase_for_citizen_and_admin(self):
        admin = User.objects.create_user(
            email="home-admin@example.com", name="Home Admin", password="CivicPass!2719",
            role=User.Role.ADMIN,
        )
        for user in (self.citizen, admin):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.get(reverse("home"))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "Buttons & Typography System")
                self.assertNotContains(response, "Example community report")
                if user.is_admin_user:
                    self.assertContains(response, "CitySense Administration")
                    self.assertContains(response, "Total reports")
                    self.assertContains(response, "Manage Incidents")
                else:
                    self.assertContains(response, "Problems you can report")
                    self.assertContains(response, "Report a Problem")

    def test_admin_home_shows_live_records_and_real_empty_states(self):
        admin = User.objects.create_user(
            email="live-home-admin@example.com", name="Live Home Admin",
            password="CivicPass!2719", role=User.Role.ADMIN,
        )
        self.client.force_login(admin)

        empty_response = self.client.get(reverse("home"))
        self.assertEqual(empty_response.status_code, 200)
        self.assertEqual(empty_response.context["report_count"], 0)
        self.assertEqual(empty_response.context["active_incident_count"], 0)
        self.assertContains(empty_response, "No reports have been submitted yet.")
        self.assertContains(empty_response, "No active incidents yet.")
        self.assertContains(empty_response, "No reports currently need attention.")
        self.assertContains(empty_response, "No active department workload to display.")
        self.assertNotContains(empty_response, "Severe Pothole on Main Arterial Avenue")

        department = Department.objects.create(name="Live Roads Department")
        incident = Incident.objects.create(
            title="Pothole near the library",
            category=Category.POTHOLE,
            priority=Priority.HIGH,
            status=IncidentStatus.IN_PROGRESS,
            department=department,
        )
        report = Issue.objects.create(
            reported_by=self.other_citizen,
            title="Pothole near the library report",
            description="A real report in the database.",
            latitude="0.000000",
            longitude="72.877700",
            incident=incident,
            ai_category=Category.POTHOLE,
            ai_priority=Priority.HIGH,
            ai_department=department,
        )
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["report_count"], 1)
        self.assertEqual(response.context["active_incident_count"], 1)
        self.assertEqual(response.context["in_progress_count"], 1)
        self.assertEqual(response.context["resolved_count"], 0)
        self.assertIn(report, response.context["recent_reports"])
        self.assertIn(incident, response.context["recent_incidents"])
        self.assertContains(response, report.issue_code)
        self.assertContains(response, report.title)
        self.assertContains(response, incident.incident_code)
        self.assertContains(response, department.name)
        self.assertContains(response, "Work in progress")
        self.assertNotContains(response, "No reports have been submitted yet.")
        self.assertNotContains(response, "No active incidents yet.")
        self.assertNotContains(response, "Severe Pothole on Main Arterial Avenue")
        self.assertContains(response, f'href="{reverse("issues:list")}"')
        self.assertContains(response, f'href="{reverse("incidents:admin_dashboard")}"')
        self.assertContains(response, f'href="{reverse("issues:create")}"')
        self.assertContains(response, f'href="{reverse("dashboard:index")}"')

    def test_admin_home_counts_reports_linked_to_resolved_incidents(self):
        admin = User.objects.create_user(
            email="resolved-home-admin@example.com", name="Resolved Home Admin",
            password="CivicPass!2719", role=User.Role.ADMIN,
        )
        resolved = Incident.objects.create(title="Resolved incident", status=IncidentStatus.RESOLVED)
        Issue.objects.create(
            reported_by=self.other_citizen, title="Resolved report", description="Completed work",
            incident=resolved,
        )
        Issue.objects.create(
            reported_by=self.citizen, title="Open report", description="Still in progress",
            incident=Incident.objects.create(title="Open incident", status=IncidentStatus.IN_PROGRESS),
        )
        self.client.force_login(admin)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.context["resolved_report_count"], 1)
        self.assertContains(response, "Resolved")
        self.assertContains(response, ">1</div>")

    def test_citizen_home_does_not_expose_global_reports(self):
        Issue.objects.create(
            reported_by=self.other_citizen,
            title="Another resident's private report",
            description="Private report details.",
        )
        self.client.force_login(self.citizen)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["admin_home"])
        self.assertNotContains(response, "Another resident's private report")
        self.assertNotContains(response, "Reports Received")

    def test_valid_issue_creates_linked_triaged_incident_and_history(self):
        self.client.force_login(self.citizen)
        response = self.client.post(reverse("issues:create"), self.submit_data())
        issue = Issue.objects.get()
        incident = issue.incident
        self.assertRedirects(response, reverse("issues:detail", args=(issue.pk,)))
        self.assertEqual(issue.reported_by, self.citizen)
        self.assertTrue(issue.issue_code.startswith("CIV-"))
        self.assertIsNotNone(incident)
        self.assertEqual(incident.title, issue.title)
        self.assertEqual(incident.category, Category.POTHOLE)
        self.assertEqual(incident.priority, Priority.MEDIUM)
        self.assertEqual(incident.department.name, "Road Maintenance")
        self.assertEqual(incident.status, IncidentStatus.REPORTED)
        self.assertEqual(incident.report_count, 1)
        history = IncidentStatusHistory.objects.get(incident=incident)
        self.assertEqual(history.new_status, IncidentStatus.REPORTED)
        self.assertEqual(history.changed_by, self.citizen)

    def test_citizen_and_admin_can_get_report_creation_form(self):
        admin = User.objects.create_user(
            email="create-form-admin@example.com", name="Create Form Admin",
            password="CivicPass!2719", role=User.Role.ADMIN,
        )
        for user in (self.citizen, admin):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.get(reverse("issues:create"))
                self.assertEqual(response.status_code, 200)
                self.assertIn("form", response.context)

    def test_admin_can_submit_report_and_review_it(self):
        admin = User.objects.create_user(
            email="reporting-admin@example.com", name="Reporting Admin",
            password="CivicPass!2719", role=User.Role.ADMIN,
        )
        self.client.force_login(admin)
        response = self.client.post(reverse("issues:create"), self.submit_data())
        issue = Issue.objects.get()

        self.assertRedirects(response, reverse("issues:detail", args=(issue.pk,)))
        self.assertEqual(issue.reported_by, admin)

        list_response = self.client.get(reverse("issues:list"))
        self.assertEqual(list_response.status_code, 200)
        self.assertIn(issue, list_response.context["issues"])

        detail_response = self.client.get(reverse("issues:detail", args=(issue.pk,)))
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.context["issue"], issue)

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

    def test_admin_role_can_access_shared_pages_and_report_creation(self):
        admin_user = User.objects.create_user(
            email="admin-role@example.com", name="Admin Role", password="CivicPass!2719",
            role=User.Role.ADMIN,
        )
        self.client.force_login(admin_user)
        self.assertEqual(self.client.get(reverse("dashboard:index")).status_code, 200)
        self.assertEqual(self.client.get(reverse("issues:list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("issues:create")).status_code, 200)

    def test_citizen_can_access_issue_list_and_only_sees_own_reports(self):
        own = Issue.objects.create(reported_by=self.citizen, title="My list report", description="Mine")
        Issue.objects.create(reported_by=self.other_citizen, title="Other list report", description="Theirs")
        self.client.force_login(self.citizen)
        response = self.client.get(reverse("issues:list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["issues"]), [own])
        self.assertContains(response, own.issue_code)
        self.assertNotContains(response, "Other list report")

    def test_admin_can_access_issue_list_and_sees_all_reports(self):
        admin = User.objects.create_user(
            email="issue-list-admin@example.com", name="Issue List Admin", password="CivicPass!2719",
            role=User.Role.ADMIN,
        )
        first = Issue.objects.create(reported_by=self.citizen, title="Citizen report", description="Mine")
        second = Issue.objects.create(
            reported_by=self.other_citizen, title="Another report", description="Theirs"
        )
        self.client.force_login(admin)
        response = self.client.get(reverse("issues:list"))
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(response.context["issues"], [first, second])

    def test_admin_can_filter_resolved_reports_and_review_resolution_details(self):
        admin = User.objects.create_user(
            email="resolved-report-admin@example.com", name="Resolved Report Admin",
            password="CivicPass!2719", role=User.Role.ADMIN,
        )
        self.client.force_login(admin)
        empty_resolved = self.client.get(
            reverse("issues:list"), {"status": IncidentStatus.RESOLVED}
        )
        self.assertContains(empty_resolved, "No resolved complaints yet.")
        department = Department.objects.create(name="Resolved Roads")
        resolved_incident = Incident.objects.create(
            title="Resolved pothole", category=Category.POTHOLE, priority=Priority.HIGH,
            status=IncidentStatus.RESOLVED, department=department, assigned_to=admin,
            resolution_notes="Road surface repaired and inspected.", resolved_at=timezone.now(),
        )
        resolved_report = Issue.objects.create(
            reported_by=self.other_citizen, title="Pothole report", description="Road damage",
            incident=resolved_incident,
        )
        open_incident = Incident.objects.create(
            title="Open garbage issue", status=IncidentStatus.IN_PROGRESS,
        )
        open_report = Issue.objects.create(
            reported_by=self.citizen, title="Garbage report", description="Uncollected waste",
            incident=open_incident,
        )

        response = self.client.get(reverse("issues:list"), {"status": IncidentStatus.RESOLVED})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["issues"]), [resolved_report])
        self.assertContains(response, 'badge-status-resolved')
        self.assertContains(response, "Resolution update:")
        self.assertContains(response, "Road surface repaired and inspected.")
        self.assertContains(response, "Assigned Department:")
        self.assertContains(response, "Resolved Roads")
        self.assertContains(response, "Assigned Staff Member:")
        self.assertContains(response, admin.name)
        self.assertContains(response, resolved_incident.incident_code)
        for status_label in (
            "Report received", "Verified", "Assigned", "Work in progress",
            "Resolved", "Closed / Not approved",
        ):
            self.assertContains(response, status_label)
        self.assertNotContains(response, open_report.title)

        detail_response = self.client.get(reverse("issues:detail", args=(resolved_report.pk,)))
        self.assertContains(detail_response, "Resolution information")
        self.assertContains(detail_response, "Road surface repaired and inspected.")
        self.assertContains(detail_response, "Resolved:")
        self.assertContains(detail_response, "Delete Report")

    def test_resolved_report_status_is_visible_to_its_citizen(self):
        incident = Incident.objects.create(
            title="Resolved citizen issue", status=IncidentStatus.RESOLVED,
            resolution_notes="The drain has been cleared.", resolved_at=timezone.now(),
        )
        report = Issue.objects.create(
            reported_by=self.citizen, title="Blocked drain report", description="Drainage problem",
            incident=incident,
        )
        self.client.force_login(self.citizen)
        response = self.client.get(reverse("issues:detail", args=(report.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resolved")
        self.assertContains(response, "The drain has been cleared.")
        self.assertNotContains(response, "Delete Report")

    def test_only_admin_sees_delete_actions_and_get_never_deletes(self):
        report = Issue.objects.create(
            reported_by=self.citizen, title="Delete control check", description="Report content",
        )
        delete_url = reverse("issues:delete", args=(report.pk,))
        detail_url = reverse("issues:detail", args=(report.pk,))
        self.client.force_login(self.citizen)
        self.assertNotContains(self.client.get(detail_url), "Delete Report")
        self.assertNotContains(self.client.get(reverse("issues:list")), "Delete Report")
        self.assertEqual(self.client.post(delete_url).status_code, 403)
        self.assertTrue(Issue.objects.filter(pk=report.pk).exists())

        admin = User.objects.create_user(
            email="delete-control-admin@example.com", name="Delete Control Admin",
            password="CivicPass!2719", role=User.Role.ADMIN,
        )
        self.client.force_login(admin)
        self.assertContains(self.client.get(detail_url), "Delete Report")
        self.assertContains(self.client.get(reverse("issues:list")), "Delete Report")
        self.assertEqual(self.client.get(delete_url).status_code, 405)
        self.assertTrue(Issue.objects.filter(pk=report.pk).exists())

    def test_delete_requires_csrf_and_anonymous_user_cannot_delete(self):
        report = Issue.objects.create(
            reported_by=self.citizen, title="CSRF protected report", description="Report content",
        )
        delete_url = reverse("issues:delete", args=(report.pk,))
        strict_client = Client(enforce_csrf_checks=True)
        self.assertEqual(strict_client.post(delete_url).status_code, 403)
        self.assertTrue(Issue.objects.filter(pk=report.pk).exists())

        admin = User.objects.create_user(
            email="csrf-delete-admin@example.com", name="CSRF Delete Admin",
            password="CivicPass!2719", role=User.Role.ADMIN,
        )
        strict_client.force_login(admin)
        detail_response = strict_client.get(reverse("issues:detail", args=(report.pk,)))
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(strict_client.post(delete_url).status_code, 403)
        csrf_token = strict_client.cookies["csrftoken"].value
        response = strict_client.post(delete_url, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Issue.objects.filter(pk=report.pk).exists())

    def test_admin_delete_recalculates_shared_incident_count_location_and_severity(self):
        admin = User.objects.create_user(
            email="recalculate-delete-admin@example.com", name="Recalculate Delete Admin",
            password="CivicPass!2719", role=User.Role.ADMIN,
        )
        incident = Incident.objects.create(
            title="Shared pothole", category=Category.POTHOLE, priority=Priority.MEDIUM,
        )
        removed = Issue.objects.create(
            reported_by=self.citizen, title="First pothole report", description="First location",
            incident=incident, latitude="10.000000", longitude="20.000000",
            ai_priority=Priority.CRITICAL,
        )
        retained = Issue.objects.create(
            reported_by=self.other_citizen, title="Second pothole report", description="Second location",
            incident=incident, latitude="12.000000", longitude="24.000000",
            ai_priority=Priority.LOW,
        )
        from incidents.services import update_incident_intelligence
        update_incident_intelligence(incident)
        incident.refresh_from_db()
        old_severity = incident.severity_score

        self.client.force_login(admin)
        response = self.client.post(reverse("issues:delete", args=(removed.pk,)), follow=True)
        self.assertRedirects(response, reverse("issues:list"))
        self.assertContains(response, "Report deleted successfully.")
        self.assertNotContains(response, removed.issue_code)
        self.assertFalse(Issue.objects.filter(pk=removed.pk).exists())
        incident.refresh_from_db()
        self.assertEqual(incident.report_count, 1)
        self.assertEqual(str(incident.latitude), str(retained.latitude))
        self.assertEqual(str(incident.longitude), str(retained.longitude))
        self.assertEqual(
            incident.severity_score,
            calculate_incident_severity(incident, [retained]).score,
        )
        self.assertNotEqual(incident.severity_score, old_severity)

    def test_deleting_last_report_keeps_incident_history_and_clears_location(self):
        admin = User.objects.create_user(
            email="last-report-delete-admin@example.com", name="Last Report Delete Admin",
            password="CivicPass!2719", role=User.Role.ADMIN,
        )
        incident = Incident.objects.create(
            title="Only report incident", status=IncidentStatus.RESOLVED,
            latitude="10.000000", longitude="20.000000",
        )
        report = Issue.objects.create(
            reported_by=self.citizen, title="Only report", description="One submitted report",
            incident=incident, latitude="10.000000", longitude="20.000000",
        )
        history = IncidentStatusHistory.objects.create(
            incident=incident, old_status=IncidentStatus.IN_PROGRESS,
            new_status=IncidentStatus.RESOLVED, changed_by=admin,
        )
        from incidents.services import update_incident_intelligence
        update_incident_intelligence(incident)
        self.client.force_login(admin)
        self.client.post(reverse("issues:delete", args=(report.pk,)))

        incident.refresh_from_db()
        self.assertFalse(Issue.objects.filter(pk=report.pk).exists())
        self.assertEqual(incident.issues.count(), 0)
        self.assertEqual(incident.report_count, 0)
        self.assertIsNone(incident.latitude)
        self.assertIsNone(incident.longitude)
        self.assertEqual(incident.severity_score, calculate_incident_severity(incident, []).score)
        self.assertTrue(Incident.objects.filter(pk=incident.pk).exists())
        self.assertTrue(IncidentStatusHistory.objects.filter(pk=history.pk).exists())

    def test_admin_can_open_issue_detail_for_any_report(self):
        admin = User.objects.create_user(
            email="issue-detail-admin@example.com", name="Issue Detail Admin", password="CivicPass!2719",
            role=User.Role.ADMIN,
        )
        issue = Issue.objects.create(
            reported_by=self.other_citizen, title="Reviewable report", description="Admin review"
        )
        self.client.force_login(admin)
        response = self.client.get(reverse("issues:detail", args=(issue.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["issue"], issue)

    def test_admin_issue_detail_renders_map_for_coordinates(self):
        admin = User.objects.create_user(
            email="issue-map-admin@example.com", name="Issue Map Admin", password="CivicPass!2719",
            role=User.Role.ADMIN,
        )
        issue = Issue.objects.create(
            reported_by=self.other_citizen,
            title="Located report",
            description="Report with coordinates",
            latitude="0.000000",
            longitude="72.877700",
        )
        self.client.force_login(admin)
        response = self.client.get(reverse("issues:detail", args=(issue.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="detail-map"')
        self.assertContains(response, 'data-lat="0.000000"')
        self.assertContains(response, 'data-lng="72.877700"')
        self.assertContains(response, "leaflet@1.9.4/dist/leaflet.css")
        self.assertContains(response, "leaflet@1.9.4/dist/leaflet.js")
        self.assertContains(response, "maplibre-gl@5/dist/maplibre-gl.css")
        self.assertContains(response, "maplibre-gl@5/dist/maplibre-gl.js")
        self.assertContains(response, "@maplibre/maplibre-gl-leaflet@0.1.3/leaflet-maplibre-gl.js")
        self.assertContains(response, "https://tiles.openfreemap.org/styles/bright")
        self.assertContains(response, "OpenFreeMap © OpenMapTiles Data from OpenStreetMap")
        self.assertNotContains(response, "tile.openstreetmap.org")
        self.assertContains(response, "Number(mapElement.dataset.lat)")
        self.assertContains(response, "typeof window.L === 'undefined'")
        self.assertContains(response, "typeof window.maplibregl === 'undefined'")
        self.assertContains(response, "typeof window.L.maplibreGL !== 'function'")
        self.assertContains(response, 'id="detail-map-fallback"')
        self.assertContains(response, "Map could not be loaded. The report location is still available.")
        self.assertContains(response, "getMaplibreMap()")
        self.assertContains(response, "OpenFreeMap style or map layer failed to load.")
        self.assertContains(response, "The report map could not be initialized.")
        self.assertContains(response, "mapElement.dataset.leafletInitialized = 'true'")
        self.assertContains(response, "map.invalidateSize({ pan: false })")

    def test_citizen_issue_detail_renders_map_for_coordinates(self):
        issue = Issue.objects.create(
            reported_by=self.citizen,
            title="Located citizen report",
            description="Citizen report with coordinates",
            latitude="19.076000",
            longitude="0.000000",
        )
        self.client.force_login(self.citizen)
        response = self.client.get(reverse("issues:detail", args=(issue.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="detail-map"')
        self.assertContains(response, 'data-lat="19.076000"')
        self.assertContains(response, 'data-lng="0.000000"')
        self.assertContains(response, 'id="detail-map-fallback"')
        self.assertContains(response, "map.invalidateSize({ pan: false })")

    def test_issue_detail_shows_location_unavailable_without_coordinates(self):
        issue = Issue.objects.create(
            reported_by=self.citizen, title="Unlocated report", description="No coordinates"
        )
        self.client.force_login(self.citizen)
        response = self.client.get(reverse("issues:detail", args=(issue.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Location unavailable")
        self.assertNotContains(response, 'id="detail-map"')
        self.assertNotContains(response, "leaflet@1.9.4/dist/leaflet.js")

    def test_issue_detail_does_not_render_map_for_out_of_range_coordinates(self):
        invalid_coordinates = (("90.000001", "72.877700"), ("19.076000", "180.000001"))
        self.client.force_login(self.citizen)
        for index, (latitude, longitude) in enumerate(invalid_coordinates):
            with self.subTest(latitude=latitude, longitude=longitude):
                issue = Issue.objects.create(
                    reported_by=self.citizen,
                    title=f"Invalid location {index}",
                    description="Coordinates are outside valid ranges",
                    latitude=latitude,
                    longitude=longitude,
                )
                response = self.client.get(reverse("issues:detail", args=(issue.pk,)))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Location unavailable")
                self.assertNotContains(response, 'id="detail-map"')
                self.assertNotContains(response, "leaflet@1.9.4/dist/leaflet.js")

    def test_dashboard_only_shows_authenticated_citizens_issues(self):
        own = Issue.objects.create(reported_by=self.citizen, title="My issue", description="Mine")
        Issue.objects.create(reported_by=self.other_citizen, title="Private issue", description="Theirs")
        self.client.force_login(self.citizen)
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(list(response.context["issues"]), [own])
        self.assertContains(response, own.issue_code)
        self.assertNotContains(response, "Private issue")

    def test_admin_dashboard_shows_global_report_data(self):
        admin = User.objects.create_user(
            email="dashboard-admin@example.com", name="Dashboard Admin", password="CivicPass!2719",
            role=User.Role.ADMIN,
        )
        first = Issue.objects.create(reported_by=self.citizen, title="Citizen report", description="Mine")
        second = Issue.objects.create(
            reported_by=self.other_citizen, title="Another report", description="Theirs"
        )
        self.client.force_login(admin)
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(response.context["issues"], [first, second])

    def test_citizen_can_access_incident_linked_to_own_report(self):
        from issues.services import create_issue_with_incident

        own = create_issue_with_incident(
            issue=Issue(title="Mine", description="Mine", latitude="0.000000", longitude="72.877700"),
            reported_by=self.citizen,
        )
        incident = own.incident
        self.client.force_login(self.citizen)
        response = self.client.get(reverse("incidents:detail", args=(incident.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Report received")
        self.assertContains(response, 'id="incident-map"')
        self.assertContains(response, 'data-lat="0.000000"')
        self.assertContains(response, 'data-lng="72.877700"')
        self.assertContains(response, "Incident location")

    def test_citizen_cannot_access_unrelated_incident(self):
        unrelated = Incident.objects.create(title="Unrelated incident")
        self.client.force_login(self.citizen)
        self.assertEqual(self.client.get(reverse("incidents:detail", args=(unrelated.pk,))).status_code, 404)

    def test_admin_can_access_any_incident_detail(self):
        admin = User.objects.create_user(
            email="incident-detail-admin@example.com", name="Incident Detail Admin",
            password="CivicPass!2719", role=User.Role.ADMIN,
        )
        other_citizen = User.objects.create_user(
            email="incident-owner@example.com", name="Incident Owner", password="CivicPass!2719"
        )
        incident = Incident.objects.create(
            title="Another citizen incident", latitude="19.076000", longitude="0.000000"
        )
        Issue.objects.create(
            reported_by=other_citizen, title="Owner report", description="Linked evidence", incident=incident
        )
        self.client.force_login(admin)
        response = self.client.get(reverse("incidents:detail", args=(incident.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["incident"], incident)
        self.assertContains(response, "Owner report")
        self.assertContains(response, 'id="incident-map"')
        self.assertContains(response, 'data-lat="19.076000"')
        self.assertContains(response, 'data-lng="0.000000"')
        self.assertContains(response, "leaflet@1.9.4/dist/leaflet.js")
        self.assertContains(response, "maplibre-gl@5.0.1/dist/maplibre-gl.js")
        self.assertContains(response, "@maplibre/maplibre-gl-leaflet@0.1.3/leaflet-maplibre-gl.js")
        self.assertContains(response, "https://tiles.openfreemap.org/styles/bright")
        self.assertContains(response, "typeof window.L.maplibreGL !== 'function'")
        self.assertContains(response, "incident-map-fallback")
        self.assertContains(response, "OpenFreeMap ? OpenMapTiles Data from OpenStreetMap")
        self.assertContains(response, "map.invalidateSize({ pan: false })")
        self.assertNotContains(response, "tile.openstreetmap.org")


    def test_incident_detail_without_coordinates_shows_location_unavailable(self):
        incident = Incident.objects.create(title="Unlocated incident")
        Issue.objects.create(
            reported_by=self.citizen, title="Linked report", description="No location", incident=incident
        )
        self.client.force_login(self.citizen)
        response = self.client.get(reverse("incidents:detail", args=(incident.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Location unavailable")
        self.assertNotContains(response, 'id="incident-map"')
        self.assertNotContains(response, "leaflet@1.9.4/dist/leaflet.js")

    def test_incident_detail_with_out_of_range_coordinates_shows_location_unavailable(self):
        incident = Incident.objects.create(
            title="Invalid location incident", latitude="90.000001", longitude="72.877700"
        )
        Issue.objects.create(
            reported_by=self.citizen, title="Linked report", description="Invalid location", incident=incident
        )
        self.client.force_login(self.citizen)
        response = self.client.get(reverse("incidents:detail", args=(incident.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Location unavailable")
        self.assertNotContains(response, 'id="incident-map"')
        self.assertNotContains(response, "leaflet@1.9.4/dist/leaflet.js")


    def test_admin_reports_filters_combine_and_search_by_incident_id(self):
        admin = User.objects.create_user(
            email="inbox-admin@example.com", name="Inbox Admin", password="CivicPass!2719",
            role=User.Role.ADMIN,
        )
        sanitation = Department.objects.create(name="Inbox Sanitation")
        other_department = Department.objects.create(name="Inbox Electrical")
        active_unassigned = Incident.objects.create(
            title="Needle cleanup", category=Category.GARBAGE, priority=Priority.HIGH,
            status=IncidentStatus.IN_PROGRESS,
        )
        target = Issue.objects.create(
            reported_by=self.citizen, title="Needle near the park", description="Cleanup needed",
            incident=active_unassigned, ai_category=Category.GARBAGE,
        )
        resolved = Incident.objects.create(
            title="Resolved rubbish", category=Category.GARBAGE, priority=Priority.HIGH,
            status=IncidentStatus.RESOLVED, department=sanitation, assigned_to=admin,
        )
        resolved_report = Issue.objects.create(
            reported_by=self.other_citizen, title="Resolved rubbish report",
            description="Historical case", incident=resolved,
        )
        Issue.objects.create(
            reported_by=self.other_citizen, title="Electrical repair",
            description="Other category", incident=Incident.objects.create(
                title="Electrical repair", category=Category.STREETLIGHT,
                priority=Priority.LOW, status=IncidentStatus.IN_PROGRESS,
                department=other_department,
            ),
        )

        self.client.force_login(admin)
        combined = self.client.get(reverse("issues:list"), {
            "status": IncidentStatus.IN_PROGRESS,
            "priority": Priority.HIGH,
            "assignment": "unassigned",
            "search": active_unassigned.incident_code,
        })
        self.assertEqual(combined.status_code, 200)
        self.assertEqual(list(combined.context["issues"]), [target])
        self.assertContains(combined, "border-danger")

        resolved_by_department = self.client.get(reverse("issues:list"), {
            "status": IncidentStatus.RESOLVED,
            "department": sanitation.pk,
        })
        self.assertEqual(list(resolved_by_department.context["issues"]), [resolved_report])

        clear_response = self.client.get(reverse("issues:list"))
        self.assertEqual(clear_response.status_code, 200)
        self.assertContains(clear_response, "Clear filters")
        self.assertEqual(clear_response.context["report_counts"]["resolved"], 1)
        self.assertEqual(clear_response.context["report_counts"]["in_progress"], 2)

    def test_admin_report_pagination_keeps_search_query(self):
        admin = User.objects.create_user(
            email="pager-admin@example.com", name="Pager Admin", password="CivicPass!2719",
            role=User.Role.ADMIN,
        )
        for index in range(21):
            Issue.objects.create(
                reported_by=self.citizen,
                title=f"Needle report {index}",
                description="Searchable record",
            )
        self.client.force_login(admin)
        response = self.client.get(reverse("issues:list"), {"search": "Needle", "page": "2"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(len(response.context["issues"]), 1)
        self.assertContains(response, "search=Needle&amp;page=1")

    def test_admin_home_attention_and_department_workload_use_live_incidents(self):
        admin = User.objects.create_user(
            email="attention-admin@example.com", name="Attention Admin", password="CivicPass!2719",
            role=User.Role.ADMIN,
        )
        roads = Department.objects.create(name="Attention Roads")
        now = timezone.now()
        high = Incident.objects.create(
            title="Urgent street hazard", category=Category.ROAD_DAMAGE,
            priority=Priority.CRITICAL, status=IncidentStatus.IN_PROGRESS,
            department=roads, assigned_to=admin, created_at=now - timezone.timedelta(hours=30),
        )
        unassigned_old = Incident.objects.create(
            title="Unassigned drain", category=Category.DRAINAGE,
            priority=Priority.MEDIUM, status=IncidentStatus.REPORTED,
            created_at=now - timezone.timedelta(days=5),
        )
        resolved = Incident.objects.create(
            title="Completed road repair", priority=Priority.HIGH,
            status=IncidentStatus.RESOLVED, department=roads,
        )
        high_report = Issue.objects.create(
            reported_by=self.citizen, title="Urgent street hazard report",
            description="Traffic danger", incident=high,
        )
        old_report = Issue.objects.create(
            reported_by=self.other_citizen, title="Unassigned drain report",
            description="Drain issue", incident=unassigned_old,
        )
        Issue.objects.create(
            reported_by=self.citizen, title="Completed road report",
            description="Already complete", incident=resolved,
        )
        self.client.force_login(admin)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        attention = response.context["attention_items"]
        self.assertIn(high_report, [item["issue"] for item in attention])
        self.assertIn(old_report, [item["issue"] for item in attention])
        self.assertTrue(any("Overdue" in item["reason"] for item in attention))
        workload = list(response.context["department_workload"])
        self.assertEqual([(row.name, row.active_incident_count) for row in workload], [
            ("Attention Roads", 1),
        ])
        self.assertEqual(response.context["resolved_report_count"], 1)

    def test_progress_tracker_uses_recorded_history_for_admin_and_citizen(self):
        admin = User.objects.create_user(
            email="progress-admin@example.com", name="Progress Admin", password="CivicPass!2719",
            role=User.Role.ADMIN,
        )
        incident = Incident.objects.create(
            title="Tracked pothole", status=IncidentStatus.IN_PROGRESS,
        )
        history_time = timezone.now() - timezone.timedelta(hours=2)
        IncidentStatusHistory.objects.create(
            incident=incident, old_status=IncidentStatus.REPORTED,
            new_status=IncidentStatus.VERIFIED, created_at=history_time,
        )
        IncidentStatusHistory.objects.create(
            incident=incident, old_status=IncidentStatus.VERIFIED,
            new_status=IncidentStatus.ASSIGNED, created_at=history_time + timezone.timedelta(minutes=30),
        )
        IncidentStatusHistory.objects.create(
            incident=incident, old_status=IncidentStatus.ASSIGNED,
            new_status=IncidentStatus.IN_PROGRESS, created_at=history_time + timezone.timedelta(hours=1),
        )
        report = Issue.objects.create(
            reported_by=self.citizen, title="Tracked report", description="Progress evidence",
            incident=incident,
        )
        for user in (self.citizen, admin):
            self.client.force_login(user)
            response = self.client.get(reverse("issues:detail", args=(report.pk,)))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Complaint progress")
            self.assertContains(response, "Verified")
            self.assertContains(response, "Assigned")
            self.assertContains(response, "Work in progress")
            self.assertContains(response, 'aria-current="step"')
            self.assertContains(response, "Latest update")

    def test_citizen_does_not_see_admin_reopen_or_overdue_controls(self):
        incident = Incident.objects.create(
            title="Old citizen case", status=IncidentStatus.IN_PROGRESS,
            priority=Priority.CRITICAL, created_at=timezone.now() - timezone.timedelta(days=2),
        )
        report = Issue.objects.create(
            reported_by=self.citizen, title="Old report", description="Still open", incident=incident,
        )
        self.client.force_login(self.citizen)
        response = self.client.get(reverse("issues:detail", args=(report.pk,)))
        self.assertContains(response, "Taking longer than expected")
        self.assertNotContains(response, "Overdue")
        self.assertNotContains(response, "24 hours")
        self.assertNotContains(response, "Reopen case")
        self.assertNotContains(response, "Delete Report")


class IncidentAggregationTests(TestCase):
    def setUp(self):
        self.citizen = User.objects.create_user(
            email="intelligence@example.com", name="Intelligence Citizen", password="CivicPass!2719"
        )

    def submit(self, *, title, description, category="Pothole", priority="MEDIUM", latitude=None, longitude=None):
        issue = Issue(
            title=title,
            description=description,
            latitude=latitude,
            longitude=longitude,
        )
        return create_issue_with_incident(
            issue=issue,
            reported_by=self.citizen,
            triage_result={
                "category": category,
                "priority": priority,
                "department": "Road Maintenance" if category in ("Pothole", "Road Damage") else "General",
                "summary": description[:100],
                "confidence": 0.8,
            },
        )

    def test_clearly_unrelated_category_gets_separate_incident(self):
        first = self.submit(
            title="Pothole at Cedar Street", description="Large pothole near Cedar Street.",
            latitude="19.076000", longitude="72.877700",
        )
        unrelated = self.submit(
            title="Garbage at Cedar Street", description="Waste bags are piling up at the same corner.",
            category="Garbage", latitude="19.076001", longitude="72.877701",
        )
        self.assertNotEqual(first.incident_id, unrelated.incident_id)

    def test_nearby_same_category_reports_aggregate(self):
        first = self.submit(
            title="Large pothole on Cedar Street", description="Deep hole in roadway by the bus stop.",
            latitude="19.076000", longitude="72.877700",
        )
        second = self.submit(
            title="Road cavity by Cedar Street bus stop", description="Vehicles swerve around the damaged surface.",
            latitude="19.076500", longitude="72.877700",
        )
        self.assertEqual(first.incident_id, second.incident_id)
        first.incident.refresh_from_db()
        self.assertEqual(first.incident.report_count, 2)
        self.assertEqual(first.incident.issues.count(), 2)

    def test_text_similar_reports_aggregate_without_coordinates(self):
        first = self.submit(
            title="Pothole outside Cedar Street library",
            description="A deep pothole outside the Cedar Street library blocks cyclists.",
        )
        second = self.submit(
            title="Pothole reported outside Cedar Street library",
            description="A deep pothole outside the Cedar Street library blocks cyclists.",
        )
        self.assertEqual(first.incident_id, second.incident_id)
        self.assertIsNone(first.latitude)
        first.incident.refresh_from_db()
        self.assertEqual(first.incident.report_count, 2)

    def test_match_score_explains_missing_coordinates_and_threshold(self):
        first = self.submit(
            title="Pothole outside library", description="Deep pothole blocks the cycle lane."
        )
        new_issue = Issue(
            title="Pothole outside library", description="Deep pothole blocks the cycle lane.",
            ai_category="Pothole",
        )
        match = score_incident_match(new_issue, first.incident)
        self.assertIsNone(match.reasons["distance_km"])
        self.assertFalse(match.reasons["within_location_radius"])
        self.assertTrue(match.reasons["category_match"])
        self.assertGreaterEqual(match.score, DUPLICATE_THRESHOLD)
        self.assertTrue(match.reasons["threshold_met"])

    def test_identical_report_with_ai_category_variation_uses_prior_validated_category(self):
        first = self.submit(
            title="Street pothole", description="There is a pothole near the library.",
            category="Pothole",
        )
        triage_result = {
            "category": "Road Damage",
            "priority": "HIGH",
            "department": "Road Maintenance",
            "summary": "There is a pothole near the library.",
            "confidence": 0.8,
        }
        captured_matches = []

        def capture_match(issue):
            match = find_related_incident(issue)
            captured_matches.append(match)
            return match

        with patch("issues.services.find_related_incident", side_effect=capture_match):
            second = create_issue_with_incident(
                issue=Issue(
                    title="Street pothole",
                    description="There is a pothole near the library.",
                ),
                reported_by=self.citizen,
                triage_result=triage_result,
            )

        match = captured_matches[0]
        self.assertEqual(second.ai_category, "Road Damage")
        self.assertEqual(second.incident_id, first.incident_id)
        self.assertEqual(match.incident.pk, first.incident_id)
        self.assertEqual(match.score, 0.65)
        self.assertEqual(match.reasons["text_similarity"], 1.0)
        self.assertTrue(match.reasons["category_match"])
        self.assertEqual(match.reasons["category_match_source"], "identical_prior_report")
        self.assertEqual(Issue.objects.count(), 2)
        self.assertEqual(Incident.objects.count(), 1)

    def test_identical_same_category_reports_without_coordinates_preserve_incident(self):
        self.client.force_login(self.citizen)
        title = "Street pothole"
        description = "There is a pothole near the library."
        triage_result = {
            "category": "Pothole",
            "priority": "MEDIUM",
            "department": "Road Maintenance",
            "summary": description,
            "confidence": 0.8,
        }
        url = reverse("issues:create")
        with patch("issues.views.triage_issue", return_value=triage_result):
            first_response = self.client.post(url, {"title": title, "description": description})
        self.assertEqual(first_response.status_code, 302)
        first = Issue.objects.get()
        incident = first.incident
        department = Department.objects.create(name="Admin Road Response")
        incident.category = Category.POTHOLE
        incident.priority = Priority.CRITICAL
        incident.department = department
        incident.status = IncidentStatus.VERIFIED
        incident.severity_score = 73.5
        incident.save()

        captured_matches = []

        def capture_match(issue):
            match = find_related_incident(issue)
            captured_matches.append(match)
            return match

        with (
            patch("issues.views.triage_issue", return_value=triage_result),
            patch("issues.services.find_related_incident", side_effect=capture_match),
        ):
            second_response = self.client.post(url, {"title": title, "description": description})
        self.assertEqual(second_response.status_code, 302)
        second = Issue.objects.exclude(pk=first.pk).get()

        match = score_incident_match(second, incident, now=incident.created_at)
        incident.refresh_from_db()
        self.assertEqual(captured_matches[0].score, 0.65)
        self.assertEqual(captured_matches[0].incident.pk, incident.pk)
        self.assertEqual(second.ai_category, "Pothole")
        self.assertEqual(second.incident_id, first.incident_id)
        self.assertEqual(Incident.objects.count(), 1)
        self.assertEqual(incident.report_count, 2)
        self.assertEqual(match.score, 0.65)
        self.assertEqual(match.reasons["category_match_source"], "current_issue")
        self.assertIsNone(first.latitude)
        self.assertIsNone(second.latitude)
        self.assertEqual(incident.category, Category.POTHOLE)
        self.assertEqual(incident.priority, Priority.CRITICAL)
        self.assertEqual(incident.department, department)
        self.assertEqual(incident.status, IncidentStatus.VERIFIED)
        self.assertEqual(incident.severity_score, 73.5)

    @patch("incidents.intelligence.DUPLICATE_THRESHOLD", 0.99)
    def test_report_below_configured_threshold_is_not_merged(self):
        first = self.submit(
            title="Pothole on Cedar Street", description="Large hole in road.",
            latitude="19.076000", longitude="72.877700",
        )
        second = self.submit(
            title="Pothole near Cedar Street", description="Damaged roadway.",
            latitude="19.076010", longitude="72.877700",
        )
        self.assertNotEqual(first.incident_id, second.incident_id)

    def test_aggregation_recalculates_count_location_and_preserves_admin_fields(self):
        first = self.submit(
            title="Pothole near Cedar Street", description="Large pothole in road.",
            latitude="19.076000", longitude="72.877000", priority="MEDIUM",
        )
        incident = first.incident
        incident.category = Category.POTHOLE
        incident.priority = Priority.LOW
        incident.status = IncidentStatus.VERIFIED
        incident.department = Department.objects.create(name="Admin Assigned Roads")
        incident.severity_score = 31.5
        incident.save()

        second = self.submit(
            title="Pothole at Cedar Street", description="Large pothole in road.",
            latitude="19.078000", longitude="72.879000", priority="HIGH",
        )
        incident.refresh_from_db()
        self.assertEqual(second.incident_id, incident.pk)
        self.assertEqual(incident.report_count, 2)
        self.assertAlmostEqual(float(incident.latitude), 19.077, places=5)
        self.assertAlmostEqual(float(incident.longitude), 72.878, places=5)
        self.assertEqual(incident.category, Category.POTHOLE)
        self.assertEqual(incident.priority, Priority.LOW)
        self.assertEqual(incident.status, IncidentStatus.VERIFIED)
        self.assertEqual(incident.department.name, "Admin Assigned Roads")
        self.assertEqual(incident.severity_score, 31.5)

    def test_duplicate_report_does_not_replace_admin_edited_incident_values(self):
        first = self.submit(
            title="Pothole near school gate", description="A large hole blocks the main gate."
        )
        incident = first.incident
        incident.category = Category.ROAD_DAMAGE
        incident.priority = Priority.CRITICAL
        incident.department = Department.objects.create(name="Admin Road Response")
        incident.status = IncidentStatus.IN_PROGRESS
        incident.severity_score = 88.0
        incident.save()

        duplicate = self.submit(
            title="Pothole near school gate", description="A large hole blocks the main gate.",
            category="Pothole", priority="LOW",
        )

        incident.refresh_from_db()
        self.assertEqual(duplicate.incident_id, incident.pk)
        self.assertEqual(incident.category, Category.ROAD_DAMAGE)
        self.assertEqual(incident.priority, Priority.CRITICAL)
        self.assertEqual(incident.department.name, "Admin Road Response")
        self.assertEqual(incident.status, IncidentStatus.IN_PROGRESS)
        self.assertEqual(incident.severity_score, 88.0)

    def test_intelligence_error_rolls_back_partial_merge_and_creates_separate_incident(self):
        first = self.submit(
            title="Pothole near Cedar Street", description="Large pothole blocks the road.",
            latitude="19.076000", longitude="72.877700",
        )
        with patch("issues.services.update_incident_intelligence", side_effect=RuntimeError("simulated")):
            second = self.submit(
                title="Pothole near Cedar Street", description="Large pothole blocks the road.",
                latitude="19.076001", longitude="72.877701",
            )
        first.incident.refresh_from_db()
        self.assertNotEqual(first.incident_id, second.incident_id)
        self.assertEqual(first.incident.report_count, 1)
        self.assertEqual(second.incident.report_count, 1)
        self.assertEqual(second.incident.category, "Pothole")
        self.assertEqual(second.incident.priority, "MEDIUM")
        self.assertEqual(second.incident.department.name, "Road Maintenance")
        self.assertEqual(IncidentStatusHistory.objects.filter(incident=second.incident).count(), 1)

    def test_matching_service_failure_does_not_block_submission(self):
        with patch("issues.services.find_related_incident", side_effect=RuntimeError("matching unavailable")):
            issue = self.submit(title="Pothole", description="Road is damaged.")
        self.assertTrue(Issue.objects.filter(pk=issue.pk, incident__isnull=False).exists())
        self.assertEqual(issue.incident.report_count, 1)
