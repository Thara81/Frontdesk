from django.core.management.base import BaseCommand

from tickets.services import close_expired_waiting_tickets


class Command(BaseCommand):
    help = "Close waiting tickets after the configured silence period"

    def handle(self, *args, **options):
        closed = close_expired_waiting_tickets()
        self.stdout.write(self.style.SUCCESS(f"Closed {len(closed)} ticket(s)."))
