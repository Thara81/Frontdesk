from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render

from tickets.constants import TERMINAL_STATUSES, TicketStatus
from tickets.models import Ticket


@login_required
def home(request):
    tickets = Ticket.objects.visible_to(request.user)
    counts = {row["status"]: row["total"] for row in tickets.values("status").annotate(total=Count("id"))}
    context = {
        "open_count": counts.get(TicketStatus.OPEN, 0),
        "assigned_count": counts.get(TicketStatus.ASSIGNED, 0),
        "waiting_count": counts.get(TicketStatus.WAITING, 0),
        "resolved_count": counts.get(TicketStatus.RESOLVED, 0),
        "active_count": tickets.exclude(status__in=TERMINAL_STATUSES).count(),
        "recent_tickets": tickets.select_related("customer", "category", "assigned_agent")[:10],
        "assigned_tickets": tickets.filter(status__in=[TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS]).select_related("customer", "category", "assigned_agent")[:10],
        "waiting_tickets": tickets.filter(status=TicketStatus.WAITING).select_related("customer", "category", "assigned_agent")[:10],
        "overdue_tickets": tickets.overdue()[:10],
    }
    return render(request, "dashboard/home.html", context)
