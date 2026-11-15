"""REST API views for chat listing, direct chats, and messages."""

import logging

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Chat, Message
from .serializers import (
    ChatSerializer,
    DirectChatCreateSerializer,
    MessageCreateSerializer,
    MessageSerializer,
)
from .services import (
    assert_can_send_message,
    broadcast_chat_message,
    chat_list_params,
    mark_chat_read,
    message_page,
    parse_message_id,
    page_limit,
    visible_chats,
)

logger = logging.getLogger(__name__)

User = get_user_model()


class ChatListAPIView(generics.ListAPIView):
    """List chats the current user participates in."""

    serializer_class = ChatSerializer
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        """Return filtered chats for the same query string the inbox uses."""
        chats = visible_chats(request.user, chat_list_params(request))
        serializer = self.get_serializer(chats, many=True)
        return Response(serializer.data)

    def get_serializer_context(self):
        """Attach ``request`` for peer fields on DM chats."""
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx


class DirectChatCreateAPIView(APIView):
    """Open or create a private 1-on-1 chat with another user by id."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Create or return the DM ``Chat`` for the authenticated user and ``other_user_id``.

        Returns:
            Response: Serialized chat; status 201 if created, 200 if it already existed.

        Raises:
            ValidationError: If serializer input is invalid (handled by DRF).
        """
        ser = DirectChatCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        other = get_object_or_404(User, pk=ser.validated_data["other_user_id"])

        if other.pk == request.user.pk:
            return Response(
                {"detail": "Cannot open a direct chat with yourself."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if other.is_bot or not other.is_active:
            return Response(
                {"detail": "Cannot open a direct chat with that player."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        chat, created = Chat.objects.get_or_create_direct(request.user, other)
        out = ChatSerializer(chat, context={"request": request})
        return Response(out.data, status=201 if created else 200)


class ChatMessagesAPIView(generics.ListCreateAPIView):
    """List one page of messages in a chat or post a new message.

    ``GET`` returns the latest page, oldest first. ``before`` is a message id
    for the previous page. ``limit`` defaults to 40 and cannot exceed 50.
    ``envelope=1`` wraps the list as ``{"results", "has_older"}``. Without it
    the body stays a JSON list so older clients keep working.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        """Use create serializer for POST, read serializer for GET."""
        if self.request.method == "POST":
            return MessageCreateSerializer
        return MessageSerializer

    def get_queryset(self):
        """Kept for the create mixin. Listing uses :meth:`list`."""
        return Message.objects.none()

    def list(self, request, *args, **kwargs):
        """Return one chronological page for a participant."""
        chat = get_object_or_404(Chat, pk=self.kwargs["chat_id"])
        if not chat.has_participant(request.user):
            raise PermissionDenied("You are not a member of this chat.")
        try:
            before_id = parse_message_id(request.query_params.get("before"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        rows, has_older = message_page(
            chat,
            before_id=before_id,
            limit=page_limit(request.query_params.get("limit")),
            text=request.query_params.get("q"),
        )
        data = MessageSerializer(rows, many=True).data
        if request.query_params.get("envelope") == "1":
            return Response({"results": data, "has_older": has_older})
        return Response(data)

    def create(self, request, *args, **kwargs):
        """Store a line and return the public message shape."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            MessageSerializer(serializer.instance).data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    def perform_create(self, serializer):
        """Persist a message after membership and block checks, then broadcast it."""
        chat = get_object_or_404(Chat, pk=self.kwargs["chat_id"])
        if not chat.has_participant(self.request.user):
            raise PermissionDenied("You are not a member of this chat.")

        try:
            assert_can_send_message(chat, self.request.user)
        except PermissionError as exc:
            logger.info(
                "Chat send denied user=%s chat=%s",
                self.request.user.pk,
                chat.pk,
            )
            raise PermissionDenied(str(exc)) from exc

        serializer.save(sender=self.request.user, chat=chat)
        broadcast_chat_message(serializer.instance)


class ChatReadAPIView(APIView):
    """Move the caller's read mark forward in one chat."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, chat_id):
        """Mark messages up to ``message_id`` as read, or up to now when it is omitted.

        The mark does not move backward. Other participants are not told.

        Returns:
            Response: ``{"last_read_at": ...}``.
        """
        chat = get_object_or_404(Chat, pk=chat_id)
        if not chat.has_participant(request.user):
            raise PermissionDenied("You are not a member of this chat.")
        try:
            message_id = parse_message_id(request.data.get("message_id"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        moment = None
        if message_id is not None:
            message = Message.objects.filter(pk=message_id, chat=chat).only("sent_at").first()
            if message is None:
                return Response(
                    {"detail": "Message not found."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            moment = message.sent_at
        participant = mark_chat_read(chat, request.user, at=moment)
        return Response({"last_read_at": participant.last_read_at.isoformat()})


class UserSearchAPIView(APIView):
    """Suggest active players by a username prefix.

    Requires a signed-in user. The query must be at least two characters.
    At most eight usernames are returned. Bots, inactive accounts, and the
    caller are left out. Email addresses are not searched or returned.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Return ``{"results": [{"id", "username"}, ...]}``."""
        query = (request.query_params.get("q") or "").strip()
        if len(query) < 2 or len(query) > 150:
            return Response(
                {"detail": "Enter at least 2 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rows = (
            User.objects.filter(is_active=True, is_bot=False, username__istartswith=query)
            .exclude(pk=request.user.pk)
            .order_by("username")
            .only("id", "username", "avatar_url")[:8]
        )
        return Response(
            {
                "results": [
                    {
                        "id": str(row.pk),
                        "username": row.username,
                        "initials": row.display_initials(),
                        "avatar_url": row.avatar_url or "",
                    }
                    for row in rows
                ]
            }
        )
