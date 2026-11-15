from channels.routing import URLRouter

from chat.routing import websocket_urlpatterns as chat_routes
from fools.routing import websocket_urlpatterns as fools_routes

# AuthMiddlewareStack is applied once in asgi.py (do not wrap here too).
websocket_application = URLRouter(chat_routes + fools_routes)
