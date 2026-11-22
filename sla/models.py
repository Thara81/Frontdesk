from django.core.exceptions import ValidationError
from django.db import models


class BusinessHoliday(models.Model):
    date = models.DateField(unique=True)
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.name} ({self.date})"


class SLAConfiguration(models.Model):
    priority = models.CharField(max_length=20, unique=True)
    response_minutes = models.PositiveIntegerField()
    resolution_minutes = models.PositiveIntegerField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority"]
        verbose_name = "SLA configuration"
        verbose_name_plural = "SLA configurations"

    def __str__(self):
        return f"{self.priority}: response {self.response_minutes}m / resolution {self.resolution_minutes}m"

    def clean(self):
        if (
            self.response_minutes
            and self.resolution_minutes
            and self.response_minutes > self.resolution_minutes
        ):
            raise ValidationError("Response time cannot be longer than resolution time.")
