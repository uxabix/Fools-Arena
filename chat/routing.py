from django.urls import re_path
from .consumers import ChatConsumer

websocket_urlpatterns = [
    # Universal chat consumer for all chat types
    re_path(r'ws/chat/(?P<chat_id>[0-9a-f-]+)/$', ChatConsumer.as_asgi()),
]
