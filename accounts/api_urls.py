from django.urls import path
from .api_views import RegistrationAPI, LoginAPI, ProfileAPI, LogoutAPI

urlpatterns = [
    path('auth/register/', RegistrationAPI.as_view(), name='api_register'),
    path('auth/login/', LoginAPI.as_view(), name='api_login'),
    path('auth/profile/', ProfileAPI.as_view(), name='api_profile'),
    path('auth/logout/', LogoutAPI.as_view(), name='api_logout'),
]
