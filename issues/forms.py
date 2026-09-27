from PIL import Image as PillowImage
from django import forms
from django.core.exceptions import ValidationError

from incidents.models import Incident, IncidentStatus
from .models import Category, Department, Issue, Priority

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



class IssueAdminFilterForm(forms.Form):
    """Validated, human-readable filters for the administrator reports inbox."""

    status = forms.ChoiceField(
        required=False,
        choices=(
            ("", "All statuses"),
            (IncidentStatus.REPORTED, "Report received"),
            (IncidentStatus.VERIFIED, "Verified"),
            (IncidentStatus.ASSIGNED, "Assigned"),
            (IncidentStatus.IN_PROGRESS, "Work in progress"),
            (IncidentStatus.RESOLVED, "Resolved"),
            (IncidentStatus.REJECTED, "Closed / Not approved"),
        ),
    )
    priority = forms.ChoiceField(
        required=False,
        choices=(("", "All priorities"), *Priority.choices),
    )
    category = forms.ChoiceField(
        required=False,
        choices=(("", "All issue types"), *Category.choices),
    )
    department = forms.ModelChoiceField(
        required=False,
        queryset=Department.objects.all(),
        empty_label="All departments",
    )
    assignment = forms.ChoiceField(
        required=False,
        choices=(("", "Any assignment"), ("unassigned", "Unassigned"), ("assigned", "Assigned")),
    )
    search = forms.CharField(required=False, max_length=100, label="Search")
    sort = forms.ChoiceField(
        required=False,
        choices=(("newest", "Newest first"), ("oldest", "Oldest first"), ("priority", "Highest priority")),
        initial="newest",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            css_class = "form-control" if field_name == "search" else "form-select"
            field.widget.attrs["class"] = css_class
        self.fields["search"].widget.attrs["placeholder"] = "Report ID, incident ID, title, or issue type"
