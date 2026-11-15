"""WebSocket tests for the chat consumer."""

import json

import pytest
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser

from chat.models import Chat, ChatParticipant, Message
from Fools_Arena.routing import websocket_application


def _communicator(path, user):
    communicator = WebsocketCommunicator(websocket_application, path)
    communicator.scope["user"] = user
    return communicator


@pytest.mark.django_db(transaction=True)
def test_guest_chat_socket_is_closed():
    """A socket with no user is rejected before it joins the room."""
    chat = Chat.objects.create(name="room", is_group=True)

    async def open_socket():
        communicator = _communicator(f"/ws/chat/{chat.id}/", AnonymousUser())
        connected, code = await communicator.connect()
        return connected, code

    connected, code = async_to_sync(open_socket)()
    assert connected is False
    assert code == 4401


@pytest.mark.django_db(transaction=True)
def test_non_member_chat_socket_is_closed(test_user):
    """A signed-in user who is not in the chat is rejected."""
    chat = Chat.objects.create(name="room", is_group=True)

    async def open_socket():
        communicator = _communicator(f"/ws/chat/{chat.id}/", test_user)
        connected, code = await communicator.connect()
        return connected, code

    connected, code = async_to_sync(open_socket)()
    assert connected is False
    assert code == 403


@pytest.mark.django_db(transaction=True)
def test_member_receives_recent_messages(test_user):
    """Connecting sends the messages already stored in the chat."""
    chat = Chat.objects.create(name="room", is_group=True)
    ChatParticipant.objects.create(chat=chat, user=test_user, role="member")
    Message.objects.create(sender=test_user, chat=chat, content="already here")

    async def read_history():
        communicator = _communicator(f"/ws/chat/{chat.id}/", test_user)
        connected, _code = await communicator.connect()
        payload = json.loads(await communicator.receive_from())
        await communicator.disconnect()
        return connected, payload

    connected, payload = async_to_sync(read_history)()
    assert connected is True
    assert payload["type"] == "last_messages"
    assert payload["messages"][0]["content"] == "already here"


@pytest.mark.django_db(transaction=True)
def test_member_send_is_stored_and_echoed(test_user):
    """A text frame becomes a Message row and comes back on the same socket."""
    chat = Chat.objects.create(name="room", is_group=True)
    ChatParticipant.objects.create(chat=chat, user=test_user, role="member")

    async def send_line():
        communicator = _communicator(f"/ws/chat/{chat.id}/", test_user)
        connected, _code = await communicator.connect()
        await communicator.receive_from()
        await communicator.send_to(text_data=json.dumps({"message": "hi"}))
        payload = json.loads(await communicator.receive_from())
        await communicator.disconnect()
        return connected, payload

    connected, payload = async_to_sync(send_line)()
    assert connected is True
    assert payload["content"] == "hi"
    assert payload["sender_id"] == str(test_user.id)
    assert Message.objects.filter(chat=chat, content="hi", sender=test_user).exists()
