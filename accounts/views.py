from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.decorators import admin_required, employee_required
from accounts.forms import (
    EmployeeAuthenticationForm,
    EmployeeCreateForm,
    EmployeeUpdateForm,
    ProfileForm,
    StyledPasswordChangeForm,
)
from accounts.models import User


class StaffLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmployeeAuthenticationForm
    redirect_authenticated_user = True


class StaffLogoutView(LogoutView):
    http_method_names = ["post"]


@employee_required
@require_http_methods(["GET", "POST"])
def profile(request):
    post_data = request.POST if request.method == "POST" else None
    profile_form = ProfileForm(post_data, instance=request.user, prefix="profile")
    password_form = StyledPasswordChangeForm(request.user, post_data, prefix="password")
    if request.method == "POST" and "save_profile" in request.POST and profile_form.is_valid():
        profile_form.save()
        messages.success(request, "Profile updated.")
        return redirect("accounts:profile")
    if request.method == "POST" and "change_password" in request.POST and password_form.is_valid():
        user = password_form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Password changed.")
        return redirect("accounts:profile")
    return render(
        request,
        "accounts/profile.html",
        {"profile_form": profile_form, "password_form": password_form},
    )


@admin_required
def user_list(request):
    users = User.objects.order_by("role", "first_name", "username")
    return render(request, "accounts/user_list.html", {"users": users})


@admin_required
@require_http_methods(["GET", "POST"])
def user_create(request):
    form = EmployeeCreateForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Employee account created.")
        return redirect("accounts:users")
    return render(request, "accounts/user_form.html", {"form": form, "title": "New employee"})


@admin_required
@require_http_methods(["GET", "POST"])
def user_edit(request, pk):
    employee = get_object_or_404(User, pk=pk)
    form = EmployeeUpdateForm(request.POST if request.method == "POST" else None, instance=employee)
    if request.method == "POST" and form.is_valid():
        if employee.pk == request.user.pk and not form.cleaned_data["is_active"]:
            messages.error(request, "You cannot deactivate your own account.")
        else:
            form.save()
            messages.success(request, "Employee updated.")
            return redirect("accounts:users")
    return render(
        request,
        "accounts/user_form.html",
        {"form": form, "title": f"Edit {employee.display_name}"},
    )
