from django.urls import path

from game import views

urlpatterns = [
    path("", views.lobby_list_page, name="game-lobby-list-page"),
    path("lobbies/<uuid:lobby_id>/", views.lobby_detail_page, name="game-lobby-detail-page"),
    path("play/<uuid:game_id>/", views.game_play_page, name="game-play-page"),
]
