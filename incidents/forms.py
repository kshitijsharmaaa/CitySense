"""Server-rendered forms for the staff incident workflow."""

from django import forms

from accounts.models import CitySenseUser
from citysense.image_uploads import validate_city_image
from issues.models import Department

from .models import Incident, IncidentStatus


class IncidentFilterForm(forms.Form):
    status = forms.ChoiceField(
        required=False,
        choices=(
            ('', 'All statuses'),
            (IncidentStatus.REPORTED, 'Report received'),
            (IncidentStatus.VERIFIED, 'Verified'),
            (IncidentStatus.ASSIGNED, 'Assigned'),
            (IncidentStatus.IN_PROGRESS, 'Work in progress'),
            (IncidentStatus.RESOLVED, 'Resolved'),
            (IncidentStatus.REJECTED, 'Closed / Not approved'),
        ),
    )
    priority = forms.ChoiceField(
        required=False,
        choices=(('', 'All priorities'), *Incident._meta.get_field('priority').choices),
    )
    category = forms.ChoiceField(
        required=False,
        choices=(('', 'All categories'), *Incident._meta.get_field('category').choices),
    )
    department = forms.ModelChoiceField(
        required=False,
        queryset=Department.objects.all(),
        empty_label='All departments',
    )


class IncidentReviewForm(forms.ModelForm):
    status_comment = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Optional note recorded with a status change.',
    )

    class Meta:
        model = Incident
        fields = ('department', 'assigned_to', 'status', 'resolution_notes', 'resolution_image')
        widgets = {
            'resolution_notes': forms.Textarea(attrs={'rows': 4}),
            'resolution_image': forms.ClearableFileInput(attrs={
                'accept': 'image/jpeg,image/png,image/gif,image/webp',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].required = False
        self.fields['assigned_to'].required = False
        self.fields['status'].choices = (
            (IncidentStatus.REPORTED, 'Report received'),
            (IncidentStatus.VERIFIED, 'Verified'),
            (IncidentStatus.ASSIGNED, 'Assigned'),
            (IncidentStatus.IN_PROGRESS, 'Work in progress'),
            (IncidentStatus.RESOLVED, 'Resolved'),
            (IncidentStatus.REJECTED, 'Closed / Not approved'),
        )
        self.fields['assigned_to'].queryset = CitySenseUser.objects.filter(
            role=CitySenseUser.Role.ADMIN,
            is_active=True,
        ).order_by('name')

    def clean_resolution_image(self):
        uploaded = self.cleaned_data.get('resolution_image')
        if not uploaded or uploaded == self.instance.resolution_image:
            return uploaded
        return validate_city_image(uploaded)
