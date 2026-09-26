from PIL import Image as PillowImage
from django import forms
from django.core.exceptions import ValidationError

from .models import Issue

MAX_IMAGE_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "GIF", "WEBP"}


class IssueCreateForm(forms.ModelForm):
    latitude = forms.DecimalField(
        required=False, max_digits=9, decimal_places=6,
        min_value=-90, max_value=90,
    )
    longitude = forms.DecimalField(
        required=False, max_digits=9, decimal_places=6,
        min_value=-180, max_value=180,
    )

    class Meta:
        model = Issue
        fields = ("title", "description", "image", "latitude", "longitude")
        widgets = {
            "title": forms.TextInput(attrs={"maxlength": 255}),
            "description": forms.Textarea(attrs={"rows": 5}),
        }

    def clean_image(self):
        uploaded = self.cleaned_data.get("image")
        if not uploaded:
            return uploaded
        if uploaded.size > MAX_IMAGE_SIZE:
            raise ValidationError("Image must be 5 MB or smaller.")
        try:
            with PillowImage.open(uploaded) as image:
                if image.format not in ALLOWED_IMAGE_FORMATS:
                    raise ValidationError("Upload a JPEG, PNG, GIF, or WebP image.")
                image.verify()
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError("Upload a valid image file.") from exc
        uploaded.seek(0)
        return uploaded
