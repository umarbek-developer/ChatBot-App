import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application1 = get_asgi_application()

from apps.chat.middleware import JWTAuthMiddleware
from apps.chat.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": application1,
    # JWTAuthMiddleware resolves ?token=<jwt> to scope['user']; AuthMiddlewareStack
    # still provides session auth as a fallback for browser sessions.
    "websocket": AllowedHostsOriginValidator(
        JWTAuthMiddleware(AuthMiddlewareStack(URLRouter(websocket_urlpatterns)))
    )
})

