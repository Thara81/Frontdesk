from django.contrib import admin

from sla.models import BusinessHoliday, SLAConfiguration


@admin.register(BusinessHoliday)
class BusinessHolidayAdmin(admin.ModelAdmin):
    list_display = ("date", "name")
    ordering = ("date",)


@admin.register(SLAConfiguration)
class SLAConfigurationAdmin(admin.ModelAdmin):
    list_display = ("priority", "response_minutes", "resolution_minutes", "updated_at")
