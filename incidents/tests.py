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
from django.utils import timezone
from django.urls import reverse
from datetime import timedelta

from issues.models import Category, Department, Issue, Priority
from .intelligence import calculate_incident_severity
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


class IncidentSeverityTests(TestCase):
    def test_severity_explains_report_priority_persistence_and_location(self):
        now = timezone.now()
        incident = Incident.objects.create(title="Persistent road hazard", priority=Priority.LOW)
        older_report = Issue.objects.create(
            title="First report",
            description="Pothole",
            incident=incident,
            ai_priority=Priority.HIGH,
            latitude="19.076000",
            longitude="72.877700",
            created_at=now - timedelta(days=7),
        )
        newer_report = Issue.objects.create(
            title="Second report",
            description="Pothole again",
            incident=incident,
            ai_priority=Priority.CRITICAL,
            created_at=now,
        )

        assessment = calculate_incident_severity(incident, [older_report, newer_report], now=now)

        self.assertEqual(assessment.score, 70.0)
        self.assertEqual(assessment.factors["additional_report_points"], 5)
        self.assertEqual(assessment.factors["highest_priority"], Priority.CRITICAL)
        self.assertEqual(assessment.factors["persistence_points"], 10.0)
        self.assertTrue(assessment.factors["location_present"])
        incident.refresh_from_db()
        self.assertEqual(incident.priority, Priority.LOW)

    def test_severity_without_location_is_bounded_and_explained(self):
        incident = Incident.objects.create(title="Unlocated issue", priority=Priority.MEDIUM)
        report = Issue.objects.create(
            title="Unlocated report", description="No coordinates", incident=incident,
            ai_priority=Priority.MEDIUM,
        )
        assessment = calculate_incident_severity(incident, [report])
        self.assertEqual(assessment.score, 32.0)
        self.assertFalse(assessment.factors["location_present"])
        self.assertGreaterEqual(assessment.score, 0)
        self.assertLessEqual(assessment.score, 100)


class AdminIncidentWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="workflow-admin@example.com", name="Workflow Admin", password="CivicPass!2719",
            role=User.Role.ADMIN,
        )
        self.operator = User.objects.create_user(
            email="operator@example.com", name="Incident Operator", password="CivicPass!2719",
            role=User.Role.ADMIN,
        )
        self.citizen = User.objects.create_user(
            email="workflow-citizen@example.com", name="Workflow Citizen", password="CivicPass!2719",
        )
        self.department = Department.objects.create(name="Initial Department")
        self.new_department = Department.objects.create(name="Assigned Department")
        self.incident = Incident.objects.create(
            title="Pothole at Main Gate",
            category=Category.POTHOLE,
            priority=Priority.HIGH,
            department=self.department,
            report_count=3,
            severity_score=72.5,
        )
        self.issue = Issue.objects.create(
            reported_by=self.citizen,
            title="Large pothole report",
            description="A pothole blocks the cycle lane.",
            ai_category=Category.POTHOLE,
            ai_priority=Priority.HIGH,
            ai_summary="Pothole blocking the cycle lane.",
            ai_confidence=0.85,
            incident=self.incident,
        )

    def post_data(self, **overrides):
        data = {
            "department": str(self.department.pk),
            "assigned_to": "",
            "status": IncidentStatus.REPORTED,
            "resolution_notes": "",
            "status_comment": "",
        }
        data.update(overrides)
        return data

    def test_anonymous_users_are_redirected_from_management_routes(self):
        for url in (
            reverse("incidents:admin_dashboard"),
            reverse("incidents:admin_detail", args=(self.incident.pk,)),
        ):
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}")

    def test_citizen_cannot_access_dashboard_or_modify_incident(self):
        self.client.force_login(self.citizen)
        response = self.client.get(reverse("incidents:admin_dashboard"))
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            reverse("incidents:admin_detail", args=(self.incident.pk,)),
            self.post_data(status=IncidentStatus.RESOLVED, resolution_notes="Unauthorized"),
        )
        self.assertEqual(response.status_code, 403)
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, IncidentStatus.REPORTED)
        self.assertEqual(self.incident.resolution_notes, "")
        self.assertFalse(self.incident.status_history.exists())

    def test_admin_can_view_dashboard_and_review_linked_reports(self):
        self.client.force_login(self.admin)
        dashboard_response = self.client.get(reverse("incidents:admin_dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(list(dashboard_response.context["incidents"]), [self.incident])
        detail_response = self.client.get(reverse("incidents:admin_detail", args=(self.incident.pk,)))
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(list(detail_response.context["issues"]), [self.issue])
        self.assertEqual(detail_response.context["incident"].severity_score, 72.5)

    def test_dashboard_filters_status_priority_category_and_department(self):
        other_department = Department.objects.create(name="Other Department")
        other = Incident.objects.create(
            title="Streetlight out", category=Category.STREETLIGHT,
            priority=Priority.LOW, status=IncidentStatus.VERIFIED, department=other_department,
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("incidents:admin_dashboard"), {
            "status": IncidentStatus.REPORTED,
            "priority": Priority.HIGH,
            "category": Category.POTHOLE,
            "department": self.department.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["incidents"]), [self.incident])
        self.assertNotIn(other, response.context["incidents"])

    def test_admin_can_assign_department_and_existing_operator_field(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("incidents:admin_detail", args=(self.incident.pk,)),
            self.post_data(department=str(self.new_department.pk), assigned_to=str(self.operator.pk)),
        )
        self.assertRedirects(response, reverse("incidents:admin_detail", args=(self.incident.pk,)))
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.department, self.new_department)
        self.assertEqual(self.incident.assigned_to, self.operator)
        self.assertEqual(Incident.objects.count(), 1)
        self.assertEqual(self.incident.report_count, 3)
        self.assertEqual(self.incident.severity_score, 72.5)
        self.assertEqual(self.issue.incident_id, self.incident.pk)
        self.assertFalse(self.incident.status_history.exists())

    def test_each_status_change_records_old_new_time_admin_and_comment(self):
        self.client.force_login(self.admin)
        detail_url = reverse("incidents:admin_detail", args=(self.incident.pk,))
        self.client.post(detail_url, self.post_data(
            status=IncidentStatus.VERIFIED, status_comment="Reviewed by operations.",
        ))
        self.client.post(detail_url, self.post_data(
            status=IncidentStatus.IN_PROGRESS, status_comment="Crew dispatched.",
        ))
        history = list(self.incident.status_history.all())
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].old_status, IncidentStatus.VERIFIED)
        self.assertEqual(history[0].new_status, IncidentStatus.IN_PROGRESS)
        self.assertEqual(history[0].changed_by, self.admin)
        self.assertEqual(history[0].comment, "Crew dispatched.")
        self.assertIsNotNone(history[0].created_at)
        self.assertEqual(history[1].old_status, IncidentStatus.REPORTED)
        self.assertEqual(history[1].new_status, IncidentStatus.VERIFIED)

    def test_resolution_records_notes_timestamp_and_status_history(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("incidents:admin_detail", args=(self.incident.pk,)),
            self.post_data(
                status=IncidentStatus.RESOLVED,
                resolution_notes="The road crew filled and inspected the pothole.",
                status_comment="Resolution verified on site.",
            ),
        )
        self.assertRedirects(response, reverse("incidents:admin_detail", args=(self.incident.pk,)))
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, IncidentStatus.RESOLVED)
        self.assertEqual(self.incident.resolution_notes, "The road crew filled and inspected the pothole.")
        self.assertIsNotNone(self.incident.resolved_at)
        history = self.incident.status_history.get()
        self.assertEqual(history.old_status, IncidentStatus.REPORTED)
        self.assertEqual(history.new_status, IncidentStatus.RESOLVED)
        self.assertEqual(history.changed_by, self.admin)
        self.assertEqual(history.comment, "Resolution verified on site.")

    def test_invalid_post_does_not_change_any_incident_fields_or_history(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("incidents:admin_detail", args=(self.incident.pk,)),
            self.post_data(
                department=str(self.new_department.pk),
                status="NOT_A_STATUS",
                resolution_notes="Must not be saved",
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.department, self.department)
        self.assertEqual(self.incident.status, IncidentStatus.REPORTED)
        self.assertEqual(self.incident.resolution_notes, "")
        self.assertEqual(self.incident.report_count, 3)
        self.assertEqual(self.incident.severity_score, 72.5)
        self.assertEqual(self.incident.issues.count(), 1)
        self.assertFalse(self.incident.status_history.exists())

    def test_reopening_incident_clears_current_resolved_timestamp_but_keeps_notes(self):
        self.incident.status = IncidentStatus.RESOLVED
        self.incident.resolution_notes = "Resolved repair details"
        self.incident.resolved_at = timezone.now()
        self.incident.save()
        self.client.force_login(self.admin)
        self.client.post(
            reverse("incidents:admin_detail", args=(self.incident.pk,)),
            self.post_data(
                status=IncidentStatus.IN_PROGRESS,
                resolution_notes="Resolved repair details",
                status_comment="Issue has reoccurred.",
            ),
        )
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, IncidentStatus.IN_PROGRESS)
        self.assertEqual(self.incident.resolution_notes, "Resolved repair details")
        self.assertIsNone(self.incident.resolved_at)
        history = self.incident.status_history.get()
        self.assertEqual(history.old_status, IncidentStatus.RESOLVED)
        self.assertEqual(history.new_status, IncidentStatus.IN_PROGRESS)
