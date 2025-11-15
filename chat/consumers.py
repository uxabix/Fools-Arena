import json
from channels.generic.websocket import AsyncWebsocketConsumer


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.room_group_name = f"chat_{self.room_name}"

        # Подключаемся к группе (группы = комнаты)
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()  # принимаем соединение

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Принимаем сообщение от WebSocket
    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data["message"]

        # Рассылаем сообщение всем в группе
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": message
            }
        )

    # Обработка сообщения от группы
    async def chat_message(self, event):
        message = event["message"]

        # Отправляем обратно клиенту
        await self.send(text_data=json.dumps({
            "message": message
        }))
