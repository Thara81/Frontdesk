from django.urls import path

from customers import views

app_name = "customers"

urlpatterns = [
    path("submit/", views.submit_ticket, name="submit"),
    path("track/", views.track_ticket, name="track"),
]
