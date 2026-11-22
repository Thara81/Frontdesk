from django.contrib.auth.models import AbstractUser
from django.db import models

from accounts.managers import UserManager


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        MANAGER = "manager", "Manager"
        AGENT = "agent", "Support Agent"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.AGENT)
    phone = models.CharField(max_length=20, blank=True)
    job_title = models.CharField(max_length=80, blank=True)

    objects = UserManager()

    class Meta:
        indexes = [models.Index(fields=["role", "is_active"])]

    def __str__(self):
        return f"{self.display_name} ({self.get_role_display()})"

    @property
    def display_name(self):
        return self.get_full_name().strip() or self.username

    @property
    def is_administrator(self):
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_agent(self):
        return self.role == self.Role.AGENT

    @property
    def can_oversee(self):
        return self.is_administrator or self.is_manager

    @property
    def is_employee(self):
        return self.is_active and (
            self.is_superuser
            or self.role in {self.Role.ADMIN, self.Role.MANAGER, self.Role.AGENT}
        )
