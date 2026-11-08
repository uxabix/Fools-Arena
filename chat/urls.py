"""
Template routes for the chat app (included under ``/chat/`` in the project URLs).

These mirror the REST API: inbox listing, starting a direct chat, and the room
with message history plus posting.
"""

from django.urls import path

from .views import chat_inbox, chat_room, start_direct_chat

app_name = "chat"

urlpatterns = [
    path("", chat_inbox, name="inbox"),
    path("direct/new/", start_direct_chat, name="start_direct"),
    path("<uuid:chat_id>/", chat_room, name="room"),
]
