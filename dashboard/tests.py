from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from incidents.models import Incident, IncidentStatus
from issues.models import Issue


User = get_user_model()


class PersonalizedDashboardTests(TestCase):
    def setUp(self):
        self.citizen = User.objects.create_user(
            "palak@example.com", "Palak Sharma", "CivicPass!2719"
        )
        self.other_citizen = User.objects.create_user(
            "other@example.com", "Other Citizen", "CivicPass!2719"
        )
        self.active_incident = Incident.objects.create(
            title="Streetlight outage", status=IncidentStatus.IN_PROGRESS
        )
        self.resolved_incident = Incident.objects.create(
            title="Resolved road damage", status=IncidentStatus.RESOLVED
        )
        Issue.objects.create(
            reported_by=self.citizen, title="My active report", description="Active",
            incident=self.active_incident, latitude="19.076000", longitude="72.877700",
        )
        Issue.objects.create(
            reported_by=self.other_citizen, title="Private other report", description="Other",
            incident=self.active_incident,
        )
        Issue.objects.create(
            reported_by=self.citizen, title="My resolved report", description="Resolved",
            incident=self.resolved_incident, latitude="19.080000", longitude="72.880000",
        )
        Issue.objects.create(
            reported_by=self.citizen, title="My unlinked report", description="Unlinked",
        )
        self.client.force_login(self.citizen)

    def test_dashboard_is_scoped_and_personal_counts_are_database_aggregated(self):
        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Good ")
        self.assertContains(response, "Palak")
        self.assertContains(response, "My active report")
        self.assertNotContains(response, "Private other report")
        self.assertEqual(response.context["stats"], {
            "total": 3,
            "active": 2,
            "in_progress": 1,
            "resolved": 1,
            "linked": 2,
            "incident_count": 2,
        })
        self.assertEqual(response.context["other_report_count"], 1)

    def test_dashboard_personalizes_locations_from_own_located_reports(self):
        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(len(response.context["city_report_points"]), 2)
        self.assertContains(response, "cs-city-personal-report")

    def test_empty_citizen_dashboard_uses_personalized_call_to_action(self):
        Issue.objects.filter(reported_by=self.citizen).delete()

        response = self.client.get(reverse("dashboard:index"))

        self.assertContains(response, "Your CitySense activity starts here.")
        self.assertContains(response, "help your community respond faster")
        self.assertEqual(response.context["stats"]["total"], 0)

    def test_profile_is_authenticated_and_shows_only_users_own_activity(self):
        response = self.client.get(reverse("dashboard:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Palak Sharma")
        self.assertContains(response, "palak@example.com")
        self.assertContains(response, "Citizen")
        self.assertEqual(response.context["stats"]["total"], 3)
        self.assertNotContains(response, "Private other report")

    def test_anonymous_user_is_redirected_from_profile(self):
        self.client.logout()

        response = self.client.get(reverse("dashboard:profile"))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('dashboard:profile')}",
        )

    def test_dashboard_keeps_existing_dark_theme_controls_available(self):
        response = self.client.get(reverse("dashboard:index"))

        self.assertContains(response, "data-theme-toggle")
        self.assertContains(response, "citysense-theme")
        self.assertContains(response, "js/main.js")

    def test_admin_dashboard_keeps_global_incident_metrics(self):
        admin = User.objects.create_user(
            "admin@example.com", "CitySense Admin", "CivicPass!2719", role=User.Role.ADMIN
        )
        self.client.force_login(admin)

        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(response.context["stats"]["total"], 4)
        self.assertEqual(response.context["stats"]["active"], 1)
        self.assertEqual(response.context["stats"]["resolved"], 1)
        self.assertEqual(response.context["stats"]["in_progress"], 1)
