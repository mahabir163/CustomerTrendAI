from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.generic import FormView

from .forms import RegistrationForm


class RegisterView(FormView):
    """Public sign-up. Logs the new user straight in.

    The `@login_not_required` exemption is applied in urls.py, because the
    project uses LoginRequiredMiddleware (everything is private by default).
    """

    template_name = "accounts/register.html"
    form_class = RegistrationForm

    def dispatch(self, request, *args, **kwargs):
        if not settings.ALLOW_REGISTRATION:
            raise Http404("Registration is closed.")
        if request.user.is_authenticated:
            return redirect(settings.LOGIN_REDIRECT_URL)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        messages.success(self.request, f"Welcome, {user.username}! Your account is ready.")
        return redirect(settings.LOGIN_REDIRECT_URL)


def settings_view(request):
    """Account page: who you are signed in as and how to change your password."""
    return render(request, "accounts/settings.html", {"page_title": "Settings"})
