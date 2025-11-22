from rest_framework import generics, permissions
from .models import Chat, Message
from .serializers import MessageSerializer, ChatSerializer


class ChatMessagesAPIView(generics.ListAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        chat_id = self.kwargs['chat_id']
        return Message.objects.filter(
            chat_id=chat_id,
            chat__chatparticipant__user=self.request.user
        ).order_by('-sent_at')[:50]


class ChatListAPIView(generics.ListAPIView):
    serializer_class = ChatSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Chat.objects.filter(chatparticipant__user=self.request.user)
