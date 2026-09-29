"""Shared validation for user-submitted civic photos."""

from django.core.exceptions import ValidationError
from PIL import Image


MAX_IMAGE_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "GIF", "WEBP"}


def validate_city_image(uploaded):
    """Validate the real image format and size, then rewind for later storage."""
    if not uploaded:
        return uploaded
    if uploaded.size > MAX_IMAGE_SIZE:
        raise ValidationError("Image must be 5 MB or smaller.")

    try:
        uploaded.seek(0)
        with Image.open(uploaded) as image:
            image_format = image.format
            image.verify()
        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise ValidationError("Upload a JPEG, PNG, GIF, or WebP image.")
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("Upload a valid image file.") from exc
    finally:
        uploaded.seek(0)
    return uploaded
