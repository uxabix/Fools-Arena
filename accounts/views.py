"""
Views for the Accounts app.

This module defines function-based views for handling user authentication
through HTML templates. It includes registration, login, profile display,
and logout functionality. These views are connected to the routes defined
in accounts/urls.py and render templates located in accounts/templates/accounts/.

Available views:
    - register_view: render and process the registration form.
    - login_view: render and process the login form.
    - profile_view: display the authenticated user's profile page.
    - logout_view: log out the current user and redirect accordingly.
"""

from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_protect

from .forms import RegistrationForm, LoginForm

@csrf_protect
def register_view(request):
    """
    Render and process the registration form.

    If the request method is POST and the form is valid, a new user
    is created and automatically logged in. On success, the user is
    redirected to the profile page. Otherwise, the registration form
    is re-rendered with validation errors.
    """
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect('profile')
    else:
        form = RegistrationForm()
    return render(request, 'accounts/registration.html', {'form': form})

@csrf_protect
def login_view(request):
    """
    Render and process the login form.

    If the request method is POST and the form is valid, the user
    is authenticated and logged in. On success, the user is redirected
    to the profile page. Otherwise, the login form is re-rendered with
    validation errors.
    """
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            auth_login(request, form.get_user())
            return redirect('profile')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})

@login_required
def profile_view(request):
    """
    Display the authenticated user's profile page.

    Requires the user to be logged in. If the user is not authenticated,
    they will be redirected to the login page.
    """
    return render(request, 'accounts/profile.html')

@csrf_protect
def logout_view(request):
    """
    Log out the current user.

    If the request method is POST, the user is logged out and redirected
    to the login page. For non-POST requests, the user is redirected
    back to the profile page.
    """
    if request.method == 'POST':
        auth_logout(request)
        return redirect('login')
    return redirect('profile')
