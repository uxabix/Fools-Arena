from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import Chat, ChatParticipant, Message
import json

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]
        self.chat_id = self.scope["url_route"]["kwargs"]["chat_id"]

        # Check if user has access to the chat
        if not await self.user_can_access_chat():
            await self.close(code=403)  # Forbidden
            return

        self.room_group_name = f"chat_{self.chat_id}"

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Send last messages to the client
        last_messages = await self.get_last_messages()
        await self.send(text_data=json.dumps({
            "type": "last_messages",
            "messages": last_messages
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        content = data.get("message", "").strip()

        if content:
            message = await self.create_message(content)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "message": {
                        "id": str(message.id),
                        "sender": self.user.username,
                        "content": message.content,
                        "sent_at": str(message.sent_at)
                    }
                }
            )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))

    @database_sync_to_async
    def user_can_access_chat(self):
        try:
            chat = Chat.objects.get(id=self.chat_id)
        except Chat.DoesNotExist:
            return False
        return ChatParticipant.objects.filter(chat=chat, user=self.user).exists()

    @database_sync_to_async
    def create_message(self, content):
        chat = Chat.objects.get(id=self.chat_id)
        return Message.objects.create(sender=self.user, chat=chat, content=content)

    @database_sync_to_async
    def get_last_messages(self, limit=50):
        chat = Chat.objects.get(id=self.chat_id)
        messages = chat.messages.order_by('-sent_at')[:limit]
        return [
            {"id": str(m.id), "sender": m.sender.username, "content": m.content, "sent_at": str(m.sent_at)}
            for m in reversed(messages)
        ]
