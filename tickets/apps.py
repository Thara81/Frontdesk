from django.apps import AppConfig


class TicketsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tickets"
    verbose_name = "Tickets"

    def ready(self):
        from django.db.models.signals import post_migrate

        post_migrate.connect(_ensure_categories, dispatch_uid="tickets.ensure_categories")


def _ensure_categories(sender, **kwargs):
    if getattr(sender, "name", None) != "tickets":
        return
    from tickets.constants import DEFAULT_CATEGORIES
    from tickets.models import Category

    for name, description in DEFAULT_CATEGORIES:
        Category.objects.get_or_create(name=name, defaults={"description": description})
