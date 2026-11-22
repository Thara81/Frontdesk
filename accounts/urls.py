from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.StaffLoginView.as_view(), name="login"),
    path("logout/", views.StaffLogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    path("users/", views.user_list, name="users"),
    path("users/new/", views.user_create, name="create"),
    path("users/<int:pk>/", views.user_edit, name="edit"),
]
