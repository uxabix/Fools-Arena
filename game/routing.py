from django.urls import path

from game import consumers

websocket_urlpatterns = [
    path("ws/lobbies/<uuid:lobby_id>/", consumers.LobbyConsumer.as_asgi()),
    path("ws/games/<uuid:game_id>/", consumers.GameConsumer.as_asgi()),
]
