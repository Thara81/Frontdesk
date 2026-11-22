from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from tickets.constants import (
    DEFAULT_CATEGORIES,
    TERMINAL_STATUSES,
    CommentVisibility,
    Priority,
    TicketStatus,
)


class CommentQuerySet(models.QuerySet):
    def public(self):
        return self.filter(visibility=CommentVisibility.PUBLIC)

    def internal(self):
        return self.filter(visibility=CommentVisibility.INTERNAL)


class TicketQuerySet(models.QuerySet):
    def visible_to(self, user):
        if user.can_oversee:
            return self
        return self.filter(
            Q(assigned_agent=user) | Q(assigned_agent__isnull=True, status=TicketStatus.OPEN)
        )

    def overdue(self, now=None):
        now = now or timezone.now()
        active = self.exclude(status__in=TERMINAL_STATUSES)
        response_open = Q(first_response_at__isnull=True)
        running = active.filter(waiting_since__isnull=True).filter(
            (response_open & Q(response_deadline__lt=now)) | Q(resolution_deadline__lt=now)
        )
        paused = active.filter(waiting_since__isnull=False).filter(
            (response_open & Q(response_deadline__lt=models.F("waiting_since")))
            | Q(resolution_deadline__lt=models.F("waiting_since"))
        )
        return (running | paused).distinct()


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Ticket(models.Model):
    ticket_number = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="tickets")
    subject = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="tickets")
    priority = models.CharField(max_length=20, choices=Priority.choices)
    status = models.CharField(max_length=32, choices=TicketStatus.choices, default=TicketStatus.OPEN)
    assigned_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assigned_tickets",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_tickets",
    )
    sla_anchor = models.DateTimeField()
    response_deadline = models.DateTimeField()
    resolution_deadline = models.DateTimeField()
    total_paused_business_minutes = models.PositiveIntegerField(default=0)
    waiting_since = models.DateTimeField(null=True, blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    reopened_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TicketQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["assigned_agent", "status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["response_deadline"]),
            models.Index(fields=["resolution_deadline"]),
            models.Index(fields=["ticket_number"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="ticket_priority_valid",
                condition=Q(priority__in=[choice.value for choice in Priority]),
            ),
            models.CheckConstraint(
                name="ticket_status_valid",
                condition=Q(status__in=[choice.value for choice in TicketStatus]),
            ),
            models.CheckConstraint(
                name="active_work_requires_agent",
                condition=(
                    ~Q(status__in=[TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS, TicketStatus.WAITING])
                    | Q(assigned_agent__isnull=False)
                ),
            ),
        ]

    def __str__(self):
        return f"{self.ticket_number} {self.subject}"

    def sla_state(self, now=None):
        from sla.services import snapshot

        return snapshot(self, now or timezone.now())

    @property
    def is_terminal(self):
        return self.status in TERMINAL_STATUSES


class TicketComment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ticket_comments",
    )
    customer_author = models.ForeignKey(
        "customers.Customer",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="comments",
    )
    visibility = models.CharField(max_length=20, choices=CommentVisibility.choices)
    body = models.TextField()
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = CommentQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["ticket", "visibility", "created_at"])]
        constraints = [
            models.CheckConstraint(
                name="comment_visibility_valid",
                condition=Q(visibility__in=[choice.value for choice in CommentVisibility]),
            ),
            models.CheckConstraint(
                name="comment_author_present",
                condition=Q(author__isnull=False) | Q(customer_author__isnull=False),
            ),
            models.CheckConstraint(
                name="internal_notes_require_staff",
                condition=~Q(visibility=CommentVisibility.INTERNAL) | Q(author__isnull=False),
            ),
            models.CheckConstraint(
                name="internal_notes_exclude_customers",
                condition=~Q(visibility=CommentVisibility.INTERNAL, customer_author__isnull=False),
            ),
        ]

    def __str__(self):
        return f"{self.visibility} on {self.ticket_id}"

    @property
    def author_name(self):
        if self.author_id:
            return self.author.display_name
        if self.customer_author_id:
            return self.customer_author.name
        return "System"


class TicketAssignment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT, related_name="assignments")
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assignment_history",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assignments_made",
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-assigned_at", "-id"]
        indexes = [models.Index(fields=["ticket", "assigned_at"])]

    def __str__(self):
        return f"{self.ticket.ticket_number} -> {self.agent}"
