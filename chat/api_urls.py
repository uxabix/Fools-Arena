"""URL routes for the chat REST API.

These patterns are included under ``api/chat/`` in the project root ``urls.py``, so
effective paths are:

    /api/chat/chats/
    /api/chat/chats/direct/
    /api/chat/chats/<uuid>/messages/
"""

from django.urls import path

from .api_views import ChatListAPIView, ChatMessagesAPIView, DirectChatCreateAPIView

urlpatterns = [
    path("chats/", ChatListAPIView.as_view(), name="chat-list"),
    path("chats/direct/", DirectChatCreateAPIView.as_view(), name="chat-direct-create"),
    path(
        "chats/<uuid:chat_id>/messages/",
        ChatMessagesAPIView.as_view(),
        name="chat-messages",
    ),
]
