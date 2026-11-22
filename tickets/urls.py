from django.urls import path

from tickets import views

app_name = "tickets"

urlpatterns = [
    path("", views.ticket_list, name="list"),
    path("queue/", views.ticket_queue, name="queue"),
    path("new/", views.ticket_create, name="create"),
    path("<int:pk>/", views.ticket_detail, name="detail"),
    path("<int:pk>/accept/", views.accept, name="accept"),
    path("<int:pk>/assign/", views.assign, name="assign"),
    path("<int:pk>/status/", views.change_status, name="status"),
    path("<int:pk>/priority/", views.change_priority, name="priority"),
    path("<int:pk>/reopen/", views.reopen, name="reopen"),
]
