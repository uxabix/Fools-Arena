from django.urls import path

from fools import views

urlpatterns = [
    path("", views.lobby_list_page, name="fools-lobby-list-page"),
    path("lobbies/<uuid:lobby_id>/", views.lobby_detail_page, name="fools-lobby-detail-page"),
    path("play/<uuid:game_id>/", views.game_play_page, name="fools-play-page"),
]
