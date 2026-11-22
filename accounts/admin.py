from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "role", "is_active")
    list_filter = ("role", "is_active")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Frontdesk", {"fields": ("role", "phone", "job_title")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Frontdesk", {"fields": ("role", "phone", "job_title")}),
    )

    def has_delete_permission(self, request, obj=None):
        return False
