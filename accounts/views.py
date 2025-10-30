from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_protect

from .forms import RegistrationForm, LoginForm

@csrf_protect
def register_view(request):
    """Register a new user and log them in."""
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
    """Authenticate and log in an existing user."""
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
    """Display the authenticated user's profile."""
    return render(request, 'accounts/profile.html')

@csrf_protect
def logout_view(request):
    """Log out the current user."""
    if request.method == 'POST':
        auth_logout(request)
        return redirect('login')
    return redirect('profile')
