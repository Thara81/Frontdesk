from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from accounts.models import User
from audit.models import TicketActivity
from sla.business_hours import elapsed_business_minutes
from sla.defaults import DEFAULT_SLA
from tickets.constants import Priority, TicketStatus
from tickets.models import Category, Ticket
from tickets.services import (
    accept_ticket,
    add_staff_comment,
    assign_ticket,
    change_status,
    create_ticket,
    reopen_ticket,
    customer_export_payload,
    build_customer_message,
)


class FrontdeskCoreTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Test")
        self.agent = User.objects.create_user("agent", password="password123", role=User.Role.AGENT)
        self.manager = User.objects.create_user("manager", password="password123", role=User.Role.MANAGER)

    def create_ticket(self):
        return create_ticket(customer_name="Alice", customer_email="alice@example.com", subject="Cannot login", description="My account access is blocked.", category=self.category, priority=Priority.MEDIUM, created_by=self.manager)

    def test_create_accept_and_comment(self):
        ticket = self.create_ticket()
        accepted = accept_ticket(ticket.pk, self.agent)
        self.assertEqual(accepted.status, TicketStatus.ASSIGNED)
        add_staff_comment(ticket.pk, self.agent, "We are investigating", "public")
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.IN_PROGRESS)
        self.assertIsNotNone(ticket.first_response_at)

    def test_accept_is_concurrent_safe(self):
        ticket = self.create_ticket()
        accept_ticket(ticket.pk, self.agent)
        other = User.objects.create_user("agent2", password="password123", role=User.Role.AGENT)
        with self.assertRaises(Exception):
            accept_ticket(ticket.pk, other)

    def test_waiting_auto_close_limit_and_reopen(self):
        ticket = self.create_ticket()
        assign_ticket(ticket.pk, self.agent, self.manager)
        change_status(ticket.pk, TicketStatus.WAITING, self.manager)
        ticket.refresh_from_db()
        ticket.waiting_since = timezone.now() - timedelta(days=14)
        ticket.save(update_fields=["waiting_since"])
        from tickets.services import close_expired_waiting_tickets
        closed = close_expired_waiting_tickets()
        self.assertEqual(len(closed), 1)

    def test_activity_is_immutable(self):
        ticket = self.create_ticket()
        activity = ticket.activities.get()
        with self.assertRaises(Exception):
            activity.save()
        with self.assertRaises(Exception):
            TicketActivity.objects.filter(pk=activity.pk).update(new_value="changed")

    def test_resolved_ticket_reopens(self):
        ticket = self.create_ticket()
        assign_ticket(ticket.pk, self.agent, self.manager)
        change_status(ticket.pk, TicketStatus.RESOLVED, self.manager)
        reopened = reopen_ticket(ticket.pk, customer_email="alice@example.com")
        self.assertEqual(reopened.status, TicketStatus.OPEN)

    def test_business_hours(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        local = timezone.now().astimezone(ZoneInfo("Asia/Kolkata"))
        while local.weekday() != 0:
            local += timedelta(days=1)
        start = local.replace(hour=9, minute=30, second=0, microsecond=0)
        end = start.replace(hour=18, minute=30)
        self.assertGreaterEqual(elapsed_business_minutes(start, end), 540)


class ConcurrentAcceptanceTests(TransactionTestCase):
    reset_sequences = True

    def test_simultaneous_accept_only_one_succeeds(self):
        category = Category.objects.create(name="Concurrent")
        agent1 = User.objects.create_user("concurrent1", password="password123", role=User.Role.AGENT)
        agent2 = User.objects.create_user("concurrent2", password="password123", role=User.Role.AGENT)
        ticket = create_ticket(customer_name="Concurrent", customer_email="concurrent@example.com", subject="Concurrent ticket", description="Concurrent acceptance test.", category=category, priority=Priority.MEDIUM)

        def accept(agent):
            try:
                accept_ticket(ticket.pk, agent)
                return True
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(accept, [agent1, agent2]))

        ticket.refresh_from_db()
        self.assertEqual(sum(results), 1)
        self.assertIsNotNone(ticket.assigned_agent_id)


class FrontdeskAuditTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Audit Category")
        self.admin = User.objects.create_user("admin2", password="password123", role=User.Role.ADMIN)
        self.manager = User.objects.create_user("manager2", password="password123", role=User.Role.MANAGER)
        self.agent = User.objects.create_user("agent2", password="password123", role=User.Role.AGENT)
        self.other_agent = User.objects.create_user("agent3", password="password123", role=User.Role.AGENT)

    def make_ticket(self, email="owner@example.com"):
        return create_ticket(
            customer_name="Customer",
            customer_email=email,
            subject="Audit subject",
            description="Audit ticket description.",
            category=self.category,
            priority=Priority.MEDIUM,
            created_by=self.admin,
        )

    def test_second_accept_is_rejected(self):
        ticket = self.make_ticket()
        accept_ticket(ticket.pk, self.agent)
        with self.assertRaises(Exception):
            accept_ticket(ticket.pk, self.other_agent)

    def test_internal_note_hidden_everywhere_customer_can_see(self):
        from django.core import mail
        ticket = self.make_ticket()
        accept_ticket(ticket.pk, self.agent)
        add_staff_comment(ticket.pk, self.agent, "SECRET INTERNAL TEXT", "internal")

        customer_payload = customer_export_payload(ticket)
        notification = build_customer_message(ticket, "Status update")
        self.assertNotIn("SECRET INTERNAL TEXT", str(customer_payload))
        self.assertNotIn("SECRET INTERNAL TEXT", notification)

        activity = ticket.activities.filter(action=TicketActivity.Action.INTERNAL_NOTE).get()
        self.assertEqual(activity.new_value, "Internal note added")

        tracked = self.client.get("/support/track/", {"ticket_number": ticket.ticket_number, "email": ticket.customer.email})
        self.assertContains(tracked, "Audit subject")
        self.assertNotContains(tracked, "SECRET INTERNAL TEXT")

    def test_assigned_agent_activity_history_hides_internal_notes(self):
        ticket = self.make_ticket()
        accept_ticket(ticket.pk, self.agent)
        add_staff_comment(ticket.pk, self.agent, "SECRET HISTORY TEXT", "internal")
        self.client.force_login(self.agent)
        response = self.client.get(f"/activity/ticket/{ticket.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "SECRET HISTORY TEXT")

    def test_activity_delete_update_and_save_are_blocked(self):
        ticket = self.make_ticket()
        activity = ticket.activities.get()
        with self.assertRaises(Exception):
            activity.delete()
        with self.assertRaises(Exception):
            TicketActivity.objects.filter(pk=activity.pk).delete()
        with self.assertRaises(Exception):
            TicketActivity.objects.filter(pk=activity.pk).update(new_value="tampered")

    def test_weekend_and_after_hours_align_to_next_working_period(self):
        from django.utils.timezone import make_aware
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from sla.business_hours import add_business_minutes
        tz = ZoneInfo("Asia/Kolkata")
        friday_evening = make_aware(datetime(2026, 11, 20, 18, 30), tz)
        deadline = add_business_minutes(friday_evening, 60)
        self.assertEqual(deadline.weekday(), 0)
        self.assertEqual((deadline.hour, deadline.minute), (10, 30))

        saturday = make_aware(datetime(2026, 11, 21, 12, 0), tz)
        monday_end = add_business_minutes(saturday, 540)
        self.assertEqual(monday_end.weekday(), 0)
        self.assertEqual((monday_end.hour, monday_end.minute), (18, 30))

    def test_waiting_timer_pauses_and_resumes_with_exact_business_elapsed(self):
        from django.utils.timezone import make_aware
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from sla.services import pause_waiting, resume_waiting
        tz = ZoneInfo("Asia/Kolkata")
        ticket = self.make_ticket()
        start = make_aware(datetime(2026, 11, 23, 10, 0), tz)
        end = make_aware(datetime(2026, 11, 23, 10, 30), tz)
        ticket.sla_anchor = start
        ticket.waiting_since = None
        ticket.save(update_fields=["sla_anchor", "waiting_since"])
        pause_waiting(ticket, start)
        resume_waiting(ticket, end)
        self.assertEqual(ticket.waiting_since, None)
        self.assertEqual(ticket.total_paused_business_minutes, 30)

    def test_waiting_ticket_closes_after_five_business_days(self):
        from django.utils.timezone import make_aware
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from tickets.services import change_status, close_expired_waiting_tickets
        tz = ZoneInfo("Asia/Kolkata")
        ticket = self.make_ticket()
        assign_ticket(ticket.pk, self.agent, self.manager)
        change_status(ticket.pk, TicketStatus.WAITING, self.manager)
        ticket.refresh_from_db()
        ticket.waiting_since = make_aware(datetime(2026, 11, 16, 9, 30), tz)
        ticket.save(update_fields=["waiting_since"])
        now = make_aware(datetime(2026, 11, 21, 9, 30), tz)
        closed = close_expired_waiting_tickets(now=now)
        self.assertEqual(len(closed), 1)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.CLOSED)

    def test_resolved_ticket_reopens_before_and_rejects_after_five_business_days(self):
        from django.utils.timezone import make_aware
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from tickets.services import change_status
        tz = ZoneInfo("Asia/Kolkata")
        ticket = self.make_ticket()
        assign_ticket(ticket.pk, self.agent, self.manager)
        now_resolved = make_aware(datetime(2026, 11, 23, 12, 0), tz)
        change_status(ticket.pk, TicketStatus.RESOLVED, self.manager, now=now_resolved)

        reopened_at = make_aware(datetime(2026, 11, 27, 12, 0), tz)
        reopened = reopen_ticket(ticket.pk, customer_email=ticket.customer.email, now=reopened_at)
        self.assertEqual(reopened.status, TicketStatus.OPEN)

        ticket2 = self.make_ticket(email="owner2@example.com")
        assign_ticket(ticket2.pk, self.agent, self.manager)
        resolved_late = make_aware(datetime(2026, 11, 16, 12, 0), tz)
        change_status(ticket2.pk, TicketStatus.RESOLVED, self.manager, now=resolved_late)
        with self.assertRaises(Exception):
            reopen_ticket(ticket2.pk, customer_email=ticket2.customer.email, now=make_aware(datetime(2026, 11, 30, 12, 0), tz))

    def test_role_permissions_and_cross_customer_tracking(self):
        ticket = self.make_ticket(email="owner@example.com")
        assign_ticket(ticket.pk, self.agent, self.manager)

        self.client.force_login(self.agent)
        self.assertEqual(self.client.get(f"/tickets/{ticket.pk}/").status_code, 200)

        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(f"/tickets/{ticket.pk}/").status_code, 200)

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(f"/tickets/{ticket.pk}/").status_code, 200)

        self.client.logout()
        wrong = self.client.get("/support/track/", {"ticket_number": ticket.ticket_number, "email": "other@example.com"})
        self.assertNotContains(wrong, "Audit subject")

    def test_api_lists_no_internal_notes_to_agents(self):
        ticket = self.make_ticket()
        accept_ticket(ticket.pk, self.agent)
        add_staff_comment(ticket.pk, self.agent, "API SECRET INTERNAL", "internal")
        add_staff_comment(ticket.pk, self.agent, "Public API text", "public")
        self.client.force_login(self.agent)
        response = self.client.get(f"/api/tickets/{ticket.pk}/comments/")
        self.assertEqual(response.status_code, 200)
        body = str(response.json())
        self.assertNotIn("API SECRET INTERNAL", body)
        self.assertIn("Public API text", body)

    def test_festival_holiday_excludes_working_time(self):
        from datetime import datetime
        from django.utils.timezone import make_aware
        from zoneinfo import ZoneInfo
        from sla.models import BusinessHoliday
        from sla.business_hours import add_business_minutes
        tz = ZoneInfo("Asia/Kolkata")
        festival = make_aware(datetime(2026, 11, 24, 12, 0), tz)
        BusinessHoliday.objects.create(date=make_aware(datetime(2026, 11, 23, 12, 0), tz).date(), name="Test Festival")
        deadline = add_business_minutes(make_aware(datetime(2026, 11, 20, 18, 30), tz), 60)
        self.assertEqual(deadline.date().isoformat(), "2026-11-24")
        self.assertEqual((deadline.hour, deadline.minute), (10, 30))

    def test_priority_change_recalculates_both_deadlines(self):
        ticket = self.make_ticket()
        original_resolution = ticket.resolution_deadline
        change_priority = __import__("tickets.services", fromlist=["change_priority"]).change_priority
        change_priority(ticket.pk, Priority.URGENT, self.manager)
        ticket.refresh_from_db()
        self.assertEqual(ticket.priority, Priority.URGENT)
        self.assertNotEqual(ticket.resolution_deadline, original_resolution)

    def test_priority_change_during_wait_includes_elapsed_wait(self):
        from django.utils.timezone import make_aware
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from tickets.services import change_priority
        tz = ZoneInfo("Asia/Kolkata")
        ticket = self.make_ticket()
        assign_ticket(ticket.pk, self.agent, self.manager)
        change_status(ticket.pk, TicketStatus.WAITING, self.manager, now=make_aware(datetime(2026, 11, 23, 10, 0), tz))
        ticket.refresh_from_db()
        resolution_before = ticket.resolution_deadline
        change_priority(ticket.pk, Priority.LOW, self.manager, now=make_aware(datetime(2026, 11, 23, 10, 30), tz))
        ticket.refresh_from_db()
        self.assertNotEqual(ticket.resolution_deadline, resolution_before)
        self.assertEqual(ticket.total_paused_business_minutes, 0)

    def test_reopen_resets_response_sla_clock(self):
        ticket = self.make_ticket()
        accept_ticket(ticket.pk, self.agent)
        add_staff_comment(ticket.pk, self.agent, "Initial response", "public")
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.first_response_at)
        change_status(ticket.pk, TicketStatus.RESOLVED, self.manager)
        reopened = reopen_ticket(ticket.pk, actor=self.manager)
        reopened.refresh_from_db()
        self.assertIsNone(reopened.first_response_at)

    def test_public_api_submission_and_private_tracking_are_available(self):
        response = self.client.post("/api/tickets/submit/", {
            "customer_name": "API Customer",
            "customer_email": "api@example.com",
            "subject": "API subject",
            "description": "API ticket description.",
            "category": self.category.pk,
            "priority": Priority.LOW,
        }, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        ticket_number = response.json()["ticket_number"]
        tracked = self.client.get("/support/track/", {"ticket_number": ticket_number, "email": "api@example.com"})
        self.assertContains(tracked, "API subject")

    def test_priority_api_recalculates_deadline(self):
        ticket = self.make_ticket()
        before = ticket.resolution_deadline
        self.client.force_login(self.manager)
        response = self.client.post(f"/api/tickets/{ticket.pk}/priority/", {"priority": Priority.URGENT}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.priority, Priority.URGENT)
        self.assertNotEqual(ticket.resolution_deadline, before)

    def test_agent_dashboard_sections_present(self):
        ticket = self.make_ticket()
        accept_ticket(ticket.pk, self.agent)
        change_status(ticket.pk, TicketStatus.WAITING, self.agent)
        self.client.force_login(self.agent)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assigned")
        self.assertContains(response, "Waiting")
        self.assertContains(response, "Overdue")

    def test_frontend_pages_render_for_roles(self):
        ticket = self.make_ticket()
        accept_ticket(ticket.pk, self.agent)

        self.client.force_login(self.admin)
        for url in ["/", "/tickets/", "/tickets/queue/", "/tickets/new/", f"/tickets/{ticket.pk}/", f"/activity/ticket/{ticket.pk}/", "/accounts/users/"]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)

        self.client.force_login(self.manager)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get(f"/tickets/{ticket.pk}/").status_code, 200)

        self.client.force_login(self.agent)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/tickets/queue/").status_code, 200)
        self.assertEqual(self.client.get(f"/tickets/{ticket.pk}/").status_code, 200)

        self.client.logout()
        for url in ["/accounts/login/", "/support/submit/", "/support/track/"]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)

    def test_ticket_create_empty_form_shows_validation_errors(self):
        self.client.force_login(self.admin)
        response = self.client.post("/tickets/new/", {})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertContains(response, "This field is required.")

    def test_customer_tracking_empty_and_wrong_ticket_states(self):
        response = self.client.get("/support/track/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Track your ticket")

        wrong = self.client.get("/support/track/", {"ticket_number": "FD-99999", "email": "nobody@example.com"})
        self.assertContains(wrong, "Ticket not found")

    def test_customer_resolved_reply_reopens_ticket(self):
        ticket = self.make_ticket()
        assign_ticket(ticket.pk, self.agent, self.manager)
        change_status(ticket.pk, TicketStatus.RESOLVED, self.manager)
        response = self.client.post("/support/track/", {
            "ticket_number": ticket.ticket_number,
            "email": ticket.customer.email,
            "body": "Please reopen this",
        })
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.OPEN)
