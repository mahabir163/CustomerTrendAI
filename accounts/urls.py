from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.urls import path, reverse_lazy

from . import views
from .forms import (
    LoginForm,
    StyledPasswordChangeForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)

app_name = "accounts"

# Pages an anonymous visitor must be able to reach are wrapped in
# `login_not_required`; everything else is protected by the middleware.
urlpatterns = [
    path("settings/", views.settings_view, name="settings"),
    path(
        "login/",
        login_not_required(
            auth_views.LoginView.as_view(
                template_name="accounts/login.html",
                authentication_form=LoginForm,
                redirect_authenticated_user=True,
            )
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),  # POST only
    path("register/", login_not_required(views.RegisterView.as_view()), name="register"),
    # Password change (signed-in users)
    path(
        "password-change/",
        auth_views.PasswordChangeView.as_view(
            template_name="accounts/password_change.html",
            form_class=StyledPasswordChangeForm,
            success_url=reverse_lazy("accounts:password_change_done"),
        ),
        name="password_change",
    ),
    path(
        "password-change/done/",
        auth_views.PasswordChangeDoneView.as_view(template_name="accounts/password_change_done.html"),
        name="password_change_done",
    ),
    # Password reset (anonymous users, by email link)
    path(
        "password-reset/",
        login_not_required(
            auth_views.PasswordResetView.as_view(
                template_name="accounts/password_reset.html",
                email_template_name="accounts/password_reset_email.txt",
                subject_template_name="accounts/password_reset_subject.txt",
                form_class=StyledPasswordResetForm,
                success_url=reverse_lazy("accounts:password_reset_done"),
            )
        ),
        name="password_reset",
    ),
    path(
        "password-reset/sent/",
        login_not_required(
            auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html")
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        login_not_required(
            auth_views.PasswordResetConfirmView.as_view(
                template_name="accounts/password_reset_confirm.html",
                form_class=StyledSetPasswordForm,
                success_url=reverse_lazy("accounts:password_reset_complete"),
            )
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        login_not_required(
            auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html")
        ),
        name="password_reset_complete",
    ),
]
