from django.urls import path

from .views import admin_dashboard, admin_detail, detail

app_name = "incidents"

urlpatterns = [
    path("manage/", admin_dashboard, name="admin_dashboard"),
    path("manage/<int:pk>/", admin_detail, name="admin_detail"),
    path("<int:pk>/", detail, name="detail"),
]
