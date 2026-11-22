from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import User
from tickets.constants import Priority, TicketStatus
from tickets.exceptions import TicketError
from tickets.forms import AssignForm, CommentForm, TicketCreateForm
from tickets.models import Ticket
from tickets import services


@login_required
def ticket_list(request):
    queryset = Ticket.objects.visible_to(request.user).select_related("customer", "category", "assigned_agent")
    status = request.GET.get("status")
    if status in TicketStatus.values:
        queryset = queryset.filter(status=status)
    search = request.GET.get("q", "").strip()
    if search:
        queryset = queryset.filter(subject__icontains=search) | queryset.filter(ticket_number__icontains=search)
    page = Paginator(queryset, 20).get_page(request.GET.get("page"))
    return render(request, "tickets/list.html", {"page": page, "statuses": TicketStatus.choices, "selected_status": status, "search": search})


@login_required
def ticket_queue(request):
    queryset = Ticket.objects.filter(status=TicketStatus.OPEN, assigned_agent__isnull=True).select_related("customer", "category")
    return render(request, "tickets/queue.html", {"tickets": queryset})


@login_required
def ticket_create(request):
    form = TicketCreateForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            ticket = services.create_ticket(created_by=request.user, **form.cleaned_data)
            messages.success(request, f"Ticket {ticket.ticket_number} created.")
            return redirect("tickets:detail", pk=ticket.pk)
        except TicketError as exc:
            messages.error(request, str(exc))
    return render(request, "tickets/create.html", {"form": form})


@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket.objects.select_related("customer", "category", "assigned_agent"), pk=pk)
    try:
        services.assert_can_access(request.user, ticket)
    except TicketError:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    form = CommentForm(request.POST if request.method == "POST" else None)
    assign_form = AssignForm()
    if request.method == "POST" and "comment" in request.POST:
        if form.is_valid():
            try:
                services.add_staff_comment(ticket.pk, request.user, form.cleaned_data["body"], form.cleaned_data["visibility"])
                messages.success(request, "Added to the ticket.")
                return redirect("tickets:detail", pk=pk)
            except TicketError as exc:
                messages.error(request, str(exc))
    activities = ticket.activities.all()
    comments = ticket.comments.all()
    if not request.user.can_oversee:
        comments = comments.exclude(visibility="internal")
    next_statuses = services.allowed_next_statuses(request.user, ticket)
    status_choices = [(value, TicketStatus(value).label) for value in next_statuses]
    return render(request, "tickets/detail.html", {"ticket": ticket, "form": form, "assign_form": assign_form, "activities": activities, "comments": comments, "next_statuses": status_choices, "priorities": Priority.choices})


@login_required
@require_POST
def accept(request, pk):
    try:
        ticket = services.accept_ticket(pk, request.user)
        messages.success(request, f"Accepted {ticket.ticket_number}.")
    except TicketError as exc:
        messages.error(request, str(exc))
    return redirect("tickets:detail", pk=pk)


@login_required
@require_POST
def assign(request, pk):
    form = AssignForm(request.POST)
    if form.is_valid():
        try:
            ticket = services.assign_ticket(pk, form.cleaned_data["agent"], request.user)
            messages.success(request, f"Assigned to {ticket.assigned_agent.display_name}.")
        except TicketError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Choose a valid agent.")
    return redirect("tickets:detail", pk=pk)


@login_required
@require_POST
def change_status(request, pk):
    try:
        services.change_status(pk, request.POST.get("status"), request.user)
        messages.success(request, "Ticket status updated.")
    except TicketError as exc:
        messages.error(request, str(exc))
    return redirect("tickets:detail", pk=pk)


@login_required
@require_POST
def reopen(request, pk):
    try:
        ticket = services.reopen_ticket(pk, actor=request.user)
        messages.success(request, f"Reopened {ticket.ticket_number}.")
    except TicketError as exc:
        messages.error(request, str(exc))
    return redirect("tickets:detail", pk=pk)


@login_required
@require_POST
def change_priority(request, pk):
    try:
        services.change_priority(pk, request.POST.get("priority"), request.user)
        messages.success(request, "Ticket priority updated.")
    except TicketError as exc:
        messages.error(request, str(exc))
    return redirect("tickets:detail", pk=pk)
