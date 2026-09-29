"""Idempotently create or update the Render demo administrator account."""

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email


class Command(BaseCommand):
    help = "Create or update the configured demo administrator account."

    REQUIRED_ENV_VARS = (
        "DEMO_ADMIN_EMAIL",
        "DEMO_ADMIN_NAME",
        "DEMO_ADMIN_PASSWORD",
    )

    def handle(self, *args, **options):
        values = {key: os.environ.get(key, "").strip() for key in self.REQUIRED_ENV_VARS}
        missing = [key for key, value in values.items() if not value]
        if missing:
            raise CommandError(
                "Set the required environment variables: " + ", ".join(missing)
            )

        email = values["DEMO_ADMIN_EMAIL"]
        name = values["DEMO_ADMIN_NAME"]
        password = values["DEMO_ADMIN_PASSWORD"]
        try:
            validate_email(email)
        except ValidationError as exc:
            raise CommandError("DEMO_ADMIN_EMAIL must be a valid email address.") from exc

        user_model = get_user_model()
        matches = user_model.objects.filter(email__iexact=email)
        if matches.count() > 1:
            raise CommandError(
                "Multiple accounts match DEMO_ADMIN_EMAIL; resolve duplicates first."
            )

        user = matches.first()
        if user is None:
            user = user_model(email=user_model.objects.normalize_email(email))

        user.name = name
        user.role = user_model.Role.ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            raise CommandError(
                "DEMO_ADMIN_PASSWORD does not meet the configured password rules."
            ) from exc

        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS("Demo admin account is ready."))
