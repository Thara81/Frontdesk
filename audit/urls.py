from django.urls import path

from audit import views

app_name = "audit"

urlpatterns = [path("ticket/<int:ticket_id>/", views.ticket_activity, name="ticket")]
