from django.conf import settings

from sla.business_hours import (
    add_business_minutes,
    elapsed_business_minutes,
    format_minutes,
    minutes_per_business_day,
    signed_business_minutes,
)
from sla.defaults import DEFAULT_SLA
from sla.models import SLAConfiguration


def get_durations(priority):
    response_default, resolution_default = DEFAULT_SLA[priority]
    config, _created = SLAConfiguration.objects.get_or_create(
        priority=priority,
        defaults={
            "response_minutes": response_default,
            "resolution_minutes": resolution_default,
        },
    )
    return config.response_minutes, config.resolution_minutes


def recompute_deadlines(ticket, extra_business_minutes=None):
    """Rebuild deadlines from the SLA anchor plus accumulated paused minutes.

    The open customer-wait is not added here, so a paused clock stays frozen
    until work resumes. Response deadlines are left untouched once a staff
    public reply has been recorded.
    """
    response_minutes, resolution_minutes = get_durations(ticket.priority)
    extra = int(ticket.total_paused_business_minutes or 0) if extra_business_minutes is None else int(extra_business_minutes)
    anchor = ticket.sla_anchor
    if ticket.first_response_at is None:
        ticket.response_deadline = add_business_minutes(anchor, response_minutes + extra)
    ticket.resolution_deadline = add_business_minutes(anchor, resolution_minutes + extra)
    return ticket


def pause_waiting(ticket, now):
    if ticket.waiting_since is None:
        ticket.waiting_since = now
    return ticket


def resume_waiting(ticket, now):
    if ticket.waiting_since is None:
        return ticket
    paused = elapsed_business_minutes(ticket.waiting_since, now)
    ticket.total_paused_business_minutes = int(ticket.total_paused_business_minutes or 0) + paused
    ticket.waiting_since = None
    recompute_deadlines(ticket)
    return ticket


def auto_close_limit():
    return minutes_per_business_day() * int(settings.SLA_AUTO_CLOSE_BUSINESS_DAYS)


def reopen_limit():
    return minutes_per_business_day() * int(settings.SLA_REOPEN_BUSINESS_DAYS)


def snapshot(ticket, now):
    return {
        "response": _leg(ticket, "response", now),
        "resolution": _leg(ticket, "resolution", now),
    }


def _leg(ticket, kind, now):
    if ticket.status == "closed" and ticket.resolved_at is None:
        return {"state": "closed", "label": "Closed"}
    if kind == "response" and ticket.first_response_at:
        met = ticket.first_response_at <= ticket.response_deadline
        return {"state": "met" if met else "missed", "label": "Met" if met else "Missed"}
    if kind == "resolution" and ticket.resolved_at and ticket.status in {"resolved", "closed"}:
        met = ticket.resolved_at <= ticket.resolution_deadline
        return {"state": "met" if met else "missed", "label": "Met" if met else "Missed"}
    if ticket.status == "closed" and ticket.resolved_at is None:
        return {"state": "closed", "label": "Closed"}

    deadline = ticket.response_deadline if kind == "response" else ticket.resolution_deadline
    anchor = ticket.waiting_since or now
    remaining = signed_business_minutes(anchor, deadline)
    paused = ticket.waiting_since is not None
    if remaining < 0:
        label = f"Overdue {format_minutes(remaining)}"
        state = "overdue"
    elif remaining == 0:
        label = "Due now"
        state = "due"
    else:
        label = f"{format_minutes(remaining)} left"
        state = "ok"
    if paused:
        label = f"Paused · {label}"
        if state != "overdue":
            state = "paused"
    return {"state": state, "label": label}
