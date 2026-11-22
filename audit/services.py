from django.utils import timezone

from audit.models import TicketActivity


def log_activity(*, ticket, action, actor=None, previous="", new="", created_at=None):
    if actor is not None and not getattr(actor, "pk", None):
        actor = None
    return TicketActivity.objects.create(
        ticket=ticket,
        actor=actor,
        action=action,
        previous_value=str(previous or "")[:4000],
        new_value=str(new or "")[:4000],
        created_at=created_at or timezone.now(),
    )
