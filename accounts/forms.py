from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)

from config.forms import TailwindFormMixin

from .models import User


class RegistrationForm(TailwindFormMixin, UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class LoginForm(TailwindFormMixin, AuthenticationForm):
    pass


class StyledPasswordChangeForm(TailwindFormMixin, PasswordChangeForm):
    pass


class StyledPasswordResetForm(TailwindFormMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(TailwindFormMixin, SetPasswordForm):
    pass
