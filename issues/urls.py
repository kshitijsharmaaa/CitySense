from django.urls import path

from . import views

app_name = "issues"

urlpatterns = [
    path("", views.issue_list, name="list"),
    path("new/", views.create, name="create"),
    path("new/analyze-photo/", views.analyze_photo, name="analyze_photo"),
    path("<int:pk>/delete/", views.delete_report, name="delete"),
    path("<int:pk>/", views.detail, name="detail"),
]
