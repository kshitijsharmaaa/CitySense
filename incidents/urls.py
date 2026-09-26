from django.urls import path

from .views import detail

app_name = "incidents"

urlpatterns = [
    path("<int:pk>/", detail, name="detail"),
]
