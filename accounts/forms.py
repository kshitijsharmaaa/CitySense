from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import CitySenseUser


class CitizenRegistrationForm(UserCreationForm):
    class Meta:
        model = CitySenseUser
        fields = ("name", "email")
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if CitySenseUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        # Self-registration can only create citizen accounts.
        user.role = CitySenseUser.Role.CITIZEN
        if commit:
            user.save()
            self.save_m2m()
        return user


class CitySenseAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()
