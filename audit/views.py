from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render

from tickets.models import Ticket


@login_required
def ticket_activity(request, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    if not request.user.can_oversee and ticket.assigned_agent_id != request.user.id:
        raise PermissionDenied
    activities = ticket.activities.select_related("actor")
    if not request.user.can_oversee:
        from audit.models import TicketActivity
        activities = activities.exclude(action=TicketActivity.Action.INTERNAL_NOTE)
    return render(request, "activity/list.html", {"ticket": ticket, "activities": activities})
