"""
accounts/models.py

Custom User model for CitySense.

Key decisions:
- Email is the authentication identifier (not username).
- Roles: CITIZEN and ADMIN — used for authorization throughout the app.
- Extends AbstractBaseUser + PermissionsMixin for full Django auth compatibility,
  including Django admin support.
- UserManager handles create_user / create_superuser without a username field.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class CitySenseUserManager(BaseUserManager):
    """Manager that uses email as the unique identifier instead of username."""

    def create_user(self, email, name, password=None, **extra_fields):
        if not email:
            raise ValueError("Email address is required.")
        email = self.normalize_email(email)
        extra_fields.setdefault("role", CitySenseUser.Role.CITIZEN)
        user = self.model(email=email, name=name, **extra_fields)
        user.set_password(password)   # hashes password — never stored plaintext
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, password=None, **extra_fields):
        extra_fields.setdefault("role", CitySenseUser.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if not extra_fields.get("is_staff"):
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, name, password, **extra_fields)


class CitySenseUser(AbstractBaseUser, PermissionsMixin):
    """
    CitySense custom user model.

    AUTH_USER_MODEL = 'accounts.CitySenseUser'
    """

    class Role(models.TextChoices):
        CITIZEN = "CITIZEN", "Citizen"
        ADMIN = "ADMIN", "Administrator"

    # Core identity fields
    email = models.EmailField(unique=True, verbose_name="Email address")
    name = models.CharField(max_length=150, verbose_name="Full name")
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.CITIZEN,
        verbose_name="Role",
    )

    # Django internals — required for admin and permission support
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now, verbose_name="Joined")

    objects = CitySenseUserManager()

    # Tell Django to use email as the login field
    USERNAME_FIELD = "email"
    # name is required when creating via createsuperuser
    REQUIRED_FIELDS = ["name"]

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email}> [{self.role}]"

    @property
    def is_citizen(self):
        return self.role == self.Role.CITIZEN

    @property
    def is_admin_user(self):
        return self.role == self.Role.ADMIN
