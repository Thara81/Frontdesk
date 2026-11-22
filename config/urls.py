from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

admin.site.site_header = "Frontdesk"
admin.site.site_title = "Frontdesk"
admin.site.index_title = "Operations"


def healthz(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("api/", include("tickets.api_urls")),
    path("support/", include("customers.urls")),
    path("tickets/", include("tickets.urls")),
    path("activity/", include("audit.urls")),
    path("", include("dashboard.urls")),
]
