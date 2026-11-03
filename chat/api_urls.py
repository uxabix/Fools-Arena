"""URL routes for the chat REST API.

These patterns are included under ``api/chat/`` in the project root ``urls.py``, so
effective paths are:

    /api/chat/chats/
    /api/chat/chats/direct/
    /api/chat/users/?q=
    /api/chat/chats/<uuid>/messages/
    /api/chat/chats/<uuid>/read/
"""

from django.urls import path

from .api_views import (
    ChatListAPIView,
    ChatMessagesAPIView,
    ChatReadAPIView,
    DirectChatCreateAPIView,
    UserSearchAPIView,
)

urlpatterns = [
    path("chats/", ChatListAPIView.as_view(), name="chat-list"),
    path("chats/direct/", DirectChatCreateAPIView.as_view(), name="chat-direct-create"),
    path("users/", UserSearchAPIView.as_view(), name="chat-user-search"),
    path(
        "chats/<uuid:chat_id>/messages/",
        ChatMessagesAPIView.as_view(),
        name="chat-messages",
    ),
    path(
        "chats/<uuid:chat_id>/read/",
        ChatReadAPIView.as_view(),
        name="chat-read",
    ),
]
