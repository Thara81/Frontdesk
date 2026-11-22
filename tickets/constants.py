from django.db import models


class TicketStatus(models.TextChoices):
    OPEN = "open", "Open"
    ASSIGNED = "assigned", "Assigned"
    IN_PROGRESS = "in_progress", "In Progress"
    WAITING = "waiting_for_customer", "Waiting for Customer"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"


class Priority(models.TextChoices):
    URGENT = "urgent", "Urgent"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"


class CommentVisibility(models.TextChoices):
    PUBLIC = "public", "Public reply"
    INTERNAL = "internal", "Internal note"


TERMINAL_STATUSES = {TicketStatus.RESOLVED, TicketStatus.CLOSED}

DEFAULT_CATEGORIES = [
    ("Billing", "Invoices, refunds, and payment disputes"),
    ("Technical Support", "Product defects and access failures"),
    ("Account Access", "Login, permissions, and profile issues"),
    ("Service Delivery", "Onboarding, fulfilment, and delays"),
    ("General Inquiry", "Questions that do not fit another category"),
]
