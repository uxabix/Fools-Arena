"""
URL configuration for Fools_Arena project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.shortcuts import redirect
from django.urls import path, include


def home(request):
    """Send visitors to games when signed in, otherwise to login."""
    if request.user.is_authenticated:
        return redirect("fools-lobby-list-page")
    return redirect("login")


urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),
    # UI
    path("accounts/", include("accounts.urls")),
    path("chat/", include("chat.urls")),
    path("fools/", include("fools.urls")),
    # API
    path("api/accounts/", include("accounts.api_urls")),
    path("api/chat/", include("chat.api_urls")),
    path("api/fools/", include("fools.api_urls")),
]

# Static files: in DEBUG serve straight from app ``static/`` folders (no collectstatic needed).
# When DEBUG is off, use a real web server or WhiteNoise + collectstatic in production.
if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
else:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
