from django.urls import path

from fools import consumers

websocket_urlpatterns = [
    path("ws/lobbies/", consumers.LobbyListConsumer.as_asgi()),
    path("ws/lobbies/<uuid:lobby_id>/", consumers.LobbyConsumer.as_asgi()),
    path("ws/games/<uuid:game_id>/", consumers.GameConsumer.as_asgi()),
]
