"""URL routes for the JSON API under ``/api/fools/``."""

from django.urls import path

from fools import api_views

urlpatterns = [
    path("lobbies/", api_views.LobbyListCreateAPI.as_view(), name="api-lobby-list"),
    path("lobbies/<uuid:lobby_id>/", api_views.LobbyDetailAPI.as_view(), name="api-lobby-detail"),
    path("lobbies/<uuid:lobby_id>/join/", api_views.LobbyJoinAPI.as_view(), name="api-lobby-join"),
    path("lobbies/<uuid:lobby_id>/leave/", api_views.LobbyLeaveAPI.as_view(), name="api-lobby-leave"),
    path("lobbies/<uuid:lobby_id>/ready/", api_views.LobbyReadyAPI.as_view(), name="api-lobby-ready"),
    path("lobbies/<uuid:lobby_id>/start/", api_views.LobbyStartAPI.as_view(), name="api-lobby-start"),
    path(
        "lobbies/<uuid:lobby_id>/messages/",
        api_views.LobbyMessagesAPI.as_view(),
        name="api-lobby-messages",
    ),
    path("games/<uuid:game_id>/", api_views.GameStateAPI.as_view(), name="api-fools-state"),
    path("games/<uuid:game_id>/attack/", api_views.GameAttackAPI.as_view(), name="api-fools-attack"),
    path("games/<uuid:game_id>/seal/", api_views.GameSealAPI.as_view(), name="api-fools-seal"),
    path("games/<uuid:game_id>/defend/", api_views.GameDefendAPI.as_view(), name="api-fools-defend"),
    path("games/<uuid:game_id>/take/", api_views.GameTakeAPI.as_view(), name="api-fools-take"),
    path("games/<uuid:game_id>/pass/", api_views.GamePassAPI.as_view(), name="api-fools-pass"),
    path("games/<uuid:game_id>/bito/", api_views.GameBitoAPI.as_view(), name="api-fools-bito"),
    path("games/<uuid:game_id>/leave/", api_views.GameLeaveAPI.as_view(), name="api-fools-leave"),
]
