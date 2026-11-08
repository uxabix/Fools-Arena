"""REST API views for chat listing, direct chats, and messages."""

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
from .services import assert_can_send_message

User = get_user_model()


class ChatListAPIView(generics.ListAPIView):
    """List chats the current user participates in."""

    serializer_class = ChatSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return distinct chats for the request user, newest first."""
        return (
            Chat.objects.filter(chatparticipant__user=self.request.user)
            .distinct()
            .order_by("-created_at")
        )

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

        chat, created = Chat.objects.get_or_create_direct(request.user, other)
        out = ChatSerializer(chat, context={"request": request})
        return Response(out.data, status=201 if created else 200)


class ChatMessagesAPIView(generics.ListCreateAPIView):
    """List recent messages in a chat or post a new message."""

    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        """Use create serializer for POST, read serializer for GET."""
        if self.request.method == "POST":
            return MessageCreateSerializer
        return MessageSerializer

    def get_queryset(self):
        """Messages for this chat, visible only to participants."""
        chat_id = self.kwargs["chat_id"]
        return (
            Message.objects.filter(
                chat_id=chat_id,
                chat__chatparticipant__user=self.request.user,
            )
            .distinct()
            .order_by("-sent_at")[:50]
        )

    def perform_create(self, serializer):
        """Persist a message after membership and block checks."""
        chat = get_object_or_404(Chat, pk=self.kwargs["chat_id"])
        if not chat.has_participant(self.request.user):
            raise PermissionDenied("You are not a member of this chat.")

        try:
            assert_can_send_message(chat, self.request.user)
        except PermissionError as exc:
            raise PermissionDenied(str(exc)) from exc

        serializer.save(sender=self.request.user, chat=chat)
