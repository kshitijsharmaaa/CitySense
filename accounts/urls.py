from django.urls import path

from .views import CitySenseLoginView, logout_view, register

app_name = "accounts"

urlpatterns = [
    path("register/", register, name="register"),
    path("login/", CitySenseLoginView.as_view(), name="login"),
    path("logout/", logout_view, name="logout"),
]
