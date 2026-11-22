from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render

from tickets.constants import CommentVisibility, Priority
from tickets.exceptions import TicketError
from tickets.forms import TicketCreateForm
from tickets.models import Category, Ticket
from tickets import services


def submit_ticket(request):
    form = TicketCreateForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            ticket = services.create_ticket(**form.cleaned_data)
            messages.success(request, f"Your ticket {ticket.ticket_number} was submitted.")
            return redirect("customers:track")
        except TicketError as exc:
            messages.error(request, str(exc))
    return render(request, "support/submit.html", {"form": form})


def track_ticket(request):
    ticket = None
    comments = []
    number = (request.POST if request.method == "POST" else request.GET).get("ticket_number", "").strip()
    email = (request.POST if request.method == "POST" else request.GET).get("email", "").strip()
    if number and email:
        ticket = Ticket.objects.filter(ticket_number__iexact=number, customer__email__iexact=email).select_related("customer", "category").first()
        if ticket:
            if request.method == "POST":
                try:
                    # Resolved tickets can be reopened by a matching customer reply.
                    if ticket.status in {"resolved", "closed"}:
                        if ticket.status == "resolved":
                            services.reopen_ticket(ticket.pk, customer_email=email)
                            ticket.refresh_from_db()
                        else:
                            raise TicketError("Closed tickets cannot receive new replies.")
                    services.add_customer_reply(ticket, request.POST.get("body", ""))
                    ticket.refresh_from_db()
                    messages.success(request, "Reply sent.")
                except TicketError as exc:
                    messages.error(request, str(exc))
            comments = ticket.comments.public()
        else:
            messages.error(request, "Ticket not found.")
    return render(request, "support/track.html", {"ticket": ticket, "comments": comments, "number": number, "email": email})
