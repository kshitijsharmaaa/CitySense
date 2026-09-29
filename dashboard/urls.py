from django.urls import path

from .views import index, profile

app_name = "dashboard"

urlpatterns = [
    path("", index, name="index"),
    path("profile/", profile, name="profile"),
]
