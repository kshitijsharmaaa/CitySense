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
from django.contrib.auth import get_user_model
from django.db import IntegrityError

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
