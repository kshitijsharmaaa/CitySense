from django import forms

from ai_engine.prompts import ALLOWED_DEPARTMENTS
from citysense.image_uploads import MAX_IMAGE_SIZE, validate_city_image
from incidents.models import Incident, IncidentStatus
from .models import Category, Department, Issue, Priority


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ai_category"] = forms.ChoiceField(
            required=False,
            choices=(("", "Use AI recommendation"), *Category.choices),
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.fields["ai_priority"] = forms.ChoiceField(
            required=False,
            choices=(("", "Use AI recommendation"), *Priority.choices),
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.fields["ai_department"] = forms.ChoiceField(
            required=False,
            choices=(("", "Use AI recommendation"), *((name, name) for name in ALLOWED_DEPARTMENTS)),
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        # An image can supply the missing report text after validated AI analysis.
        self.fields["title"].required = False
        self.fields["description"].required = False

    def clean_image(self):
        return validate_city_image(self.cleaned_data.get("image"))

    def clean(self):
        cleaned_data = super().clean()
        title = cleaned_data.get("title", "").strip()
        description = cleaned_data.get("description", "").strip()
        image = cleaned_data.get("image")

        if not image:
            if not title:
                self.add_error("title", "Add a title, or attach a photo for AI-assisted drafting.")
            if not description:
                self.add_error("description", "Add a description, or attach a photo for AI-assisted drafting.")
        return cleaned_data



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
