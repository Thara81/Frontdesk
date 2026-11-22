from django.apps import AppConfig


class SlaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sla"
    verbose_name = "SLA"

    def ready(self):
        from django.db.models.signals import post_migrate

        from sla.defaults import ensure_sla_defaults

        post_migrate.connect(ensure_sla_defaults, dispatch_uid="sla.ensure_defaults")
