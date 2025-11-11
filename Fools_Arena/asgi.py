"""
ASGI config for Fools_Arena project.

It exposes the ASGI callable as a module-level variable namedя ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter

from Fools_Arena.routing import websocket_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fools_Arena.settings")

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(websocket_application),
})