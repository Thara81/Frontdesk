from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditImmutabilityError(Exception):
    """Raised when application code tries to change historical activity."""


class ImmutableQuerySet(models.QuerySet):
    def delete(self):
        raise AuditImmutabilityError("Activity records cannot be deleted.")

    def update(self, **kwargs):
        raise AuditImmutabilityError("Activity records cannot be modified.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise AuditImmutabilityError("Activity records cannot be modified.")


class ImmutableManager(models.Manager):
    def get_queryset(self):
        return ImmutableQuerySet(self.model, using=self._db)


class TicketActivity(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", "Ticket created"
        ASSIGNED = "assigned", "Ticket assigned"
        STATUS_CHANGED = "status_changed", "Status changed"
        PRIORITY_CHANGED = "priority_changed", "Priority changed"
        PUBLIC_REPLY = "public_reply", "Agent response"
        INTERNAL_NOTE = "internal_note", "Internal note"
        CUSTOMER_REPLY = "customer_reply", "Customer response"
        RESOLVED = "resolved", "Ticket resolved"
        REOPENED = "reopened", "Ticket reopened"
        CLOSED = "closed", "Ticket closed"

    ticket = models.ForeignKey("tickets.Ticket", on_delete=models.PROTECT, related_name="activities")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ticket_activities",
    )
    action = models.CharField(max_length=40, choices=Action.choices)
    previous_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = ImmutableManager()

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name_plural = "Ticket activities"
        indexes = [
            models.Index(fields=["ticket", "created_at"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self):
        return f"{self.ticket_id} {self.action}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise AuditImmutabilityError("Activity records cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditImmutabilityError("Activity records cannot be deleted.")
