from django.urls import include, path
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsEmployee
from tickets.constants import CommentVisibility
from tickets.exceptions import TicketError
from tickets.models import Category, Ticket, TicketComment
from tickets import services


class TicketSerializer(serializers.ModelSerializer):
    customer = serializers.CharField(source="customer.name", read_only=True)
    assignee = serializers.CharField(source="assigned_agent.display_name", read_only=True, default=None)

    class Meta:
        model = Ticket
        fields = ["id", "ticket_number", "customer", "subject", "description", "priority", "status", "assignee", "created_at", "updated_at"]
        read_only_fields = fields


class CommentSerializer(serializers.ModelSerializer):
    author = serializers.CharField(source="author.display_name", read_only=True)

    class Meta:
        model = TicketComment
        fields = ["id", "author", "visibility", "body", "created_at"]
        read_only_fields = ["id", "author", "visibility", "created_at"]


class CommentCreateSerializer(serializers.Serializer):
    body = serializers.CharField(min_length=2)
    visibility = serializers.ChoiceField(choices=CommentVisibility.choices)


class TicketViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated, IsEmployee]

    def get_queryset(self):
        return Ticket.objects.visible_to(self.request.user).select_related("customer", "assigned_agent")

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        try:
            ticket = services.accept_ticket(pk, request.user)
        except TicketError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(TicketSerializer(ticket).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        if not request.user.can_oversee:
            return Response({"detail": "Manager or administrator access is required."}, status=status.HTTP_403_FORBIDDEN)
        from accounts.models import User
        try:
            agent = User.objects.get(pk=request.data.get("agent_id"), is_active=True, role=User.Role.AGENT)
            ticket = services.assign_ticket(pk, agent, request.user)
        except User.DoesNotExist:
            return Response({"detail": "Choose an active support agent."}, status=status.HTTP_400_BAD_REQUEST)
        except TicketError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(TicketSerializer(ticket).data)

    @action(detail=True, methods=["post"])
    def priority(self, request, pk=None):
        try:
            ticket = services.change_priority(pk, request.data.get("priority"), request.user)
        except TicketError as exc:
            code = status.HTTP_403_FORBIDDEN if "Only managers" in str(exc) else status.HTTP_409_CONFLICT
            return Response({"detail": str(exc)}, status=code)
        return Response(TicketSerializer(ticket).data)

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        try:
            ticket = services.change_status(pk, request.data.get("status"), request.user)
        except TicketError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(TicketSerializer(ticket).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        try:
            ticket = services.reopen_ticket(pk, actor=request.user)
        except TicketError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(TicketSerializer(ticket).data)

    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        ticket = self.get_object()
        try:
            services.assert_can_access(request.user, ticket)
        except TicketError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        if request.method == "POST":
            serializer = CommentCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            try:
                comment = services.add_staff_comment(
                    ticket.pk,
                    request.user,
                    serializer.validated_data["body"],
                    serializer.validated_data["visibility"],
                )
            except TicketError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
            return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)
        queryset = ticket.comments.all()
        if not request.user.can_oversee:
            queryset = queryset.exclude(visibility=CommentVisibility.INTERNAL)
        return Response(CommentSerializer(queryset, many=True).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def customer_submit(request):
    required = ["customer_name", "customer_email", "subject", "description", "category", "priority"]
    missing = [field for field in required if not request.data.get(field)]
    if missing:
        return Response({"detail": f"Missing fields: {', '.join(missing)}"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        ticket = services.create_ticket(
            customer_name=request.data["customer_name"],
            customer_email=request.data["customer_email"],
            subject=request.data["subject"],
            description=request.data["description"],
            category=int(request.data["category"]),
            priority=request.data["priority"],
            phone=request.data.get("phone", ""),
            company=request.data.get("company", ""),
        )
    except (TicketError, ValueError, Category.DoesNotExist):
        return Response({"detail": "Invalid ticket submission."}, status=status.HTTP_400_BAD_REQUEST)
    return Response(TicketSerializer(ticket).data, status=status.HTTP_201_CREATED)


urlpatterns = [
    path("tickets/submit/", customer_submit, name="ticket-api-submit"),
    path("tickets/", TicketViewSet.as_view({"get": "list"}), name="ticket-list"),
    path("tickets/<int:pk>/", TicketViewSet.as_view({"get": "retrieve"}), name="ticket-detail"),
    path("tickets/<int:pk>/accept/", TicketViewSet.as_view({"post": "accept"}), name="ticket-accept"),
    path("tickets/<int:pk>/assign/", TicketViewSet.as_view({"post": "assign"}), name="ticket-api-assign"),
    path("tickets/<int:pk>/priority/", TicketViewSet.as_view({"post": "priority"}), name="ticket-api-priority"),
    path("tickets/<int:pk>/status/", TicketViewSet.as_view({"post": "status"}), name="ticket-api-status"),
    path("tickets/<int:pk>/reopen/", TicketViewSet.as_view({"post": "reopen"}), name="ticket-api-reopen"),
    path("tickets/<int:pk>/comments/", TicketViewSet.as_view({"get": "comments", "post": "comments"}), name="ticket-comments"),
]
