"""
accounts/tests.py

Backend tests for the CitySense custom user model.

Tests cover:
- User creation with email-based auth
- Email uniqueness constraint
- Password hashing (no plaintext storage)
- Role assignment defaults and explicit values
- Superuser creation
"""

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.core.management import call_command, CommandError
from io import StringIO
from unittest.mock import patch

User = get_user_model()


class UserCreationTests(TestCase):

    def test_create_citizen_user_defaults(self):
        """A user created without explicit role defaults to CITIZEN."""
        user = User.objects.create_user(
            email="citizen@example.com",
            name="Test Citizen",
            password="securepass123",
        )
        self.assertEqual(user.email, "citizen@example.com")
        self.assertEqual(user.name, "Test Citizen")
        self.assertEqual(user.role, User.Role.CITIZEN)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)

    def test_create_admin_user_role(self):
        """A user can be created with ADMIN role explicitly."""
        user = User.objects.create_user(
            email="admin@example.com",
            name="Test Admin",
            password="securepass123",
            role=User.Role.ADMIN,
        )
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_admin_user)
        self.assertFalse(user.is_citizen)

    def test_password_is_hashed(self):
        """Password must never be stored in plaintext."""
        user = User.objects.create_user(
            email="hash@example.com",
            name="Hash Test",
            password="plaintext_password",
        )
        # The stored password field must NOT equal the raw input
        self.assertNotEqual(user.password, "plaintext_password")
        # Django's check_password must still succeed
        self.assertTrue(user.check_password("plaintext_password"))

    def test_email_uniqueness(self):
        """Duplicate emails must raise IntegrityError."""
        User.objects.create_user(
            email="duplicate@example.com",
            name="First",
            password="pass1",
        )
        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                email="duplicate@example.com",
                name="Second",
                password="pass2",
            )

    def test_email_is_normalised(self):
        """Email domain is lowercased during normalisation."""
        user = User.objects.create_user(
            email="Test@EXAMPLE.COM",
            name="Norm Test",
            password="pass",
        )
        self.assertEqual(user.email, "Test@example.com")

    def test_create_superuser(self):
        """Superuser has is_staff, is_superuser, and ADMIN role."""
        su = User.objects.create_superuser(
            email="super@example.com",
            name="Super User",
            password="superpass",
        )
        self.assertTrue(su.is_staff)
        self.assertTrue(su.is_superuser)
        self.assertEqual(su.role, User.Role.ADMIN)

    def test_missing_email_raises(self):
        """Creating a user without email raises ValueError."""
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", name="No Email", password="pass")

    def test_str_representation(self):
        """__str__ shows name, email and role."""
        user = User.objects.create_user(
            email="str@example.com",
            name="String User",
            password="pass",
        )
        self.assertIn("str@example.com", str(user))
        self.assertIn("String User", str(user))


class AuthenticationViewTests(TestCase):
    def test_registration_creates_hashed_citizen_and_logs_in(self):
        response = self.client.post(reverse("accounts:register"), {
            "name": "New Citizen",
            "email": "  NewCitizen@Example.COM ",
            "password1": "CivicPass!2719",
            "password2": "CivicPass!2719",
        })
        self.assertRedirects(response, reverse("dashboard:index"))
        user = User.objects.get(email="newcitizen@example.com")
        self.assertEqual(user.role, User.Role.CITIZEN)
        self.assertNotEqual(user.password, "CivicPass!2719")
        self.assertTrue(user.check_password("CivicPass!2719"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_registration_rejects_duplicate_email_case_insensitively(self):
        User.objects.create_user("person@example.com", "Existing", "CivicPass!2719")
        response = self.client.post(reverse("accounts:register"), {
            "name": "Duplicate",
            "email": "PERSON@EXAMPLE.COM",
            "password1": "CivicPass!2719",
            "password2": "CivicPass!2719",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)
        self.assertContains(response, "already exists")

    def test_registration_ignores_attempt_to_choose_admin_role(self):
        response = self.client.post(reverse("accounts:register"), {
            "name": "Self Admin",
            "email": "selfadmin@example.com",
            "password1": "CivicPass!2719",
            "password2": "CivicPass!2719",
            "role": User.Role.ADMIN,
        })
        self.assertRedirects(response, reverse("dashboard:index"))
        self.assertEqual(User.objects.get(email="selfadmin@example.com").role, User.Role.CITIZEN)

    def test_registration_rejects_password_mismatch(self):
        response = self.client.post(reverse("accounts:register"), {
            "name": "Mismatch",
            "email": "mismatch@example.com",
            "password1": "CivicPass!2719",
            "password2": "DifferentPass!18",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="mismatch@example.com").exists())

    def test_valid_login_uses_email_and_redirects_to_dashboard(self):
        User.objects.create_user("login@example.com", "Login Citizen", "CivicPass!2719")
        response = self.client.post(reverse("accounts:login"), {
            "username": "LOGIN@EXAMPLE.COM",
            "password": "CivicPass!2719",
        })
        self.assertRedirects(response, reverse("dashboard:index"))

    def test_invalid_login_is_rejected(self):
        response = self.client.post(reverse("accounts:login"), {
            "username": "nobody@example.com",
            "password": "WrongPassword!18",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct Email address and password.")

    def test_logout_invalidates_session_and_redirects_to_login(self):
        user = User.objects.create_user("logout@example.com", "Logout Citizen", "CivicPass!2719")
        self.client.force_login(user)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)


class EnsureDemoAdminCommandTests(TestCase):
    ENV = {
        "DEMO_ADMIN_EMAIL": "demo-admin@example.com",
        "DEMO_ADMIN_NAME": "Demo Administrator",
        "DEMO_ADMIN_PASSWORD": "Violet7_River!Stone2026",
    }

    @patch.dict("os.environ", ENV)
    def test_command_creates_one_admin_idempotently_without_printing_password(self):
        output = StringIO()
        call_command("ensure_demo_admin", stdout=output)
        call_command("ensure_demo_admin", stdout=output)

        self.assertEqual(User.objects.count(), 1)
        user = User.objects.get(email=self.ENV["DEMO_ADMIN_EMAIL"])
        self.assertEqual(user.name, self.ENV["DEMO_ADMIN_NAME"])
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(self.ENV["DEMO_ADMIN_PASSWORD"]))
        self.assertNotIn(self.ENV["DEMO_ADMIN_PASSWORD"], output.getvalue())

    @patch.dict("os.environ", ENV)
    def test_command_upgrades_the_matching_existing_account(self):
        user = User.objects.create_user(
            email=self.ENV["DEMO_ADMIN_EMAIL"],
            name="Old Name",
            password="OldCivicPassword!2026",
            role=User.Role.CITIZEN,
            is_staff=False,
            is_active=False,
        )

        call_command("ensure_demo_admin")

        user.refresh_from_db()
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(user.name, self.ENV["DEMO_ADMIN_NAME"])
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(self.ENV["DEMO_ADMIN_PASSWORD"]))

    @patch.dict("os.environ", {
        "DEMO_ADMIN_EMAIL": "",
        "DEMO_ADMIN_NAME": "",
        "DEMO_ADMIN_PASSWORD": "",
    })
    def test_command_requires_all_configuration_without_creating_a_user(self):
        with self.assertRaises(CommandError):
            call_command("ensure_demo_admin")
        self.assertFalse(User.objects.exists())
