"""Default SLA durations in business minutes.

Assumptions, used when the assignment does not specify exact durations:

- Urgent: respond within 1 business hour, resolve within 4 business hours.
- Medium: respond within 4 business hours, resolve within 1 business day.
- Low: respond within 1 business day, resolve within 3 business days.

A business day is the configured working window (default 09:30–18:30, 9 hours).
Administrators can change these values in SLA settings. Existing tickets keep
their stored deadlines until priority is changed, the SLA resumes, or the
ticket is reopened.
"""

DEFAULT_SLA = {
    "urgent": (60, 240),
    "medium": (240, 540),
    "low": (540, 1620),
}


def ensure_sla_defaults(sender, **kwargs):
    if getattr(sender, "name", None) != "sla":
        return
    from sla.models import SLAConfiguration

    for priority, (response_minutes, resolution_minutes) in DEFAULT_SLA.items():
        SLAConfiguration.objects.get_or_create(
            priority=priority,
            defaults={
                "response_minutes": response_minutes,
                "resolution_minutes": resolution_minutes,
            },
        )
