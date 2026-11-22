from rest_framework.permissions import BasePermission


class IsEmployee(BasePermission):
    message = "Employee authentication is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_employee)


class IsOverseer(BasePermission):
    message = "Manager or administrator access is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.can_oversee)
