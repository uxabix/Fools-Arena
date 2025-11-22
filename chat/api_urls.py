from django.urls import path
from .api_views import ChatListAPIView, ChatMessagesAPIView

urlpatterns = [
    # All chat available for user
    path('api/chats/', ChatListAPIView.as_view(), name='chat-list'),

    # Get all messages for a specific chat
    path('api/chats/<uuid:chat_id>/messages/', ChatMessagesAPIView.as_view(), name='chat-messages'),
]