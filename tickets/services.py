import json
import uuid

from django.conf import settings
from django.core.mail import send_mail
from django.db import connection, transaction
from django.utils import timezone

from audit.models import TicketActivity
from audit.services import log_activity
from customers.models import Customer
from sla.business_hours import elapsed_business_minutes
from sla.services import auto_close_limit, pause_waiting, recompute_deadlines, reopen_limit, resume_waiting
from tickets.constants import CommentVisibility, Priority, TicketStatus
from tickets.exceptions import TicketError, TicketUnavailable
from tickets.models import Category, Ticket, TicketAssignment, TicketComment

TRANSITIONS = {
    TicketStatus.OPEN: set(),
    TicketStatus.ASSIGNED: {TicketStatus.IN_PROGRESS, TicketStatus.WAITING, TicketStatus.RESOLVED},
    TicketStatus.IN_PROGRESS: {TicketStatus.WAITING, TicketStatus.RESOLVED},
    TicketStatus.WAITING: {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED},
    TicketStatus.RESOLVED: {TicketStatus.CLOSED},
    TicketStatus.CLOSED: set(),
}


def _lock(ticket_id):
    if connection.features.has_select_for_update:
        list(Ticket.objects.select_for_update().filter(pk=ticket_id).values_list("pk", flat=True))


def _locked_ticket(ticket_id):
    queryset = Ticket.objects.select_related("customer", "assigned_agent", "category")
    if connection.features.has_select_for_update:
        return queryset.select_for_update().get(pk=ticket_id)
    return queryset.get(pk=ticket_id)


def _actor_name(user):
    if user is None:
        return "System"
    return user.display_name


def assert_can_access(user, ticket):
    if not user.is_employee:
        raise TicketError("Only employees can access this ticket.")
    if user.can_oversee:
        return
    if ticket.assigned_agent_id == user.id:
        return
    if ticket.assigned_agent_id is None and ticket.status == TicketStatus.OPEN:
        return
    raise TicketError("You do not have access to this ticket.")


def allowed_next_statuses(user, ticket):
    if not user.can_oversee and ticket.assigned_agent_id != user.id:
        return []
    options = set(TRANSITIONS.get(ticket.status, set()))
    if not user.can_oversee:
        options.discard(TicketStatus.CLOSED)
    return sorted(options, key=lambda value: TicketStatus(value).label)


def can_reopen(ticket, *, now=None, user=None, customer_email=None):
    if ticket.status != TicketStatus.RESOLVED or not ticket.resolved_at:
        return False
    now = now or timezone.now()
    if elapsed_business_minutes(ticket.resolved_at, now) > reopen_limit():
        return False
    if customer_email and ticket.customer.email.lower() == customer_email.strip().lower():
        return True
    if user is not None and getattr(user, "is_authenticated", False):
        if user.can_oversee or user.id == ticket.assigned_agent_id:
            return True
    return False


def _get_or_create_customer(*, name, email, phone="", company=""):
    email = email.strip().lower()
    customer, created = Customer.objects.get_or_create(
        email=email,
        defaults={"name": name.strip(), "phone": phone.strip(), "company": company.strip()},
    )
    if not created:
        dirty = []
        if name.strip() and customer.name != name.strip():
            customer.name = name.strip()
            dirty.append("name")
        if phone.strip() and customer.phone != phone.strip():
            customer.phone = phone.strip()
            dirty.append("phone")
        if company.strip() and customer.company != company.strip():
            customer.company = company.strip()
            dirty.append("company")
        if dirty:
            customer.save(update_fields=dirty)
    return customer


@transaction.atomic
def create_ticket(
    *,
    customer_name,
    customer_email,
    subject,
    description,
    category,
    priority,
    phone="",
    company="",
    created_by=None,
    now=None,
):
    if priority not in Priority.values:
        raise TicketError("Choose a valid priority.")
    if isinstance(category, int):
        category = Category.objects.get(pk=category)
    if not category.is_active:
        raise TicketError("Choose an active category.")
    subject = subject.strip()
    description = description.strip()
    if len(subject) < 3 or len(description) < 10:
        raise TicketError("Subject and description are too short.")
    now = now or timezone.now()
    customer = _get_or_create_customer(
        name=customer_name,
        email=customer_email,
        phone=phone,
        company=company,
    )
    ticket = Ticket(
        ticket_number=f"TMP-{uuid.uuid4().hex[:16]}",
        customer=customer,
        subject=subject,
        description=description,
        category=category,
        priority=priority,
        status=TicketStatus.OPEN,
        created_by=created_by if getattr(created_by, "pk", None) else None,
        sla_anchor=now,
        response_deadline=now,
        resolution_deadline=now,
        created_at=now,
    )
    recompute_deadlines(ticket)
    ticket.save()
    ticket.ticket_number = f"FD-{ticket.pk:05d}"
    ticket.save(update_fields=["ticket_number"])
    log_activity(
        ticket=ticket,
        actor=created_by if getattr(created_by, "pk", None) else None,
        action=TicketActivity.Action.CREATED,
        previous="",
        new=ticket.ticket_number,
        created_at=now,
    )
    return ticket


@transaction.atomic
def accept_ticket(ticket_id, agent, now=None):
    if not agent.is_agent:
        raise TicketError("Only support agents can accept a ticket from the queue.")
    now = now or timezone.now()
    _lock(ticket_id)
    updated = Ticket.objects.filter(
        pk=ticket_id,
        assigned_agent__isnull=True,
        status=TicketStatus.OPEN,
    ).update(
        assigned_agent=agent,
        status=TicketStatus.ASSIGNED,
        updated_at=now,
    )
    if updated != 1:
        raise TicketUnavailable(
            "This ticket is no longer available. Another agent has already accepted it."
        )
    ticket = Ticket.objects.select_related("assigned_agent", "customer", "category").get(pk=ticket_id)
    TicketAssignment.objects.create(ticket=ticket, agent=agent, assigned_by=agent, assigned_at=now, note="Accepted from queue")
    log_activity(
        ticket=ticket,
        actor=agent,
        action=TicketActivity.Action.ASSIGNED,
        previous="",
        new=_actor_name(agent),
        created_at=now,
    )
    log_activity(
        ticket=ticket,
        actor=agent,
        action=TicketActivity.Action.STATUS_CHANGED,
        previous=TicketStatus.OPEN,
        new=TicketStatus.ASSIGNED,
        created_at=now,
    )
    return ticket


@transaction.atomic
def assign_ticket(ticket_id, agent, assigned_by, now=None):
    if not assigned_by.can_oversee:
        raise TicketError("Only managers and administrators can assign tickets.")
    if not agent.is_active or not agent.is_agent:
        raise TicketError("Choose an active support agent.")
    now = now or timezone.now()
    _lock(ticket_id)
    ticket = _locked_ticket(ticket_id)
    if ticket.status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
        raise TicketError("Resolved or closed tickets cannot be assigned.")
    if ticket.assigned_agent_id == agent.id:
        raise TicketError("This ticket is already assigned to that agent.")
    previous_agent = _actor_name(ticket.assigned_agent) if ticket.assigned_agent_id else ""
    previous_status = ticket.status
    previous_assigned_agent_id = ticket.assigned_agent_id
    new_status = TicketStatus.ASSIGNED if ticket.status == TicketStatus.OPEN else ticket.status
    updated = Ticket.objects.filter(
        pk=ticket_id,
        assigned_agent_id=previous_assigned_agent_id,
        status=previous_status,
    ).update(assigned_agent=agent, status=new_status)
    if updated != 1:
        raise TicketUnavailable("This ticket changed while it was being assigned.")
    ticket.assigned_agent = agent
    ticket.status = new_status
    TicketAssignment.objects.create(
        ticket=ticket,
        agent=agent,
        assigned_by=assigned_by,
        assigned_at=now,
        note="Assigned by manager",
    )
    log_activity(
        ticket=ticket,
        actor=assigned_by,
        action=TicketActivity.Action.ASSIGNED,
        previous=previous_agent,
        new=_actor_name(agent),
        created_at=now,
    )
    if previous_status != ticket.status:
        log_activity(
            ticket=ticket,
            actor=assigned_by,
            action=TicketActivity.Action.STATUS_CHANGED,
            previous=previous_status,
            new=ticket.status,
            created_at=now,
        )
    return ticket


@transaction.atomic
def change_status(ticket_id, new_status, actor, now=None):
    now = now or timezone.now()
    _lock(ticket_id)
    ticket = _locked_ticket(ticket_id)
    if actor is not None:
        assert_can_access(actor, ticket)
        if new_status not in allowed_next_statuses(actor, ticket):
            raise TicketError("That status change is not allowed.")
    elif new_status not in TRANSITIONS.get(ticket.status, set()) and not (
        ticket.status == TicketStatus.WAITING and new_status in {TicketStatus.IN_PROGRESS, TicketStatus.OPEN}
    ):
        raise TicketError("That status change is not allowed.")
    if new_status == ticket.status:
        raise TicketError("The ticket is already in that status.")
    previous = ticket.status
    if previous == TicketStatus.WAITING and new_status != TicketStatus.WAITING:
        resume_waiting(ticket, now)
    if new_status == TicketStatus.WAITING:
        if ticket.assigned_agent_id is None:
            raise TicketError("Assign the ticket before waiting on the customer.")
        pause_waiting(ticket, now)
    if new_status == TicketStatus.RESOLVED:
        ticket.resolved_at = now
    if new_status == TicketStatus.CLOSED:
        ticket.closed_at = now
    if new_status == TicketStatus.IN_PROGRESS and ticket.assigned_agent_id is None:
        raise TicketError("An agent must own the ticket before it can be in progress.")
    ticket.status = new_status
    ticket.save()
    if new_status == TicketStatus.RESOLVED:
        action = TicketActivity.Action.RESOLVED
    elif new_status == TicketStatus.CLOSED:
        action = TicketActivity.Action.CLOSED
    else:
        action = TicketActivity.Action.STATUS_CHANGED
    log_activity(
        ticket=ticket,
        actor=actor if getattr(actor, "pk", None) else None,
        action=action,
        previous=previous,
        new=new_status,
        created_at=now,
    )
    if new_status in {TicketStatus.RESOLVED, TicketStatus.WAITING} and actor is not None:
        notify_customer_public_update(ticket, _status_intro(ticket, new_status))
    return ticket


@transaction.atomic
def change_priority(ticket_id, new_priority, actor, now=None):
    if actor is None or not actor.can_oversee:
        raise TicketError("Only managers and administrators can change priority.")
    if new_priority not in Priority.values:
        raise TicketError("Choose a valid priority.")
    now = now or timezone.now()
    _lock(ticket_id)
    ticket = _locked_ticket(ticket_id)
    if ticket.status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
        raise TicketError("Priority cannot change after the ticket is resolved or closed.")
    if ticket.priority == new_priority:
        raise TicketError("The ticket already has that priority.")
    previous = ticket.priority
    previous_deadlines = json.dumps(
        {
            "response_deadline": ticket.response_deadline.isoformat(),
            "resolution_deadline": ticket.resolution_deadline.isoformat(),
        }
    )
    ticket.priority = new_priority
    extra = int(ticket.total_paused_business_minutes or 0)
    if ticket.waiting_since is not None:
        extra += elapsed_business_minutes(ticket.waiting_since, now)
    recompute_deadlines(ticket, extra_business_minutes=extra)
    ticket.save()
    log_activity(
        ticket=ticket,
        actor=actor,
        action=TicketActivity.Action.PRIORITY_CHANGED,
        previous=previous,
        new=json.dumps(
            {
                "priority": new_priority,
                "response_deadline": ticket.response_deadline.isoformat(),
                "resolution_deadline": ticket.resolution_deadline.isoformat(),
                "previous_deadlines": previous_deadlines,
            }
        ),
        created_at=now,
    )
    return ticket


@transaction.atomic
def add_staff_comment(ticket_id, author, body, visibility, now=None):
    if not author.is_employee:
        raise TicketError("Only employees can add notes or replies.")
    if visibility not in CommentVisibility.values:
        raise TicketError("Choose a valid visibility.")
    body = body.strip()
    if len(body) < 2:
        raise TicketError("Write a longer note.")
    now = now or timezone.now()
    _lock(ticket_id)
    ticket = _locked_ticket(ticket_id)
    assert_can_access(author, ticket)
    if ticket.status in {TicketStatus.CLOSED}:
        raise TicketError("Closed tickets cannot receive new notes.")
    comment = TicketComment.objects.create(
        ticket=ticket,
        author=author,
        visibility=visibility,
        body=body,
        created_at=now,
    )
    if visibility == CommentVisibility.INTERNAL:
        log_activity(
            ticket=ticket,
            actor=author,
            action=TicketActivity.Action.INTERNAL_NOTE,
            previous="",
            new="Internal note added",
            created_at=now,
        )
        return comment
    previous_status = ticket.status
    if ticket.first_response_at is None:
        ticket.first_response_at = now
    if ticket.status == TicketStatus.WAITING:
        resume_waiting(ticket, now)
        ticket.status = TicketStatus.IN_PROGRESS
    elif ticket.status == TicketStatus.ASSIGNED:
        ticket.status = TicketStatus.IN_PROGRESS
    ticket.save()
    log_activity(
        ticket=ticket,
        actor=author,
        action=TicketActivity.Action.PUBLIC_REPLY,
        previous="",
        new=body[:500],
        created_at=now,
    )
    if previous_status != ticket.status:
        log_activity(
            ticket=ticket,
            actor=author,
            action=TicketActivity.Action.STATUS_CHANGED,
            previous=previous_status,
            new=ticket.status,
            created_at=now,
        )
    notify_customer_public_update(ticket, f"{author.display_name} replied on {ticket.ticket_number}.")
    return comment


@transaction.atomic
def add_customer_reply(ticket, body, now=None):
    body = body.strip()
    if len(body) < 2:
        raise TicketError("Write a longer reply.")
    if ticket.status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
        raise TicketError("This ticket is not accepting replies. Reopen it if that option is still available.")
    now = now or timezone.now()
    comment = TicketComment.objects.create(
        ticket=ticket,
        customer_author=ticket.customer,
        visibility=CommentVisibility.PUBLIC,
        body=body,
        created_at=now,
    )
    log_activity(
        ticket=ticket,
        actor=None,
        action=TicketActivity.Action.CUSTOMER_REPLY,
        previous="",
        new=body[:500],
        created_at=now,
    )
    if ticket.status == TicketStatus.WAITING:
        next_status = TicketStatus.IN_PROGRESS if ticket.assigned_agent_id else TicketStatus.OPEN
        change_status(ticket.pk, next_status, actor=None, now=now)
    return comment


@transaction.atomic
def reopen_ticket(ticket_id, *, actor=None, customer_email=None, now=None):
    now = now or timezone.now()
    _lock(ticket_id)
    ticket = _locked_ticket(ticket_id)
    if not can_reopen(ticket, now=now, user=actor, customer_email=customer_email):
        raise TicketError("This ticket can no longer be reopened.")
    previous_status = ticket.status
    previous_deadlines = f"{ticket.response_deadline.isoformat()} | {ticket.resolution_deadline.isoformat()}"
    ticket.status = TicketStatus.OPEN
    ticket.resolved_at = None
    ticket.closed_at = None
    ticket.reopened_at = now
    ticket.first_response_at = None
    ticket.waiting_since = None
    ticket.total_paused_business_minutes = 0
    ticket.sla_anchor = now
    recompute_deadlines(ticket)
    ticket.save()
    who = _actor_name(actor) if getattr(actor, "pk", None) else ticket.customer.email
    log_activity(
        ticket=ticket,
        actor=actor if getattr(actor, "pk", None) else None,
        action=TicketActivity.Action.REOPENED,
        previous=json.dumps({"status": previous_status, "deadlines": previous_deadlines}),
        new=json.dumps(
            {
                "status": ticket.status,
                "by": who,
                "response_deadline": ticket.response_deadline.isoformat(),
                "resolution_deadline": ticket.resolution_deadline.isoformat(),
            }
        ),
        created_at=now,
    )
    return ticket


def close_expired_waiting_tickets(now=None, dry_run=False):
    now = now or timezone.now()
    limit = auto_close_limit()
    candidates = list(
        Ticket.objects.filter(status=TicketStatus.WAITING, waiting_since__isnull=False).select_related("customer")
    )
    due = [ticket for ticket in candidates if elapsed_business_minutes(ticket.waiting_since, now) >= limit]
    if dry_run:
        return due
    closed = []
    for ticket in due:
        closed.append(_close_for_customer_silence(ticket.pk, now))
    return closed


@transaction.atomic
def _close_for_customer_silence(ticket_id, now):
    _lock(ticket_id)
    ticket = _locked_ticket(ticket_id)
    if ticket.status != TicketStatus.WAITING or ticket.waiting_since is None:
        return ticket
    if elapsed_business_minutes(ticket.waiting_since, now) < auto_close_limit():
        return ticket
    previous = ticket.status
    ticket.status = TicketStatus.CLOSED
    ticket.closed_at = now
    ticket.save()
    log_activity(
        ticket=ticket,
        actor=None,
        action=TicketActivity.Action.CLOSED,
        previous=previous,
        new="Closed automatically after five business days with no customer response.",
        created_at=now,
    )
    return ticket


def customer_export_payload(ticket):
    """Customer-safe representation. Internal notes are excluded by query."""
    comments = ticket.comments.public().order_by("created_at", "id")
    return {
        "ticket_number": ticket.ticket_number,
        "subject": ticket.subject,
        "description": ticket.description,
        "status": ticket.status,
        "priority": ticket.priority,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
        "comments": [
            {"author": comment.author_name, "body": comment.body, "created_at": comment.created_at.isoformat()}
            for comment in comments
        ],
    }


def build_customer_message(ticket, intro):
    public_comments = ticket.comments.public().order_by("created_at", "id")
    lines = [intro, "", f"Ticket: {ticket.ticket_number}", f"Subject: {ticket.subject}", "", "Public conversation:"]
    for comment in public_comments:
        lines.append(f"- {comment.author_name}: {comment.body}")
    return "\n".join(lines)


def notify_customer_public_update(ticket, intro):
    message = build_customer_message(ticket, intro)
    send_mail(
        subject=f"[{ticket.ticket_number}] {ticket.subject}",
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[ticket.customer.email],
        fail_silently=True,
    )
    return message


def _status_intro(ticket, new_status):
    label = TicketStatus(new_status).label
    return f"The status of {ticket.ticket_number} is now {label}."
