"""
Forms for the Accounts app.

This module defines form classes used for user registration and login.
They extend Django's built-in authentication forms to include additional
fields or custom behavior where necessary.

Available forms:
    - RegistrationForm: extends UserCreationForm to include an email field.
    - LoginForm: extends AuthenticationForm for user login.
"""

from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model

User = get_user_model()

class RegistrationForm(UserCreationForm):
    """
    Form for user registration.

    Extends Django's built-in UserCreationForm by adding
    a required email field. Handles validation and creation
    of a new user instance with username, email, and password.
    """
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

class LoginForm(AuthenticationForm):
    """
    Form for user login.

    Extends Django's built-in AuthenticationForm without
    additional fields. Used to authenticate existing users
    with their username and password.
    """
    pass
