"""Root URL configuration.

Each app owns its URLs; this file only wires them together. Sections that are
built in later phases point at a shared placeholder view so the sidebar works
without showing any fake data.

Uploaded datasets are private, so MEDIA_URL is deliberately NOT served here.
Files are only reachable through permission-checked download views.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("assistant/", include("ai_assistant.urls")),
    path("reports/", include("reports.urls")),
    path("account/", include("accounts.urls")),
    path("", include("analytics.urls")),
]
